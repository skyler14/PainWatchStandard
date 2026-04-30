#!/usr/bin/env python3
"""Exploratory self-supervised probes over pain feeder windows.

This is intentionally lightweight: it learns sensor interconnections,
next-window dynamics, and contrastive-style augmented-window structure from the
tabular feeder output before any supervised pain model is trained.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parent
DEFAULT_WINDOW_TABLE = ROOT / "_normalized" / "window_features" / "target_hz=1" / "window_features.parquet"
DEFAULT_OUTPUT = ROOT / "_normalized" / "self_supervised" / "exploratory_1hz_30s"

BLOCK_PREFIXES: dict[str, tuple[str, ...]] = {
    "bvp": ("bvp__",),
    "bvp_rb": ("bvp_rb__",),
    "hr": ("hr__",),
    "ibi": ("ibi__",),
    "ecg": ("ecg__",),
    "eda": ("eda__",),
    "eda_rb": ("eda_rb__",),
    "temperature": ("temperature__",),
    "acc": ("acc_x__", "acc_y__", "acc_z__", "acc__"),
    "gyro": ("gyro_x__", "gyro_y__", "gyro_z__", "gyro__"),
    "respiration": ("respiration__",),
    "emg": ("emg__",),
    "grip": ("grip__",),
    "bp_systolic": ("bp_systolic__",),
    "bp_diastolic": ("bp_diastolic__",),
    "spo2": ("spo2__",),
    "steps": ("steps__",),
    "eeg_delta": ("eeg_delta__",),
    "eeg_theta": ("eeg_theta__",),
    "eeg_alpha1": ("eeg_alpha1__",),
    "eeg_alpha2": ("eeg_alpha2__",),
    "eeg_beta1": ("eeg_beta1__",),
    "eeg_beta2": ("eeg_beta2__",),
    "eeg_gamma1": ("eeg_gamma1__",),
    "eeg_gamma2": ("eeg_gamma2__",),
    "eeg_attention": ("eeg_attention__",),
    "eeg_meditation": ("eeg_meditation__",),
}

RECONSTRUCTION_TARGETS: dict[str, str] = {
    "bvp": "bvp__mean",
    "bvp_rb": "bvp_rb__mean",
    "hr": "hr__mean",
    "ibi": "ibi__mean",
    "ecg": "ecg__mean",
    "eda": "eda__mean",
    "eda_rb": "eda_rb__mean",
    "temperature": "temperature__mean",
    "acc": "acc__mag__mean",
    "gyro": "gyro__mag__mean",
    "respiration": "respiration__mean",
    "emg": "emg__mean",
    "grip": "grip__mean",
    "bp_systolic": "bp_systolic__mean",
    "bp_diastolic": "bp_diastolic__mean",
    "spo2": "spo2__mean",
    "steps": "steps__mean",
    "eeg_delta": "eeg_delta__mean",
    "eeg_theta": "eeg_theta__mean",
    "eeg_alpha1": "eeg_alpha1__mean",
    "eeg_alpha2": "eeg_alpha2__mean",
    "eeg_beta1": "eeg_beta1__mean",
    "eeg_beta2": "eeg_beta2__mean",
    "eeg_gamma1": "eeg_gamma1__mean",
    "eeg_gamma2": "eeg_gamma2__mean",
    "eeg_attention": "eeg_attention__mean",
    "eeg_meditation": "eeg_meditation__mean",
}

NEXT_WINDOW_TARGETS = (
    "bvp__mean",
    "hr__mean",
    "ibi__mean",
    "ecg__mean",
    "eda__mean",
    "temperature__mean",
    "acc__mag__mean",
    "gyro__mag__mean",
    "respiration__mean",
    "emg__mean",
    "grip__mean",
    "bp_systolic__mean",
    "bp_diastolic__mean",
    "spo2__mean",
    "steps__mean",
    "eeg_delta__mean",
    "eeg_theta__mean",
)

ID_COLUMNS = {
    "subject_id",
    "session_id",
}

LABEL_COLUMNS = {
    "target_available",
    "target_pain_nrs_0_10",
    "target_pain_min",
    "target_pain_max",
    "target_pain_count",
    "target_pain_coverage",
    "target_pain_class_3",
    "target_scale",
    "target_granularity",
    "target_confidence",
    "no_pain_threshold",
    "severe_pain_threshold",
}

BASIC_METADATA_COLUMNS = {
    "dataset_id",
    "condition",
    "record_type",
    "device",
    "diagnosis",
    "sex",
    "age",
    "pain_scale_type",
    "baseline_available",
    "window_seconds",
    "target_hz",
    "source_archive",
    "source_member",
    "source_table",
    "source_modality",
    "activity_status",
    "aux_state_label",
    "proxy_label",
    "pain_type",
    "window_sampling",
}


@dataclass(frozen=True)
class ExplorationConfig:
    input_path: str
    output_dir: str
    metadata: str = "basic"
    random_state: int = 42
    min_rows: int = 500
    max_model_rows: int | None = None
    model_iterations: int = 80
    next_horizon_seconds: float = 1.0
    contrastive_sample: int = 8000
    contrastive_components: int = 16
    sensor_dropout_probability: float = 0.35
    noise_scale: float = 0.02
    balance_mode: str = "dataset_session"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def block_columns(columns: list[str], block: str) -> list[str]:
    prefixes = BLOCK_PREFIXES[block]
    return [column for column in columns if column.startswith(prefixes)]


def is_label_or_id(column: str) -> bool:
    return column in LABEL_COLUMNS or column in ID_COLUMNS or column.startswith("target_")


def feature_columns(
    frame: pd.DataFrame,
    excluded_block: str | None = None,
    metadata: str = "basic",
    exclude_future_targets: bool = True,
) -> list[str]:
    columns = list(frame.columns)
    excluded: set[str] = set(ID_COLUMNS) | set(LABEL_COLUMNS)
    excluded.add("ssl_weight")
    excluded.update(column for column in columns if column.startswith("target_"))
    if exclude_future_targets:
        excluded.update(column for column in columns if column.endswith("__future"))
    if excluded_block is not None:
        excluded.update(block_columns(columns, excluded_block))
    if metadata == "none":
        excluded.update(BASIC_METADATA_COLUMNS)
    elif metadata != "basic":
        raise ValueError("metadata must be 'basic' or 'none'")
    selected = [column for column in columns if column not in excluded]
    return [column for column in selected if frame[column].notna().any()]


def split_feature_types(frame: pd.DataFrame, columns: list[str]) -> tuple[list[str], list[str]]:
    numeric = [
        column
        for column in columns
        if pd.api.types.is_numeric_dtype(frame[column]) or pd.api.types.is_bool_dtype(frame[column])
    ]
    categorical = [column for column in columns if column not in numeric]
    return numeric, categorical


def make_preprocessor(frame: pd.DataFrame, columns: list[str], scale_numeric: bool = False) -> ColumnTransformer:
    numeric, categorical = split_feature_types(frame, columns)
    numeric_steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median", add_indicator=True))]
    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(("num", Pipeline(numeric_steps), numeric))
    if categorical:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", one_hot_encoder()),
                    ]
                ),
                categorical,
            )
        )
    return ColumnTransformer(transformers=transformers, remainder="drop", sparse_threshold=0.0)


def make_regressor(config: ExplorationConfig) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=config.model_iterations,
        learning_rate=0.06,
        l2_regularization=0.05,
        random_state=config.random_state,
        max_leaf_nodes=31,
        early_stopping=True,
    )


def supports_sample_weight(model: Pipeline) -> bool:
    return True


def grouped_train_test_indices(frame: pd.DataFrame, seed: int, test_size: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
    groups = (
        frame["dataset_id"].astype("string").fillna("dataset")
        + "::"
        + frame["subject_id"].astype("string").fillna("subject")
    )
    if groups.nunique() >= 3:
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train_idx, test_idx = next(splitter.split(frame, groups=groups))
        return train_idx, test_idx
    indices = np.arange(len(frame))
    return train_test_split(indices, test_size=test_size, random_state=seed)


def sample_rows(frame: pd.DataFrame, max_rows: int | None, seed: int) -> pd.DataFrame:
    if max_rows is None or len(frame) <= max_rows:
        return frame.copy()
    return frame.sample(n=max_rows, random_state=seed).sort_index()


def add_balance_weights(frame: pd.DataFrame, mode: str = "dataset_session") -> pd.DataFrame:
    """Add sample weights so dense datasets/sessions do not dominate probes."""
    out = frame.copy()
    if mode == "none":
        out["ssl_weight"] = 1.0
        return out
    if mode not in {"dataset", "dataset_session"}:
        raise ValueError("balance_mode must be one of: none, dataset, dataset_session")

    dataset_counts = out.groupby("dataset_id", dropna=False)["row_id"].transform("count").astype(float)
    dataset_count = max(float(out["dataset_id"].nunique(dropna=False)), 1.0)
    weights = len(out) / (dataset_count * dataset_counts)
    if mode == "dataset_session":
        session_key = [
            out["dataset_id"].astype("string").fillna("dataset"),
            out["subject_id"].astype("string").fillna("subject"),
            out["session_id"].astype("string").fillna("session"),
        ]
        session_counts = out.groupby(session_key, dropna=False)["row_id"].transform("count").astype(float)
        sessions_per_dataset = out.groupby("dataset_id", dropna=False)["session_id"].transform("nunique").astype(float)
        session_weights = len(out) / (dataset_count * sessions_per_dataset * session_counts)
        weights = session_weights
    out["ssl_weight"] = weights.astype(float)
    mean_weight = float(out["ssl_weight"].mean())
    if mean_weight > 0:
        out["ssl_weight"] = out["ssl_weight"] / mean_weight
    return out


def weight_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if "ssl_weight" not in frame.columns:
        return []
    summary = frame.groupby("dataset_id", dropna=False).agg(
        rows=("row_id", "size"),
        weight_sum=("ssl_weight", "sum"),
        weight_mean=("ssl_weight", "mean"),
        subjects=("subject_id", "nunique"),
        sessions=("session_id", "nunique"),
    )
    return summary.reset_index().to_dict(orient="records")


def metric_dict(y_true: np.ndarray, y_pred: np.ndarray, y_train: np.ndarray) -> dict[str, Any]:
    baseline = np.full_like(y_true, float(np.nanmean(y_train)), dtype=float)
    mae = float(mean_absolute_error(y_true, y_pred))
    baseline_mae = float(mean_absolute_error(y_true, baseline))
    rmse = float(math.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = None
    if np.unique(y_true).shape[0] > 1:
        r2 = float(r2_score(y_true, y_pred))
    return {
        "test_mae": mae,
        "baseline_mae": baseline_mae,
        "mae_improvement_vs_mean": float(1.0 - mae / baseline_mae) if baseline_mae > 0 else None,
        "test_rmse": rmse,
        "test_r2": r2,
    }


def weighted_metric_dict(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_train: np.ndarray,
    sample_weight: np.ndarray,
) -> dict[str, Any]:
    baseline = np.full_like(y_true, float(np.nanmean(y_train)), dtype=float)
    weighted_mae = float(mean_absolute_error(y_true, y_pred, sample_weight=sample_weight))
    weighted_baseline_mae = float(mean_absolute_error(y_true, baseline, sample_weight=sample_weight))
    weighted_rmse = float(math.sqrt(mean_squared_error(y_true, y_pred, sample_weight=sample_weight)))
    return {
        "weighted_test_mae": weighted_mae,
        "weighted_baseline_mae": weighted_baseline_mae,
        "weighted_mae_improvement_vs_mean": (
            float(1.0 - weighted_mae / weighted_baseline_mae) if weighted_baseline_mae > 0 else None
        ),
        "weighted_test_rmse": weighted_rmse,
    }


def run_regression_task(
    frame: pd.DataFrame,
    target_col: str,
    feature_cols: list[str],
    task_name: str,
    config: ExplorationConfig,
) -> tuple[dict[str, Any], pd.DataFrame | None]:
    valid = frame[target_col].notna()
    work = frame.loc[valid].copy()
    work = sample_rows(work, config.max_model_rows, config.random_state)
    if len(work) < config.min_rows:
        return (
            {
                "task": task_name,
                "target_column": target_col,
                "status": "skipped",
                "reason": f"only {len(work)} valid rows; min_rows={config.min_rows}",
                "rows": int(len(work)),
            },
            None,
        )

    train_idx, test_idx = grouped_train_test_indices(work, config.random_state)
    train = work.iloc[train_idx]
    test = work.iloc[test_idx]
    usable_feature_cols = [column for column in feature_cols if train[column].notna().any()]
    if not usable_feature_cols:
        return (
            {
                "task": task_name,
                "target_column": target_col,
                "status": "skipped",
                "reason": "no usable feature columns after train split",
                "rows": int(len(work)),
            },
            None,
        )

    model = Pipeline(
        [
            ("prep", make_preprocessor(train, usable_feature_cols, scale_numeric=False)),
            ("model", clone(make_regressor(config))),
        ]
    )
    fit_kwargs: dict[str, Any] = {}
    if "ssl_weight" in train.columns and supports_sample_weight(model):
        fit_kwargs["model__sample_weight"] = train["ssl_weight"].astype(float).to_numpy()
    model.fit(train[usable_feature_cols], train[target_col].astype(float), **fit_kwargs)
    pred_test = model.predict(test[usable_feature_cols])
    metrics = metric_dict(
        test[target_col].astype(float).to_numpy(),
        pred_test,
        train[target_col].astype(float).to_numpy(),
    )
    if "ssl_weight" in test.columns:
        metrics.update(
            weighted_metric_dict(
                test[target_col].astype(float).to_numpy(),
                pred_test,
                train[target_col].astype(float).to_numpy(),
                test["ssl_weight"].astype(float).to_numpy(),
            )
        )

    pred_all = model.predict(work[usable_feature_cols])
    split = pd.Series("unused", index=work.index)
    split.iloc[train_idx] = "train"
    split.iloc[test_idx] = "test"
    predictions = pd.DataFrame(
        {
            "row_id": work["row_id"].to_numpy(),
            "dataset_id": work["dataset_id"].to_numpy(),
            "subject_id": work["subject_id"].to_numpy(),
            "session_id": work["session_id"].to_numpy(),
            "window_end_s": work["window_end_s"].to_numpy(),
            "task": task_name,
            "target_column": target_col,
            "observed": work[target_col].astype(float).to_numpy(),
            "predicted": pred_all,
            "residual": work[target_col].astype(float).to_numpy() - pred_all,
            "split": split.to_numpy(),
            "ssl_weight": work.get("ssl_weight", pd.Series(1.0, index=work.index)).astype(float).to_numpy(),
        }
    )
    payload = {
        "task": task_name,
        "target_column": target_col,
        "status": "ok",
        "rows": int(len(work)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "features": int(len(usable_feature_cols)),
        **metrics,
    }
    return payload, predictions


def sensor_interconnection(frame: pd.DataFrame) -> pd.DataFrame:
    numeric = frame.select_dtypes(include=[np.number, "bool"]).copy()
    rows: list[dict[str, Any]] = []
    for target_block, target_col in RECONSTRUCTION_TARGETS.items():
        if target_col not in numeric.columns:
            continue
        y = numeric[target_col]
        for source_block in BLOCK_PREFIXES:
            if source_block == target_block:
                continue
            source_cols = [column for column in block_columns(list(numeric.columns), source_block) if column != target_col]
            corrs: list[float] = []
            for column in source_cols:
                pair = pd.concat([y, numeric[column]], axis=1).dropna()
                if len(pair) < 50 or pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
                    continue
                corr = pair.iloc[:, 0].corr(pair.iloc[:, 1])
                if pd.notna(corr):
                    corrs.append(abs(float(corr)))
            if corrs:
                top = sorted(corrs, reverse=True)[:5]
                rows.append(
                    {
                        "target_block": target_block,
                        "target_column": target_col,
                        "source_block": source_block,
                        "features_compared": len(corrs),
                        "max_abs_corr": max(corrs),
                        "mean_top5_abs_corr": float(np.mean(top)),
                    }
                )
    return pd.DataFrame(rows).sort_values(
        ["target_block", "max_abs_corr"], ascending=[True, False]
    )


def add_future_targets(frame: pd.DataFrame, horizon_seconds: float) -> pd.DataFrame:
    out = frame.sort_values(["dataset_id", "subject_id", "session_id", "window_end_s"]).copy()
    median_step = out.groupby(["dataset_id", "subject_id", "session_id"], dropna=False)["window_end_s"].diff().median()
    if pd.isna(median_step) or median_step <= 0:
        horizon_steps = 1
    else:
        horizon_steps = max(1, int(round(horizon_seconds / float(median_step))))
    for column in NEXT_WINDOW_TARGETS:
        if column in out.columns:
            out[f"{column}__future"] = out.groupby(
                ["dataset_id", "subject_id", "session_id"], dropna=False
            )[column].shift(-horizon_steps)
    return out


def augment_for_contrastive(
    frame: pd.DataFrame,
    numeric_cols: list[str],
    seed: int,
    dropout_probability: float,
    noise_scale: float,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = frame.copy()
    for block in BLOCK_PREFIXES:
        columns = [column for column in block_columns(numeric_cols, block) if column in out.columns]
        if not columns:
            continue
        mask = rng.random(len(out)) < dropout_probability
        if mask.any():
            out.loc[mask, columns] = np.nan
    for column in numeric_cols:
        if column not in out.columns:
            continue
        values = pd.to_numeric(out[column], errors="coerce")
        std = float(values.std(skipna=True))
        if math.isfinite(std) and std > 0 and noise_scale > 0:
            out[column] = values + rng.normal(0.0, noise_scale * std, size=len(out))
    return out


def normalized_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def run_contrastive_probe(frame: pd.DataFrame, config: ExplorationConfig) -> tuple[dict[str, Any], pd.DataFrame]:
    base = sample_rows(frame, config.contrastive_sample, config.random_state)
    feature_cols = feature_columns(base, metadata=config.metadata)
    numeric_cols, _ = split_feature_types(base, feature_cols)
    if len(base) < 10:
        return {"status": "skipped", "reason": "not enough rows"}, pd.DataFrame()

    preprocessor = make_preprocessor(base, feature_cols, scale_numeric=True)
    transformed = preprocessor.fit_transform(base[feature_cols])
    components = min(config.contrastive_components, transformed.shape[0] - 1, transformed.shape[1])
    pca = PCA(n_components=components, random_state=config.random_state)
    pca.fit(transformed)

    view_a = augment_for_contrastive(
        base,
        numeric_cols,
        seed=config.random_state + 1,
        dropout_probability=config.sensor_dropout_probability,
        noise_scale=config.noise_scale,
    )
    view_b = augment_for_contrastive(
        base,
        numeric_cols,
        seed=config.random_state + 2,
        dropout_probability=config.sensor_dropout_probability,
        noise_scale=config.noise_scale,
    )
    emb_a = normalized_rows(pca.transform(preprocessor.transform(view_a[feature_cols])))
    emb_b = normalized_rows(pca.transform(preprocessor.transform(view_b[feature_cols])))

    positive = np.sum(emb_a * emb_b, axis=1)
    shuffled = np.random.default_rng(config.random_state).permutation(len(base))
    negative = np.sum(emb_a * emb_b[shuffled], axis=1)

    neighbors = NearestNeighbors(n_neighbors=min(6, len(base)), metric="cosine")
    neighbors.fit(emb_b)
    distances, indices = neighbors.kneighbors(emb_a)
    top1 = indices[:, 0]
    base_reset = base.reset_index(drop=True)
    same_row = top1 == np.arange(len(base_reset))
    same_session = (
        base_reset.loc[top1, "session_id"].to_numpy() == base_reset["session_id"].to_numpy()
    )
    same_subject = (
        base_reset.loc[top1, "subject_id"].to_numpy() == base_reset["subject_id"].to_numpy()
    )
    same_dataset = (
        base_reset.loc[top1, "dataset_id"].to_numpy() == base_reset["dataset_id"].to_numpy()
    )

    embedding_frame = pd.DataFrame(
        {
            "row_id": base_reset["row_id"],
            "dataset_id": base_reset["dataset_id"],
            "subject_id": base_reset["subject_id"],
            "session_id": base_reset["session_id"],
            "window_end_s": base_reset["window_end_s"],
            "target_granularity": base_reset["target_granularity"],
            "target_available": base_reset["target_available"],
            "target_pain_nrs_0_10": base_reset["target_pain_nrs_0_10"],
            "positive_cosine": positive,
            "random_negative_cosine": negative,
            "top1_neighbor_row_id": base_reset.loc[top1, "row_id"].to_numpy(),
            "top1_neighbor_distance": distances[:, 0],
            "top1_same_row": same_row,
            "top1_same_session": same_session,
            "top1_same_subject": same_subject,
            "top1_same_dataset": same_dataset,
        }
    )
    for idx in range(components):
        embedding_frame[f"pca_{idx + 1:02d}"] = emb_a[:, idx]

    return (
        {
            "status": "ok",
            "rows": int(len(base)),
            "features": int(len(feature_cols)),
            "components": int(components),
            "explained_variance_ratio_sum": float(np.sum(pca.explained_variance_ratio_)),
            "positive_cosine_mean": float(np.mean(positive)),
            "random_negative_cosine_mean": float(np.mean(negative)),
            "positive_minus_negative_mean": float(np.mean(positive - negative)),
            "top1_same_row_rate": float(np.mean(same_row)),
            "top1_same_session_rate": float(np.mean(same_session)),
            "top1_same_subject_rate": float(np.mean(same_subject)),
            "top1_same_dataset_rate": float(np.mean(same_dataset)),
            "dropout_probability": config.sensor_dropout_probability,
            "noise_scale": config.noise_scale,
        },
        embedding_frame,
    )


def label_and_metadata_audit(frame: pd.DataFrame) -> dict[str, Any]:
    by_dataset = frame.groupby("dataset_id").agg(
        rows=("dataset_id", "size"),
        subjects=("subject_id", "nunique"),
        sessions=("session_id", "nunique"),
        target_available=("target_available", "sum"),
    )
    label_regimes = (
        frame.groupby(["dataset_id", "target_granularity"], dropna=False)
        .size()
        .reset_index(name="rows")
    )
    categorical_cardinality = {}
    for column in ["dataset_id", "condition", "record_type", "device", "diagnosis", "sex", "pain_scale_type"]:
        if column in frame.columns:
            categorical_cardinality[column] = int(frame[column].astype("string").nunique(dropna=True))
    return {
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "by_dataset": by_dataset.reset_index().to_dict(orient="records"),
        "label_regimes": label_regimes.to_dict(orient="records"),
        "categorical_cardinality": categorical_cardinality,
        "metadata_policy": {
            "included_by_default": sorted(BASIC_METADATA_COLUMNS),
            "excluded_from_self_supervised_features": sorted(ID_COLUMNS | LABEL_COLUMNS),
            "note": "subject_id and session_id are retained in outputs for grouping/audit but excluded as model features.",
        },
        "weight_summary": weight_summary(frame),
    }


def write_markdown_report(
    path: Path,
    config: ExplorationConfig,
    audit: dict[str, Any],
    reconstruction: pd.DataFrame,
    next_window: pd.DataFrame,
    contrastive: dict[str, Any],
    interconnection: pd.DataFrame,
) -> None:
    def metric_table(frame: pd.DataFrame) -> str:
        if frame.empty:
            return "_No rows._\n"
        cols = [
            "task",
            "target_column",
            "status",
            "rows",
            "test_mae",
            "weighted_test_mae",
            "baseline_mae",
            "weighted_baseline_mae",
            "mae_improvement_vs_mean",
            "weighted_mae_improvement_vs_mean",
            "test_r2",
        ]
        available = [column for column in cols if column in frame.columns]
        return frame[available].to_markdown(index=False)

    top_inter = interconnection.head(20).to_markdown(index=False) if not interconnection.empty else "_No rows._"
    report = f"""# Exploratory Self-Supervised Report

