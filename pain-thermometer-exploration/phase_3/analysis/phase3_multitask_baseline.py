#!/usr/bin/env python3
"""Run Phase 3 lightweight multi-task baselines.

The goal is not to maximize a single pooled score. It is to make direct pain,
stress/proxy, activity, baseline, metadata, LOSO, and leave-dataset behavior
visible with models that are still simple enough to debug.
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


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
DEFAULT_INPUT = WORKSPACE_ROOT / "_normalized" / "phase3" / "target_hz=1" / "window_features.parquet"
DEFAULT_OUTPUT = WORKSPACE_ROOT / "_normalized" / "phase3" / "target_hz=1" / "baselines"

TARGET_PREFIXES = ("target_",)
ID_COLUMNS = {
    "phase3_window_id",
    "original_all_window_id",
    "subject_id",
    "session_id",
    "phase3_eval_group",
    "baseline_anchor_id",
}
LEAKY_COLUMNS = {
    "window_start_s",
    "window_end_s",
    "source_archive",
    "source_member",
    "source_table",
    "phase3_source_table",
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
    "baseline_missing",
}
METADATA_COLUMNS = {
    "dataset_id",
    "source_family",
    "collection_protocol",
    "label_family",
    "pain_label_regime",
    "condition",
    "record_type",
    "device",
    "diagnosis",
    "sex",
    "age",
    "pain_scale_type",
    "source_modality",
    "source_dataset",
    "aux_state_label",
    "aux_stress_label",
    "proxy_label",
    "pain_type",
    "activity_status",
    "window_sampling",
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
    "sensors_plus_state": {"sensors": tuple(SENSOR_PREFIXES), "state": True, "metadata": False},
    "apple_watch_like": {
        "sensors": ("acc", "gyro", "bvp", "hr", "ibi", "ecg", "temperature", "spo2"),
        "state": True,
        "metadata": False,
    },
    "e4_like": {"sensors": ("acc", "bvp", "eda", "temperature", "hr", "ibi"), "state": True, "metadata": False},
    "autonomic_core": {
        "sensors": ("bvp", "hr", "ibi", "ecg", "eda", "temperature", "respiration"),
        "state": True,
        "metadata": False,
    },
    "hr_eda_stress": {"sensors": ("hr", "eda"), "state": False, "metadata": False},
    "motion_only": {"sensors": ("acc", "gyro", "steps"), "state": True, "metadata": False},
    "metadata_probe": {"sensors": (), "state": True, "metadata": True},
}
FAST_FEATURES = {
    "pain": ("sensors_plus_state", "apple_watch_like", "metadata_probe"),
    "stress": ("hr_eda_stress", "autonomic_core", "metadata_probe"),
    "baseline": ("sensors_plus_state", "apple_watch_like", "metadata_probe"),
}
FULL_FEATURES = {
    "pain": ("sensors_plus_state", "apple_watch_like", "e4_like", "autonomic_core", "motion_only", "metadata_probe"),
    "stress": ("hr_eda_stress", "e4_like", "autonomic_core", "sensors_plus_state", "metadata_probe"),
    "baseline": ("sensors_plus_state", "apple_watch_like", "e4_like", "metadata_probe"),
}


@dataclass(frozen=True)
class Phase3Config:
    input_path: str
    output_dir: str
    random_state: int = 42
    model_iterations: int = 80
    min_train_rows: int = 400
    min_test_rows: int = 80
    max_aux_rows: int = 120_000
    max_loso_subjects: int = 4
    feature_mode: str = "fast"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def sensor_columns(frame: pd.DataFrame, sensors: tuple[str, ...]) -> list[str]:
    prefixes = tuple(prefix for sensor in sensors for prefix in SENSOR_PREFIXES[sensor])
    return [
        column
        for column in frame.columns
        if column.startswith(prefixes)
        and not column.startswith(TARGET_PREFIXES)
        and column not in ID_COLUMNS
        and column not in LEAKY_COLUMNS
    ]


def feature_columns(frame: pd.DataFrame, feature_set: str) -> list[str]:
    spec = FEATURE_SETS[feature_set]
    selected: list[str] = []
    selected.extend(sensor_columns(frame, tuple(spec["sensors"])))
    if spec["state"]:
        selected.extend(column for column in STATE_COLUMNS if column in frame.columns)
    if spec["metadata"]:
        selected.extend(column for column in METADATA_COLUMNS if column in frame.columns)
    excluded = set(ID_COLUMNS) | set(LEAKY_COLUMNS)
    excluded.update(column for column in frame.columns if column.startswith(TARGET_PREFIXES))
    out: list[str] = []
    seen: set[str] = set()
    for column in selected:
        if column in seen or column in excluded or column not in frame.columns:
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


def clean_feature_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame[columns].copy()
    numeric, categorical = split_feature_types(out, columns)
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    for column in categorical:
        out[column] = out[column].astype("object").where(out[column].notna(), "__missing__").astype(str)
    return out


def make_preprocessor(frame: pd.DataFrame, columns: list[str]) -> ColumnTransformer:
    numeric, categorical = split_feature_types(frame, columns)
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(("num", SimpleImputer(strategy="median", add_indicator=True), numeric))
    if categorical:
        transformers.append(
            (
                "cat",
                Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", one_hot_encoder())]),
                categorical,
            )
        )
    return ColumnTransformer(transformers=transformers, remainder="drop", sparse_threshold=0.0)


def make_classifier(config: Phase3Config) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=config.model_iterations,
        learning_rate=0.05,
        l2_regularization=0.08,
        max_leaf_nodes=31,
        early_stopping=True,
        random_state=config.random_state,
    )


def make_regressor(config: Phase3Config) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=config.model_iterations,
        learning_rate=0.05,
        l2_regularization=0.08,
        max_leaf_nodes=31,
        early_stopping=True,
        random_state=config.random_state,
    )


def task_weights(frame: pd.DataFrame, target: str, confidence_weighted: bool = False) -> np.ndarray:
    dataset_counts = frame.groupby("dataset_id", dropna=False)["dataset_id"].transform("count").astype(float)
    dataset_count = max(float(frame["dataset_id"].nunique(dropna=False)), 1.0)
    weights = len(frame) / (dataset_count * dataset_counts)
    y = pd.to_numeric(frame[target], errors="coerce")
    if y.dropna().nunique() <= 8:
        class_counts = y.groupby(y).transform("count").astype(float)
        class_count = max(float(y.nunique(dropna=True)), 1.0)
        weights = weights * (len(frame) / (class_count * class_counts)).fillna(1.0)
    if confidence_weighted and "target_confidence" in frame.columns:
        confidence = pd.to_numeric(frame["target_confidence"], errors="coerce").fillna(1.0).clip(lower=0.05)
        weights = weights * confidence
    mean = float(weights.mean())
    return (weights / mean if mean > 0 else weights).to_numpy(dtype=float)


def cap_frame(frame: pd.DataFrame, max_rows: int, seed: int) -> pd.DataFrame:
    if len(frame) <= max_rows:
        return frame
    strata_cols = [column for column in ("dataset_id", "source_dataset", "label_family") if column in frame.columns]
    if not strata_cols:
        return frame.sample(max_rows, random_state=seed)
    pieces = []
    per_stratum = max(max_rows // max(int(frame.groupby(strata_cols, dropna=False).ngroups), 1), 100)
    for _, group in frame.groupby(strata_cols, dropna=False):
        pieces.append(group.sample(min(len(group), per_stratum), random_state=seed))
    out = pd.concat(pieces, ignore_index=False)
    if len(out) > max_rows:
        out = out.sample(max_rows, random_state=seed)
    return out


def grouped_split(frame: pd.DataFrame, seed: int, group_col: str = "phase3_eval_group", test_size: float = 0.25) -> tuple[pd.DataFrame, pd.DataFrame]:
    groups = frame[group_col].astype("string").fillna("missing")
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(splitter.split(frame, groups=groups))
    return frame.iloc[train_idx].copy(), frame.iloc[test_idx].copy()


def evaluate_classifier(y_true: np.ndarray, score: np.ndarray) -> dict[str, Any]:
    pred = (score >= 0.5).astype(int)
    return {
        "prevalence": float(np.mean(y_true)),
        "roc_auc": float(roc_auc_score(y_true, score)) if np.unique(y_true).size > 1 else None,
        "average_precision": float(average_precision_score(y_true, score)) if np.unique(y_true).size > 1 else None,
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
    }


def evaluate_regression(y_true: np.ndarray, y_pred: np.ndarray, y_train: np.ndarray) -> dict[str, Any]:
    baseline = np.full_like(y_true, float(np.nanmean(y_train)), dtype=float)
    mae = float(mean_absolute_error(y_true, y_pred))
    baseline_mae = float(mean_absolute_error(y_true, baseline))
    return {
        "mae": mae,
        "baseline_mae": baseline_mae,
        "mae_improvement_vs_train_mean": float(1 - mae / baseline_mae) if baseline_mae > 0 else None,
        "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)) if np.unique(y_true).size > 1 else None,
    }


def result_header(task: str, split: str, feature_set: str, train: pd.DataFrame, test: pd.DataFrame, columns: list[str], heldout: str | None = None) -> dict[str, Any]:
    return {
        "task": task,
        "split": split,
        "feature_set": feature_set,
        "heldout": heldout,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "features": int(len(columns)),
        "train_datasets": ",".join(sorted(train["dataset_id"].astype(str).unique())),
        "test_datasets": ",".join(sorted(test["dataset_id"].astype(str).unique())),
        "train_subjects": int(train["phase3_eval_group"].nunique()),
        "test_subjects": int(test["phase3_eval_group"].nunique()),
    }


def run_classifier_split(
    task: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_set: str,
    target: str,
    split: str,
    config: Phase3Config,
    heldout: str | None = None,
    confidence_weighted: bool = False,
) -> dict[str, Any]:
    columns = [column for column in feature_columns(train, feature_set) if column in test.columns]
    header = result_header(task, split, feature_set, train, test, columns, heldout)
    if len(train) < config.min_train_rows or len(test) < config.min_test_rows or not columns:
        return {**header, "status": "skipped", "reason": "too few rows or no features"}
    if train[target].nunique() < 2 or test[target].nunique() < 2:
        return {**header, "status": "skipped", "reason": "target has fewer than two classes"}
    train = cap_frame(train, config.max_aux_rows, config.random_state) if len(train) > config.max_aux_rows else train
    x_train = clean_feature_frame(train, columns)
    x_test = clean_feature_frame(test, columns)
    model = Pipeline([("prep", make_preprocessor(x_train, columns)), ("model", make_classifier(config))])
    model.fit(x_train, train[target].astype(int), model__sample_weight=task_weights(train, target, confidence_weighted))
    score = model.predict_proba(x_test)[:, 1]
    return {**header, "status": "ok", **evaluate_classifier(test[target].astype(int).to_numpy(), score)}


def run_regression_split(
    task: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_set: str,
    target: str,
    split: str,
    config: Phase3Config,
    heldout: str | None = None,
) -> dict[str, Any]:
    columns = [column for column in feature_columns(train, feature_set) if column in test.columns]
    header = result_header(task, split, feature_set, train, test, columns, heldout)
    if len(train) < config.min_train_rows or len(test) < config.min_test_rows or not columns:
        return {**header, "status": "skipped", "reason": "too few rows or no features"}
    if pd.to_numeric(train[target], errors="coerce").nunique() < 2:
        return {**header, "status": "skipped", "reason": "target has fewer than two values"}
    x_train = clean_feature_frame(train, columns)
    x_test = clean_feature_frame(test, columns)
    model = Pipeline([("prep", make_preprocessor(x_train, columns)), ("model", make_regressor(config))])
    y_train = train[target].astype(float)
    model.fit(x_train, y_train, model__sample_weight=task_weights(train, target, confidence_weighted=True))
    pred = model.predict(x_test)
    return {**header, "status": "ok", **evaluate_regression(test[target].astype(float).to_numpy(), pred, y_train.to_numpy())}


def selected_loso_subjects(frame: pd.DataFrame, max_subjects: int) -> list[str]:
    summary = (
        frame.groupby("phase3_eval_group")
        .agg(rows=("phase3_eval_group", "size"), mean_pain=("target_pain_nrs_0_10", "mean"), max_pain=("target_pain_nrs_0_10", "max"))
        .reset_index()
    )
    summary = summary.loc[summary["rows"] >= 80].sort_values(["mean_pain", "rows"], ascending=[True, False])
    if len(summary) <= max_subjects:
        return summary["phase3_eval_group"].astype(str).tolist()
    positions = np.linspace(0, len(summary) - 1, max_subjects).round().astype(int)
    return summary.iloc[positions]["phase3_eval_group"].astype(str).tolist()


def feature_sets_for(config: Phase3Config, family: str) -> tuple[str, ...]:
    return (FULL_FEATURES if config.feature_mode == "full" else FAST_FEATURES)[family]


def run_phase3(config: Phase3Config) -> dict[str, Any]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(config.input_path).reset_index(drop=True)
    rows: list[dict[str, Any]] = []

    direct = frame.loc[frame["label_family"].eq("direct_pain") & frame["target_pain_nrs_0_10"].notna()].copy()
    direct["pain_high_4_plus"] = (direct["target_pain_nrs_0_10"].astype(float) >= 4).astype(int)
    direct["pain_nonzero"] = (direct["target_pain_nrs_0_10"].astype(float) > 0).astype(int)
    train, test = grouped_split(direct, config.random_state)
    for feature_set in feature_sets_for(config, "pain"):
        rows.append(run_regression_split("pain_nrs_regression", train, test, feature_set, "target_pain_nrs_0_10", "direct_pain_group_holdout", config))
        rows.append(run_classifier_split("pain_high_4_plus", train, test, feature_set, "pain_high_4_plus", "direct_pain_group_holdout", config, confidence_weighted=True))
        rows.append(run_classifier_split("pain_nonzero", train, test, feature_set, "pain_nonzero", "direct_pain_group_holdout", config, confidence_weighted=True))

    for dataset_id in sorted(direct["dataset_id"].dropna().unique()):
        test = direct.loc[direct["dataset_id"].eq(dataset_id)].copy()
        train = direct.loc[~direct["dataset_id"].eq(dataset_id)].copy()
        for feature_set in feature_sets_for(config, "pain"):
            rows.append(run_regression_split("pain_nrs_regression", train, test, feature_set, "target_pain_nrs_0_10", "leave_direct_pain_dataset_out", config, str(dataset_id)))
            rows.append(run_classifier_split("pain_high_4_plus", train, test, feature_set, "pain_high_4_plus", "leave_direct_pain_dataset_out", config, str(dataset_id), True))

    for dataset_id, dataset_frame in direct.groupby("dataset_id", sort=True):
        for subject_group in selected_loso_subjects(dataset_frame, config.max_loso_subjects):
            test = dataset_frame.loc[dataset_frame["phase3_eval_group"].eq(subject_group)].copy()
            train = dataset_frame.loc[~dataset_frame["phase3_eval_group"].eq(subject_group)].copy()
            for feature_set in ("sensors_plus_state", "apple_watch_like", "metadata_probe"):
                rows.append(run_regression_split("pain_nrs_regression", train, test, feature_set, "target_pain_nrs_0_10", "within_dataset_loso", config, f"{dataset_id}:{subject_group}"))
                rows.append(run_classifier_split("pain_high_4_plus", train, test, feature_set, "pain_high_4_plus", "within_dataset_loso", config, f"{dataset_id}:{subject_group}", True))

    stress = frame.loc[pd.to_numeric(frame["target_stress_binary"], errors="coerce").notna()].copy()
    stress["target_stress_binary"] = stress["target_stress_binary"].astype(int)
    train, test = grouped_split(stress, config.random_state)
    for feature_set in feature_sets_for(config, "stress"):
        rows.append(run_classifier_split("stress_binary", train, test, feature_set, "target_stress_binary", "stress_group_holdout", config))
    for source in sorted(stress["source_dataset"].dropna().astype(str).unique()):
        test = stress.loc[stress["source_dataset"].astype(str).eq(source)].copy()
        train = stress.loc[~stress["source_dataset"].astype(str).eq(source)].copy()
        for feature_set in feature_sets_for(config, "stress"):
            rows.append(run_classifier_split("stress_binary", train, test, feature_set, "target_stress_binary", "leave_stress_source_out", config, source))

    baseline = frame.loc[pd.to_numeric(frame["target_baseline_binary"], errors="coerce").notna()].copy()
    baseline["target_baseline_binary"] = baseline["target_baseline_binary"].astype(int)
    train, test = grouped_split(baseline, config.random_state)
    for feature_set in feature_sets_for(config, "baseline"):
        rows.append(run_classifier_split("baseline_state_binary", train, test, feature_set, "target_baseline_binary", "baseline_group_holdout", config))

    metrics = pd.DataFrame(rows)
    metrics.to_csv(output_dir / "phase3_metrics.csv", index=False)
    write_markdown_report(output_dir / "PHASE_3_BASELINE_REPORT.md", config, frame, metrics)
    manifest = {
        "config": asdict(config),
        "rows": int(len(frame)),
        "direct_pain_rows": int(len(direct)),
        "stress_rows": int(len(stress)),
        "baseline_rows": int(len(baseline)),
        "outputs": {
            "metrics": str(output_dir / "phase3_metrics.csv"),
            "report": str(output_dir / "PHASE_3_BASELINE_REPORT.md"),
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def write_markdown_report(path: Path, config: Phase3Config, frame: pd.DataFrame, metrics: pd.DataFrame) -> None:
    ok = metrics.loc[metrics["status"].eq("ok")].copy() if not metrics.empty else pd.DataFrame()
    audit = (
        frame.groupby(["label_family", "dataset_id"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values(["label_family", "rows"], ascending=[True, False])
    )

    def table(task: str, split: str, cols: list[str], n: int = 40) -> str:
        if ok.empty:
            return "_No successful rows._"
        part = ok.loc[ok["task"].eq(task) & ok["split"].eq(split)].copy()
        if part.empty:
            return "_No successful rows._"
        available = [column for column in cols if column in part.columns]
        return part[available].head(n).to_markdown(index=False)

    report = f"""# Phase 3 Baseline Report

