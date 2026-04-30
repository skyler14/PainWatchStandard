#!/usr/bin/env python3
"""First-pass supervised pain prediction baselines.

This script intentionally uses lightweight sklearn models. It answers whether
the current window features have any predictive signal for direct pain labels,
while making dataset/subject leakage visible through split design.
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
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "window_features.parquet"
DEFAULT_STATE_ATLAS = (
    ROOT
    / "_normalized"
    / "window_features_all"
    / "target_hz=1"
    / "state_atlas"
    / "baseline_state_assignments.parquet"
)
DEFAULT_OUTPUT = ROOT / "_normalized" / "supervised" / "first_pass_pain"

TARGET_COLUMNS = {
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

ID_COLUMNS = {
    "subject_id",
    "session_id",
    "all_window_id",
}

LEAKY_COLUMNS = {
    "window_start_s",
    "window_end_s",
    "source_archive",
    "source_member",
    "source_table",
}

LIMITED_METADATA = {
    "dataset_id",
    "condition",
    "record_type",
    "device",
    "diagnosis",
    "sex",
    "age",
    "pain_scale_type",
    "source_modality",
    "activity_status",
    "aux_state_label",
    "proxy_label",
    "pain_type",
    "window_sampling",
}

STATE_COLUMNS = {
    "baseline_candidate",
    "baseline_anchor_available",
    "baseline_feature_count",
    "baseline_abs_delta_mean",
    "baseline_abs_delta_max",
    "baseline_l2_delta",
    "baseline_state_bin",
    "state_cluster_id",
}

SENSOR_PREFIXES = {
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
    "bp": ("bp_systolic__", "bp_diastolic__"),
    "spo2": ("spo2__",),
    "steps": ("steps__",),
    "eeg": (
        "eeg_delta__",
        "eeg_theta__",
        "eeg_alpha1__",
        "eeg_alpha2__",
        "eeg_beta1__",
        "eeg_beta2__",
        "eeg_gamma1__",
        "eeg_gamma2__",
        "eeg_attention__",
        "eeg_meditation__",
    ),
}

FEATURE_SETS: dict[str, dict[str, Any]] = {
    "sensors_only": {"sensors": tuple(SENSOR_PREFIXES), "state": False, "metadata": False},
    "sensors_plus_state": {"sensors": tuple(SENSOR_PREFIXES), "state": True, "metadata": False},
    "e4_like": {"sensors": ("acc", "bvp", "eda", "temperature", "hr", "ibi"), "state": True, "metadata": False},
    "apple_watch_like": {
        "sensors": ("acc", "gyro", "bvp", "hr", "ibi", "ecg", "temperature", "spo2"),
        "state": True,
        "metadata": False,
    },
    "autonomic_core": {
        "sensors": ("bvp", "hr", "ibi", "ecg", "eda", "temperature", "respiration"),
        "state": True,
        "metadata": False,
    },
    "motion_only": {"sensors": ("acc", "gyro", "steps"), "state": True, "metadata": False},
    "metadata_probe": {"sensors": (), "state": True, "metadata": True},
    "sensors_plus_metadata": {"sensors": tuple(SENSOR_PREFIXES), "state": True, "metadata": True},
}


@dataclass(frozen=True)
class SupervisedConfig:
    input_path: str
    state_atlas_path: str
    output_dir: str
    random_state: int = 42
    model_iterations: int = 180
    min_train_rows: int = 500
    min_test_rows: int = 100
    high_pain_threshold: float = 4.0


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def load_labeled_frame(config: SupervisedConfig) -> pd.DataFrame:
    frame = pd.read_parquet(config.input_path).reset_index(drop=True)
    frame.insert(0, "all_window_id", np.arange(len(frame), dtype=np.int64))
    if Path(config.state_atlas_path).exists():
        atlas_cols = ["all_window_id", *sorted(STATE_COLUMNS)]
        atlas = pd.read_parquet(config.state_atlas_path, columns=atlas_cols)
        frame = frame.merge(atlas, on="all_window_id", how="left", suffixes=("", "_atlas"))
    target = pd.to_numeric(frame["target_pain_nrs_0_10"], errors="coerce")
    labeled = frame.loc[target.notna()].copy()
    labeled["target_pain_nrs_0_10"] = target.loc[labeled.index].astype(float)
    labeled["target_high_pain_4_plus"] = (labeled["target_pain_nrs_0_10"] >= config.high_pain_threshold).astype(int)
    labeled["target_nonzero_pain"] = (labeled["target_pain_nrs_0_10"] > 0).astype(int)
    labeled["supervised_weight"] = supervised_weights(labeled)
    return labeled.reset_index(drop=True)


def supervised_weights(frame: pd.DataFrame) -> np.ndarray:
    dataset_counts = frame.groupby("dataset_id", dropna=False)["dataset_id"].transform("count").astype(float)
    dataset_count = max(float(frame["dataset_id"].nunique(dropna=False)), 1.0)
    weights = len(frame) / (dataset_count * dataset_counts)
    confidence = pd.to_numeric(frame.get("target_confidence", pd.Series(1.0, index=frame.index)), errors="coerce").fillna(1.0)
    weights = weights * confidence.astype(float)
    mean = float(weights.mean())
    if mean > 0:
        weights = weights / mean
    return weights.to_numpy(dtype=float)


def sensor_columns(frame: pd.DataFrame, sensors: tuple[str, ...]) -> list[str]:
    prefixes: tuple[str, ...] = tuple(prefix for sensor in sensors for prefix in SENSOR_PREFIXES[sensor])
    return [
        column
        for column in frame.columns
        if column.startswith(prefixes)
        and column not in TARGET_COLUMNS
        and not column.startswith("target_")
    ]


def feature_columns(frame: pd.DataFrame, feature_set: str) -> list[str]:
    spec = FEATURE_SETS[feature_set]
    selected: list[str] = []
    selected.extend(sensor_columns(frame, tuple(spec["sensors"])))
    if spec["state"]:
        selected.extend(column for column in STATE_COLUMNS if column in frame.columns)
    if spec["metadata"]:
        selected.extend(column for column in LIMITED_METADATA if column in frame.columns)
    excluded = set(TARGET_COLUMNS) | ID_COLUMNS | LEAKY_COLUMNS
    excluded.update(column for column in frame.columns if column.startswith("target_"))
    out = []
    seen = set()
    for column in selected:
        if column in excluded or column in seen or column not in frame.columns:
            continue
        if frame[column].notna().any():
            out.append(column)
            seen.add(column)
    return out


def split_feature_types(frame: pd.DataFrame, columns: list[str]) -> tuple[list[str], list[str]]:
    numeric = [
        column
        for column in columns
        if pd.api.types.is_numeric_dtype(frame[column]) or pd.api.types.is_bool_dtype(frame[column])
    ]
    categorical = [column for column in columns if column not in numeric]
    return numeric, categorical


def make_preprocessor(frame: pd.DataFrame, columns: list[str]) -> ColumnTransformer:
    numeric, categorical = split_feature_types(frame, columns)
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(("num", SimpleImputer(strategy="median", add_indicator=True), numeric))
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


def make_regressor(config: SupervisedConfig) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=config.model_iterations,
        learning_rate=0.05,
        l2_regularization=0.08,
        max_leaf_nodes=31,
        early_stopping=True,
        random_state=config.random_state,
    )


def make_classifier(config: SupervisedConfig) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=config.model_iterations,
        learning_rate=0.05,
        l2_regularization=0.08,
        max_leaf_nodes=31,
        early_stopping=True,
        random_state=config.random_state,
    )


def group_split(frame: pd.DataFrame, seed: int, test_size: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
    groups = frame["dataset_id"].astype("string") + "::" + frame["subject_id"].astype("string")
    if groups.nunique() < 3:
        raise ValueError("not enough groups for grouped split")
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    return next(splitter.split(frame, groups=groups))


def evaluate_regression(y_true: np.ndarray, y_pred: np.ndarray, y_train: np.ndarray, weights: np.ndarray | None) -> dict[str, Any]:
    baseline = np.full_like(y_true, float(np.nanmean(y_train)), dtype=float)
    mae = float(mean_absolute_error(y_true, y_pred))
    baseline_mae = float(mean_absolute_error(y_true, baseline))
    rmse = float(math.sqrt(mean_squared_error(y_true, y_pred)))
    payload: dict[str, Any] = {
        "mae": mae,
        "baseline_mae": baseline_mae,
        "mae_improvement_vs_train_mean": float(1.0 - mae / baseline_mae) if baseline_mae > 0 else None,
        "rmse": rmse,
        "r2": float(r2_score(y_true, y_pred)) if np.unique(y_true).size > 1 else None,
        "pearson": float(np.corrcoef(y_true, y_pred)[0, 1]) if np.unique(y_true).size > 1 and np.unique(y_pred).size > 1 else None,
    }
    if weights is not None:
        w_mae = float(mean_absolute_error(y_true, y_pred, sample_weight=weights))
        w_base = float(mean_absolute_error(y_true, baseline, sample_weight=weights))
        payload.update(
            {
                "weighted_mae": w_mae,
                "weighted_baseline_mae": w_base,
                "weighted_mae_improvement_vs_train_mean": float(1.0 - w_mae / w_base) if w_base > 0 else None,
            }
        )
    return payload


def evaluate_classifier(y_true: np.ndarray, score: np.ndarray, weights: np.ndarray | None) -> dict[str, Any]:
    pred = (score >= 0.5).astype(int)
    payload: dict[str, Any] = {
        "prevalence": float(np.mean(y_true)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "average_precision": float(average_precision_score(y_true, score)) if np.unique(y_true).size > 1 else None,
        "roc_auc": float(roc_auc_score(y_true, score)) if np.unique(y_true).size > 1 else None,
    }
    if weights is not None:
        payload.update(
            {
                "weighted_accuracy": float(accuracy_score(y_true, pred, sample_weight=weights)),
                "weighted_balanced_accuracy": float(balanced_accuracy_score(y_true, pred, sample_weight=weights)),
                "weighted_f1": float(f1_score(y_true, pred, sample_weight=weights, zero_division=0)),
                "weighted_average_precision": (
                    float(average_precision_score(y_true, score, sample_weight=weights))
                    if np.unique(y_true).size > 1
                    else None
                ),
                "weighted_roc_auc": (
                    float(roc_auc_score(y_true, score, sample_weight=weights))
                    if np.unique(y_true).size > 1
                    else None
                ),
            }
        )
    return payload


def fit_predict_regression(
    train: pd.DataFrame,
    test: pd.DataFrame,
    columns: list[str],
    config: SupervisedConfig,
) -> tuple[dict[str, Any], np.ndarray]:
    model = Pipeline([("prep", make_preprocessor(train, columns)), ("model", make_regressor(config))])
    model.fit(
        train[columns],
        train["target_pain_nrs_0_10"].astype(float),
        model__sample_weight=train["supervised_weight"].astype(float).to_numpy(),
    )
    pred = model.predict(test[columns])
    metrics = evaluate_regression(
        test["target_pain_nrs_0_10"].astype(float).to_numpy(),
        pred,
        train["target_pain_nrs_0_10"].astype(float).to_numpy(),
        test["supervised_weight"].astype(float).to_numpy(),
    )
    return metrics, pred


def fit_predict_classifier(
    train: pd.DataFrame,
    test: pd.DataFrame,
    columns: list[str],
    config: SupervisedConfig,
    target_col: str,
) -> tuple[dict[str, Any], np.ndarray]:
    if train[target_col].nunique() < 2 or test[target_col].nunique() < 2:
        raise ValueError("classifier target has fewer than two classes in train or test")
    model = Pipeline([("prep", make_preprocessor(train, columns)), ("model", make_classifier(config))])
    model.fit(
        train[columns],
        train[target_col].astype(int),
        model__sample_weight=train["supervised_weight"].astype(float).to_numpy(),
    )
    score = model.predict_proba(test[columns])[:, 1]
    metrics = evaluate_classifier(
        test[target_col].astype(int).to_numpy(),
        score,
        test["supervised_weight"].astype(float).to_numpy(),
    )
    return metrics, score


def result_header(
    split_name: str,
    feature_set: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    columns: list[str],
    task: str,
    heldout_dataset: str | None = None,
) -> dict[str, Any]:
    return {
        "split": split_name,
        "feature_set": feature_set,
        "task": task,
        "heldout_dataset": heldout_dataset,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "features": int(len(columns)),
        "train_datasets": ",".join(sorted(train["dataset_id"].astype(str).unique())),
        "test_datasets": ",".join(sorted(test["dataset_id"].astype(str).unique())),
        "train_subjects": int(train["subject_id"].nunique()),
        "test_subjects": int(test["subject_id"].nunique()),
    }


def run_one_split(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_set: str,
    split_name: str,
    config: SupervisedConfig,
    heldout_dataset: str | None = None,
) -> tuple[list[dict[str, Any]], list[pd.DataFrame]]:
    columns = feature_columns(train, feature_set)
    columns = [column for column in columns if column in test.columns and train[column].notna().any()]
    rows: list[dict[str, Any]] = []
    predictions: list[pd.DataFrame] = []
    if len(train) < config.min_train_rows or len(test) < config.min_test_rows or not columns:
        for task in ("regression_nrs", "classification_high_pain_4_plus"):
            rows.append(
                {
                    **result_header(split_name, feature_set, train, test, columns, task, heldout_dataset),
                    "status": "skipped",
                    "reason": "too few rows or no usable features",
                }
            )
        return rows, predictions

    try:
        metrics, pred = fit_predict_regression(train, test, columns, config)
        payload = {
            **result_header(split_name, feature_set, train, test, columns, "regression_nrs", heldout_dataset),
            "status": "ok",
            **metrics,
        }
        rows.append(payload)
        predictions.append(
            prediction_frame(test, split_name, feature_set, "regression_nrs", pred, observed_col="target_pain_nrs_0_10")
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic script should keep running.
        rows.append(
            {
                **result_header(split_name, feature_set, train, test, columns, "regression_nrs", heldout_dataset),
                "status": "failed",
                "reason": str(exc),
            }
        )

    for target_col, task in (
        ("target_high_pain_4_plus", "classification_high_pain_4_plus"),
        ("target_nonzero_pain", "classification_nonzero_pain"),
    ):
        try:
            metrics, score = fit_predict_classifier(train, test, columns, config, target_col)
            rows.append(
                {
                    **result_header(split_name, feature_set, train, test, columns, task, heldout_dataset),
                    "status": "ok",
                    **metrics,
                }
            )
            predictions.append(prediction_frame(test, split_name, feature_set, task, score, observed_col=target_col))
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    **result_header(split_name, feature_set, train, test, columns, task, heldout_dataset),
                    "status": "skipped",
                    "reason": str(exc),
                }
            )
    return rows, predictions


def prediction_frame(
    test: pd.DataFrame,
    split_name: str,
    feature_set: str,
    task: str,
    predicted: np.ndarray,
    observed_col: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "split": split_name,
            "feature_set": feature_set,
            "task": task,
            "dataset_id": test["dataset_id"].to_numpy(),
            "subject_id": test["subject_id"].to_numpy(),
            "session_id": test["session_id"].to_numpy(),
            "window_end_s": test["window_end_s"].to_numpy() if "window_end_s" in test.columns else np.nan,
            "observed": test[observed_col].to_numpy(),
            "predicted": predicted,
            "target_pain_nrs_0_10": test["target_pain_nrs_0_10"].to_numpy(),
            "supervised_weight": test["supervised_weight"].to_numpy(),
        }
    )


def run_analysis(config: SupervisedConfig) -> dict[str, Any]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = load_labeled_frame(config)
    write_json(output_dir / "label_audit.json", label_audit(frame))

    metric_rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    feature_sets = list(FEATURE_SETS)

    train_idx, test_idx = group_split(frame, config.random_state)
    train = frame.iloc[train_idx].copy()
    test = frame.iloc[test_idx].copy()
    for feature_set in feature_sets:
        rows, predictions = run_one_split(train, test, feature_set, "pooled_subject_holdout", config)
        metric_rows.extend(rows)
        prediction_frames.extend(predictions)

    for dataset_id, subset in frame.groupby("dataset_id", sort=True):
        if len(subset) < config.min_train_rows + config.min_test_rows or subset["subject_id"].nunique() < 3:
            continue
        train_idx, test_idx = group_split(subset.reset_index(drop=True), config.random_state)
        train = subset.reset_index(drop=True).iloc[train_idx].copy()
        test = subset.reset_index(drop=True).iloc[test_idx].copy()
        for feature_set in feature_sets:
            rows, predictions = run_one_split(
                train,
                test,
                feature_set,
                f"within_dataset_subject_holdout:{dataset_id}",
                config,
            )
            metric_rows.extend(rows)
            prediction_frames.extend(predictions)

    for heldout in sorted(frame["dataset_id"].dropna().unique()):
        train = frame.loc[frame["dataset_id"] != heldout].copy()
        test = frame.loc[frame["dataset_id"] == heldout].copy()
        for feature_set in feature_sets:
            rows, predictions = run_one_split(
                train,
                test,
                feature_set,
                "leave_dataset_out",
                config,
                heldout_dataset=str(heldout),
            )
            metric_rows.extend(rows)
            prediction_frames.extend(predictions)

    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(output_dir / "supervised_metrics.csv", index=False)
    if prediction_frames:
        pd.concat(prediction_frames, ignore_index=True).to_parquet(
            output_dir / "supervised_predictions.parquet",
            compression="zstd",
            index=False,
        )

    write_markdown_report(output_dir / "SUPERVISED_PAIN_BASELINE_REPORT.md", config, frame, metrics)
    manifest = {
        "config": asdict(config),
        "rows": int(len(frame)),
        "outputs": {
            "label_audit": str(output_dir / "label_audit.json"),
            "metrics": str(output_dir / "supervised_metrics.csv"),
            "predictions": str(output_dir / "supervised_predictions.parquet"),
            "report": str(output_dir / "SUPERVISED_PAIN_BASELINE_REPORT.md"),
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def label_audit(frame: pd.DataFrame) -> dict[str, Any]:
    by_dataset = (
        frame.groupby("dataset_id")
        .agg(
            rows=("dataset_id", "size"),
            subjects=("subject_id", "nunique"),
            sessions=("session_id", "nunique"),
            mean_pain=("target_pain_nrs_0_10", "mean"),
            min_pain=("target_pain_nrs_0_10", "min"),
            max_pain=("target_pain_nrs_0_10", "max"),
            high_pain_rate=("target_high_pain_4_plus", "mean"),
            nonzero_pain_rate=("target_nonzero_pain", "mean"),
            mean_weight=("supervised_weight", "mean"),
            weight_sum=("supervised_weight", "sum"),
        )
        .reset_index()
    )
    return {
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "by_dataset": by_dataset.to_dict(orient="records"),
        "note": "Targets are not perfectly harmonized across datasets; use leave-dataset and within-dataset splits for interpretation.",
    }


def write_markdown_report(path: Path, config: SupervisedConfig, frame: pd.DataFrame, metrics: pd.DataFrame) -> None:
    ok = metrics.loc[metrics["status"] == "ok"].copy() if not metrics.empty else pd.DataFrame()

    def table_for(task: str, split_prefix: str, cols: list[str], n: int = 20) -> str:
        if ok.empty:
            return "_No successful rows._"
        part = ok.loc[ok["task"].eq(task) & ok["split"].astype(str).str.startswith(split_prefix)].copy()
        if part.empty:
            return "_No successful rows._"
        available = [column for column in cols if column in part.columns]
        return part[available].head(n).to_markdown(index=False)

    report = f"""# Supervised Pain Baseline Report