Date: 2026-04-29

Input: `{config.input_path}`

Output: `{config.output_dir}`

## What Ran

- Sensor-block reconstruction: predict one sensor block's mean feature from other sensor blocks plus allowed metadata.
- Next-window prediction: predict selected sensor means one horizon ahead from the current window.
- Contrastive-style probe: create two augmented views with sensor-block dropout/noise, project with PCA, and compare positive pairs to random negatives.
- Sensor interconnection audit: cross-block absolute correlation scan.

## Data Audit

Rows: {audit["rows"]}

Columns: {audit["columns"]}

Label regimes:

{pd.DataFrame(audit["label_regimes"]).to_markdown(index=False)}

Metadata policy: subject/session IDs are excluded from model features; basic dataset/protocol metadata is included unless `--metadata none` is used.

Balancing policy: `{config.balance_mode}`. The output includes `ssl_weight`, and weighted metrics are reported so denser datasets/sessions do not silently dominate interpretation.

## Reconstruction Metrics

{metric_table(reconstruction)}

## Next-Window Metrics

{metric_table(next_window)}

## Contrastive Probe

```json
{json.dumps(contrastive, indent=2, sort_keys=True)}
```

Interpretation: higher positive-vs-random cosine separation means augmented views of the same physiological window stay closer than unrelated windows. Top-1 same-row/session/subject rates show whether the representation is mostly instance-level, session-level, or dataset/protocol-level.