Input: `{config.input_path}`

Rows: {len(frame)}

## Label Family Coverage

{audit.to_markdown(index=False)}

## Direct Pain Group-Holdout

{table("pain_high_4_plus", "direct_pain_group_holdout", ["feature_set", "test_rows", "features", "prevalence", "roc_auc", "average_precision", "balanced_accuracy", "f1"])}

## Direct Pain Regression

{table("pain_nrs_regression", "direct_pain_group_holdout", ["feature_set", "test_rows", "features", "mae", "baseline_mae", "mae_improvement_vs_train_mean", "r2"])}

## Leave Direct Pain Dataset Out

{table("pain_high_4_plus", "leave_direct_pain_dataset_out", ["heldout", "feature_set", "test_rows", "prevalence", "roc_auc", "average_precision", "balanced_accuracy"], n=60)}

## Within-Dataset LOSO Pain High-Pain Classification

{table("pain_high_4_plus", "within_dataset_loso", ["heldout", "feature_set", "test_rows", "prevalence", "roc_auc", "average_precision", "balanced_accuracy"], n=80)}

## Within-Dataset LOSO Pain Regression

{table("pain_nrs_regression", "within_dataset_loso", ["heldout", "feature_set", "test_rows", "mae", "baseline_mae", "mae_improvement_vs_train_mean", "r2"], n=80)}