Date: 2026-04-29

Input: `{config.input_path}`

Rows with direct pain targets: {len(frame)}

## Label Coverage

{pd.DataFrame(label_audit(frame)["by_dataset"]).to_markdown(index=False)}

## Important Interpretation Limits

- This is a first-pass predictive-power check, not a deployable pain model.
- Label scales differ by dataset. PainMonit is broad NRS-like, RheumaPain is weak/session-level and low-range in these windows, and PhysioPain watch is 1-5.
- Pooled results can show signal, but leave-dataset-out and within-dataset subject holdout are the integrity checks.
- `metadata_probe` and `sensors_plus_metadata` are leakage diagnostics, not the preferred model for deployment.

## Pooled Subject-Holdout Regression

{table_for("regression_nrs", "pooled_subject_holdout", ["feature_set", "test_rows", "features", "mae", "baseline_mae", "mae_improvement_vs_train_mean", "weighted_mae", "weighted_baseline_mae", "weighted_mae_improvement_vs_train_mean", "r2", "pearson"])}

## Pooled Subject-Holdout High-Pain Classification

{table_for("classification_high_pain_4_plus", "pooled_subject_holdout", ["feature_set", "test_rows", "features", "prevalence", "roc_auc", "average_precision", "balanced_accuracy", "weighted_roc_auc", "weighted_average_precision", "weighted_balanced_accuracy"])}