## Strongest Cross-Block Associations

{top_inter}

## Notes

- This is exploratory self-supervision, not a final pain model.
- Direct pain labels are excluded from self-supervised inputs and are only retained for auditing embeddings/results.
- Reconstruction residuals are useful candidate features for later supervised pain models.
- If metadata-conditioned metrics are too high, rerun with `--metadata none` to check whether dataset/protocol shortcuts are driving the result.
"""
    path.write_text(report, encoding="utf-8")


def run_exploration(config: ExplorationConfig) -> dict[str, Any]:
    input_path = Path(config.input_path)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_parquet(input_path)
    frame = frame.reset_index(drop=True)
    frame.insert(0, "row_id", np.arange(len(frame), dtype=np.int64))
    frame = add_balance_weights(frame, config.balance_mode)

    audit = label_and_metadata_audit(frame)
    write_json(output_dir / "metadata_label_audit.json", audit)

    interconnection = sensor_interconnection(frame)
    interconnection.to_csv(output_dir / "sensor_interconnection.csv", index=False)

    reconstruction_rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    for block, target_col in RECONSTRUCTION_TARGETS.items():
        if target_col not in frame.columns:
            continue
        features = feature_columns(frame, excluded_block=block, metadata=config.metadata)
        metrics, predictions = run_regression_task(
            frame,
            target_col=target_col,
            feature_cols=features,
            task_name=f"reconstruct_{block}",
            config=config,
        )
        reconstruction_rows.append(metrics)
        if predictions is not None:
            prediction_frames.append(predictions)
    reconstruction = pd.DataFrame(reconstruction_rows)
    reconstruction.to_csv(output_dir / "reconstruction_metrics.csv", index=False)
    if prediction_frames:
        pd.concat(prediction_frames, ignore_index=True).to_parquet(
            output_dir / "reconstruction_predictions.parquet",
            compression="zstd",
            index=False,
        )

    future_frame = add_future_targets(frame, config.next_horizon_seconds)
    next_rows: list[dict[str, Any]] = []
    next_prediction_frames: list[pd.DataFrame] = []
    for target_col in NEXT_WINDOW_TARGETS:
        future_col = f"{target_col}__future"
        if future_col not in future_frame.columns:
            continue
        features = feature_columns(future_frame, metadata=config.metadata)
        metrics, predictions = run_regression_task(
            future_frame,
            target_col=future_col,
            feature_cols=features,
            task_name=f"next_window_{target_col}",
            config=config,
        )
        next_rows.append(metrics)
        if predictions is not None:
            predictions["target_column"] = future_col
            next_prediction_frames.append(predictions)
    next_window = pd.DataFrame(next_rows)
    next_window.to_csv(output_dir / "next_window_metrics.csv", index=False)
    if next_prediction_frames:
        pd.concat(next_prediction_frames, ignore_index=True).to_parquet(
            output_dir / "next_window_predictions.parquet",
            compression="zstd",
            index=False,
        )

    contrastive, embeddings = run_contrastive_probe(frame, config)
    write_json(output_dir / "contrastive_metrics.json", contrastive)
    if not embeddings.empty:
        embeddings.to_parquet(output_dir / "contrastive_embeddings.parquet", compression="zstd", index=False)

    manifest = {
        "config": asdict(config),
        "audit": audit,
        "outputs": {
            "metadata_label_audit": str(output_dir / "metadata_label_audit.json"),
            "sensor_interconnection": str(output_dir / "sensor_interconnection.csv"),
            "reconstruction_metrics": str(output_dir / "reconstruction_metrics.csv"),
            "reconstruction_predictions": str(output_dir / "reconstruction_predictions.parquet"),
            "next_window_metrics": str(output_dir / "next_window_metrics.csv"),
            "next_window_predictions": str(output_dir / "next_window_predictions.parquet"),
            "contrastive_metrics": str(output_dir / "contrastive_metrics.json"),
            "contrastive_embeddings": str(output_dir / "contrastive_embeddings.parquet"),
            "report": str(output_dir / "SELF_SUPERVISED_EXPLORATION_REPORT.md"),
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    write_markdown_report(
        output_dir / "SELF_SUPERVISED_EXPLORATION_REPORT.md",
        config,
        audit,
        reconstruction,
        next_window,
        contrastive,
        interconnection,
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run exploratory self-supervised probes on feeder windows.")
    parser.add_argument("--input", default=str(DEFAULT_WINDOW_TABLE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--metadata", choices=["basic", "none"], default="basic")
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--min-rows", type=int, default=500)
    parser.add_argument("--max-model-rows", type=int, default=None)
    parser.add_argument("--model-iterations", type=int, default=80)
    parser.add_argument("--next-horizon-seconds", type=float, default=1.0)
    parser.add_argument("--contrastive-sample", type=int, default=8000)
    parser.add_argument("--contrastive-components", type=int, default=16)
    parser.add_argument("--sensor-dropout-probability", type=float, default=0.35)
    parser.add_argument("--noise-scale", type=float, default=0.02)
    parser.add_argument("--balance-mode", choices=["none", "dataset", "dataset_session"], default="dataset_session")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = ExplorationConfig(
        input_path=args.input,
        output_dir=args.output,
        metadata=args.metadata,
        random_state=args.random_state,
        min_rows=args.min_rows,
        max_model_rows=args.max_model_rows,
        model_iterations=args.model_iterations,
        next_horizon_seconds=args.next_horizon_seconds,
        contrastive_sample=args.contrastive_sample,
        contrastive_components=args.contrastive_components,
        sensor_dropout_probability=args.sensor_dropout_probability,
        noise_scale=args.noise_scale,
        balance_mode=args.balance_mode,
    )
    manifest = run_exploration(config)
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