## Stress Auxiliary Source Transfer

{table("stress_binary", "leave_stress_source_out", ["heldout", "feature_set", "test_rows", "prevalence", "roc_auc", "average_precision", "balanced_accuracy"], n=80)}

## Baseline-State Probe

{table("baseline_state_binary", "baseline_group_holdout", ["feature_set", "test_rows", "prevalence", "roc_auc", "average_precision", "balanced_accuracy"])}

## Interpretation Rules

- `metadata_probe` is a leakage/protocol diagnostic, not a deployment model.
- Stress/proxy rows train only the stress/state task, never the direct pain task.
- LOSO rows are selected across each dataset's subject pain distribution to give a fast early check before a full exhaustive LOSO run.
- Leave-dataset-out direct-pain results are the primary cross-protocol integrity check.
"""
    path.write_text(report, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 3 multi-task lightweight baselines.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--model-iterations", type=int, default=80)
    parser.add_argument("--min-train-rows", type=int, default=400)
    parser.add_argument("--min-test-rows", type=int, default=80)
    parser.add_argument("--max-aux-rows", type=int, default=120000)
    parser.add_argument("--max-loso-subjects", type=int, default=4)
    parser.add_argument("--feature-mode", choices=["fast", "full"], default="fast")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = Phase3Config(
        input_path=args.input,
        output_dir=args.output,
        random_state=args.random_state,
        model_iterations=args.model_iterations,
        min_train_rows=args.min_train_rows,
        min_test_rows=args.min_test_rows,
        max_aux_rows=args.max_aux_rows,
        max_loso_subjects=args.max_loso_subjects,
        feature_mode=args.feature_mode,
    )
    print(json.dumps(run_phase3(config), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