## Within-Dataset Subject-Holdout Regression

{table_for("regression_nrs", "within_dataset_subject_holdout", ["split", "feature_set", "test_rows", "mae", "baseline_mae", "mae_improvement_vs_train_mean", "weighted_mae_improvement_vs_train_mean", "r2", "pearson"], n=60)}

## Leave-Dataset-Out Regression

{table_for("regression_nrs", "leave_dataset_out", ["heldout_dataset", "feature_set", "test_rows", "mae", "baseline_mae", "mae_improvement_vs_train_mean", "weighted_mae_improvement_vs_train_mean", "r2", "pearson"], n=60)}

## Leave-Dataset-Out High-Pain Classification

{table_for("classification_high_pain_4_plus", "leave_dataset_out", ["heldout_dataset", "feature_set", "test_rows", "prevalence", "roc_auc", "average_precision", "balanced_accuracy", "weighted_roc_auc", "weighted_average_precision", "weighted_balanced_accuracy"], n=60)}
"""
    path.write_text(report, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run first-pass supervised pain prediction baselines.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--state-atlas", default=str(DEFAULT_STATE_ATLAS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--model-iterations", type=int, default=180)
    parser.add_argument("--min-train-rows", type=int, default=500)
    parser.add_argument("--min-test-rows", type=int, default=100)
    parser.add_argument("--high-pain-threshold", type=float, default=4.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = SupervisedConfig(
        input_path=args.input,
        state_atlas_path=args.state_atlas,
        output_dir=args.output,
        random_state=args.random_state,
        model_iterations=args.model_iterations,
        min_train_rows=args.min_train_rows,
        min_test_rows=args.min_test_rows,
        high_pain_threshold=args.high_pain_threshold,
    )
    manifest = run_analysis(config)
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
