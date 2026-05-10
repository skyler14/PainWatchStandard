#!/usr/bin/env python3
"""Train dropout-tolerant portable pain trigger ensembles.

This keeps the nine Core ML-convertible candidate families from the sweep and
trains them as soft-voting ensembles over two feature views:

- `full_sensor`: all numeric sensor/state features that can appear in Phase 3.
- `watch_friendly`: the Apple Watch-like numeric subset.

Training simulates real device dropouts by adding masked copies of the training
rows where whole sensor blocks are set missing and their `__present`,
`__valid_count`, and `__valid_frac` features are forced to zero when present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC, SVC
from sklearn.tree import DecisionTreeClassifier


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "_normalized" / "phase3" / "target_hz=1" / "window_features.parquet"
DEFAULT_OUTPUT = ROOT / "inference_flow" / "models" / "pain-thermometer-dropout-ensemble"

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
WATCH_SENSOR_BLOCKS = ("acc", "gyro", "bvp", "hr", "ibi", "ecg", "temperature", "spo2")
FULL_SENSOR_BLOCKS = tuple(SENSOR_PREFIXES)
PORTABLE_MODEL_NAMES = (
    "linear_svc",
    "svc_linear",
    "svc_rbf",
    "decision_tree_depth3",
    "decision_tree_depth6",
    "random_forest_50_depth6",
    "random_forest_100_depth8",
    "gradient_boosting_50_depth2",
    "gradient_boosting_100_depth2",
)


@dataclass(frozen=True)
class DropoutConfig:
    model_alias: str = "pain-thermometer-dropout-ensemble"
    model_version: str = "dropout_soft_vote_20260510"
    high_pain_threshold_nrs: float = 4.0
    flag_threshold: float = 0.65
    random_state: int = 42
    dropout_copies: int = 1
    dropout_probability: float = 0.35
    max_kernel_rows: int = 3_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric_columns(frame: pd.DataFrame, sensor_blocks: tuple[str, ...]) -> list[str]:
    prefixes = tuple(prefix for block in sensor_blocks for prefix in SENSOR_PREFIXES[block])
    excluded = set(ID_COLUMNS) | set(LEAKY_COLUMNS)
    excluded.update(column for column in frame.columns if column.startswith(TARGET_PREFIXES))
    selected = [
        column
        for column in frame.columns
        if column.startswith(prefixes)
        and column not in excluded
        and frame[column].notna().any()
        and (pd.api.types.is_numeric_dtype(frame[column]) or pd.api.types.is_bool_dtype(frame[column]))
    ]
    selected.extend(
        column
        for column in STATE_COLUMNS
        if column in frame.columns
        and frame[column].notna().any()
        and (pd.api.types.is_numeric_dtype(frame[column]) or pd.api.types.is_bool_dtype(frame[column]))
    )
    out: list[str] = []
    seen: set[str] = set()
    for column in selected:
        if column not in seen:
            out.append(column)
            seen.add(column)
    return out


def clean_matrix(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    pieces = {}
    for column in columns:
        if column in frame.columns:
            pieces[column] = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
        else:
            pieces[column] = pd.Series(np.nan, index=frame.index)
    return pd.DataFrame(pieces, index=frame.index)


def sensor_columns_for(columns: list[str], sensor_block: str) -> list[str]:
    prefixes = SENSOR_PREFIXES[sensor_block]
    return [column for column in columns if column.startswith(prefixes)]


def apply_sensor_dropout(
    x: pd.DataFrame,
    columns: list[str],
    sensor_blocks: tuple[str, ...],
    rng: np.random.Generator,
    dropout_probability: float,
) -> pd.DataFrame:
    out = x.copy()
    for block in sensor_blocks:
        block_columns = sensor_columns_for(columns, block)
        if not block_columns or rng.random() > dropout_probability:
            continue
        for column in block_columns:
            if column.endswith("__present") or column.endswith("__valid_count") or column.endswith("__valid_frac"):
                out[column] = 0.0
            else:
                out[column] = np.nan
    return out


def augment_dropouts(
    x: pd.DataFrame,
    y: pd.Series,
    columns: list[str],
    sensor_blocks: tuple[str, ...],
    config: DropoutConfig,
) -> tuple[np.ndarray, np.ndarray]:
    frames = [x]
    labels = [y]
    rng = np.random.default_rng(config.random_state)
    for _ in range(config.dropout_copies):
        frames.append(apply_sensor_dropout(x, columns, sensor_blocks, rng, config.dropout_probability))
        labels.append(y)
    combined_x = pd.concat(frames, ignore_index=True)
    combined_y = pd.concat(labels, ignore_index=True).astype(int)
    return combined_x.to_numpy(dtype=np.float32), combined_y.to_numpy(dtype=np.int64)


def model_factories(seed: int) -> dict[str, tuple[Callable[[], Any], bool]]:
    return {
        "linear_svc": (lambda: LinearSVC(class_weight="balanced", max_iter=4000, random_state=seed), True),
        "svc_linear": (lambda: SVC(kernel="linear", probability=True, class_weight="balanced", max_iter=3000, random_state=seed), True),
        "svc_rbf": (lambda: SVC(kernel="rbf", probability=True, class_weight="balanced", max_iter=3000, random_state=seed), True),
        "decision_tree_depth3": (lambda: DecisionTreeClassifier(max_depth=3, class_weight="balanced", random_state=seed), False),
        "decision_tree_depth6": (lambda: DecisionTreeClassifier(max_depth=6, class_weight="balanced", random_state=seed), False),
        "random_forest_50_depth6": (
            lambda: RandomForestClassifier(n_estimators=50, max_depth=6, class_weight="balanced_subsample", n_jobs=-1, random_state=seed),
            False,
        ),
        "random_forest_100_depth8": (
            lambda: RandomForestClassifier(n_estimators=100, max_depth=8, class_weight="balanced_subsample", n_jobs=-1, random_state=seed),
            False,
        ),
        "gradient_boosting_50_depth2": (lambda: GradientBoostingClassifier(n_estimators=50, learning_rate=0.06, max_depth=2, random_state=seed), False),
        "gradient_boosting_100_depth2": (lambda: GradientBoostingClassifier(n_estimators=100, learning_rate=0.04, max_depth=2, random_state=seed), False),
    }


def pipeline_for(name: str, seed: int) -> Pipeline:
    factory, scaled = model_factories(seed)[name]
    steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median"))]
    if scaled:
        steps.append(("scaler", StandardScaler()))
    steps.append(("model", factory()))
    return Pipeline(steps)


def hgb_pipeline(seed: int) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                HistGradientBoostingClassifier(
                    max_iter=80,
                    learning_rate=0.05,
                    l2_regularization=0.08,
                    max_leaf_nodes=31,
                    early_stopping=True,
                    random_state=seed,
                ),
            ),
        ]
    )


def score_values(model: Pipeline, x: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(x)[:, 1]
    if hasattr(model, "decision_function"):
        scores = model.decision_function(x)
        return 1.0 / (1.0 + np.exp(-np.clip(scores, -50, 50)))
    return model.predict(x)


def metrics(y_true: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    pred = (scores >= 0.5).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "average_precision": float(average_precision_score(y_true, scores)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
        "accuracy": float(accuracy_score(y_true, pred)),
    }


def subset_for_kernel(x: np.ndarray, y: np.ndarray, max_rows: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    if len(y) <= max_rows:
        return x, y
    rng = np.random.default_rng(seed)
    positive = np.flatnonzero(y == 1)
    negative = np.flatnonzero(y == 0)
    pos_n = min(len(positive), max(max_rows // 2, int(max_rows * y.mean())))
    neg_n = max_rows - pos_n
    keep = np.concatenate(
        [
            rng.choice(positive, size=pos_n, replace=False),
            rng.choice(negative, size=min(len(negative), neg_n), replace=False),
        ]
    )
    rng.shuffle(keep)
    return x[keep], y[keep]


def fit_member(name: str, x: np.ndarray, y: np.ndarray, config: DropoutConfig) -> tuple[Pipeline, float, int]:
    model = pipeline_for(name, config.random_state)
    x_fit, y_fit = (x, y)
    if name in {"svc_linear", "svc_rbf"}:
        x_fit, y_fit = subset_for_kernel(x, y, config.max_kernel_rows, config.random_state)
    print(f"training {name} rows={len(y_fit)} features={x_fit.shape[1]}", flush=True)
    started = time.perf_counter()
    model.fit(x_fit, y_fit)
    elapsed = time.perf_counter() - started
    print(f"trained {name} seconds={elapsed:.2f}", flush=True)
    return model, elapsed, len(y_fit)


def evaluate_view(
    name: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    sensor_blocks: tuple[str, ...],
    config: DropoutConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    columns = numeric_columns(train, sensor_blocks)
    x_train_raw = clean_matrix(train, columns)
    x_test = clean_matrix(test, columns).to_numpy(dtype=np.float32)
    y_train = train["pain_high_4_plus"].astype(int)
    y_test = test["pain_high_4_plus"].astype(int).to_numpy(dtype=np.int64)
    x_train, y_train_aug = augment_dropouts(x_train_raw, y_train, columns, sensor_blocks, config)

    hgb = hgb_pipeline(config.random_state)
    print(f"training hgb_current_family view={name} rows={len(y_train_aug)} features={len(columns)}", flush=True)
    started = time.perf_counter()
    hgb.fit(x_train, y_train_aug)
    hgb_scores = score_values(hgb, x_test)
    baseline = {
        "model_name": "hgb_current_family",
        "train_rows": int(len(y_train_aug)),
        "test_rows": int(len(y_test)),
        "features": int(len(columns)),
        "train_seconds": float(time.perf_counter() - started),
        "conversion_status": "not_coreml_sklearn_supported",
        **metrics(y_test, hgb_scores),
    }

    members: dict[str, Pipeline] = {}
    member_rows = []
    member_scores = []
    for member_name in PORTABLE_MODEL_NAMES:
        model, train_seconds, fit_rows = fit_member(member_name, x_train, y_train_aug, config)
        scores = score_values(model, x_test)
        member_scores.append(scores)
        members[member_name] = model
        member_rows.append(
            {
                "model_name": member_name,
                "train_rows": int(fit_rows),
                "test_rows": int(len(y_test)),
                "features": int(len(columns)),
                "train_seconds": float(train_seconds),
                "relative_auc_vs_hgb": float(roc_auc_score(y_test, scores) / baseline["roc_auc"]),
                **metrics(y_test, scores),
            }
        )

    ensemble_scores = np.mean(np.vstack(member_scores), axis=0)
    ensemble = {
        "model_name": "soft_vote_all_nine",
        "train_rows": int(len(y_train_aug)),
        "test_rows": int(len(y_test)),
        "features": int(len(columns)),
        "members": list(PORTABLE_MODEL_NAMES),
        "relative_auc_vs_hgb": float(roc_auc_score(y_test, ensemble_scores) / baseline["roc_auc"]),
        **metrics(y_test, ensemble_scores),
    }
    payload = {
        "view": name,
        "columns": columns,
        "sensor_blocks": sensor_blocks,
        "dropout_training": {
            "copies": config.dropout_copies,
            "probability": config.dropout_probability,
            "original_train_rows": int(len(train)),
            "augmented_train_rows": int(len(y_train_aug)),
        },
        "baseline": baseline,
        "members": member_rows,
        "ensemble": ensemble,
    }
    artifact = {"columns": columns, "sensor_blocks": sensor_blocks, "members": members}
    return payload, artifact


def train_final_view(
    frame: pd.DataFrame,
    sensor_blocks: tuple[str, ...],
    config: DropoutConfig,
) -> dict[str, Any]:
    columns = numeric_columns(frame, sensor_blocks)
    x_raw = clean_matrix(frame, columns)
    y = frame["pain_high_4_plus"].astype(int)
    x_train, y_train = augment_dropouts(x_raw, y, columns, sensor_blocks, config)
    members: dict[str, Pipeline] = {}
    rows = []
    for member_name in PORTABLE_MODEL_NAMES:
        model, train_seconds, fit_rows = fit_member(member_name, x_train, y_train, config)
        members[member_name] = model
        rows.append({"model_name": member_name, "train_rows": int(fit_rows), "train_seconds": float(train_seconds)})
    return {
        "columns": columns,
        "sensor_blocks": sensor_blocks,
        "members": members,
        "training_summary": rows,
        "dropout_training": {
            "copies": config.dropout_copies,
            "probability": config.dropout_probability,
            "original_rows": int(len(frame)),
            "augmented_rows": int(len(y_train)),
        },
    }


def export_coreml(model: Pipeline, columns: list[str], path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        import coremltools as ct

        coreml_model = ct.converters.sklearn.convert(
            model,
            input_features=columns,
            output_feature_names=("pain_flag", "pain_scores"),
        )
        if not hasattr(coreml_model, "save"):
            coreml_model = ct.models.MLModel(coreml_model)
        coreml_model.save(str(path))
        return {"status": "converted", "seconds": float(time.perf_counter() - started), "path": str(path)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "seconds": float(time.perf_counter() - started), "error": f"{type(exc).__name__}: {exc}"}


def export_onnx(model: Pipeline, feature_count: int, path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from skl2onnx import to_onnx

        options = {}
        if isinstance(model.steps[-1][1], LinearSVC):
            options[id(model.steps[-1][1])] = {"raw_scores": True}
        onnx_model = to_onnx(model, np.zeros((1, feature_count), dtype=np.float32), target_opset=15, options=options)
        path.write_bytes(onnx_model.SerializeToString())
        return {"status": "converted", "seconds": float(time.perf_counter() - started), "path": str(path)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "seconds": float(time.perf_counter() - started), "error": f"{type(exc).__name__}: {exc}"}


def export_artifacts(final_artifact: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    export_dir = output_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    exports: dict[str, Any] = {}
    for view_name, view in final_artifact["views"].items():
        columns = view["columns"]
        exports[view_name] = {}
        for member_name, model in view["members"].items():
            stem = f"{view_name}_{member_name}"
            print(f"exporting {stem}", flush=True)
            exports[view_name][member_name] = {
                "coreml": export_coreml(model, columns, export_dir / f"{stem}.mlmodel"),
                "onnx": export_onnx(model, len(columns), export_dir / f"{stem}.onnx"),
            }
    return exports


def build_artifact(input_path: Path, output_dir: Path, config: DropoutConfig, skip_exports: bool = False) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(input_path).reset_index(drop=True)
    direct = frame.loc[frame["label_family"].eq("direct_pain") & frame["target_pain_nrs_0_10"].notna()].copy()
    direct["pain_high_4_plus"] = (direct["target_pain_nrs_0_10"].astype(float) >= config.high_pain_threshold_nrs).astype(int)
    groups = direct["phase3_eval_group"].astype("string").fillna("missing")
    split = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=config.random_state)
    train_idx, test_idx = next(split.split(direct, groups=groups))
    train = direct.iloc[train_idx].copy()
    test = direct.iloc[test_idx].copy()

    reports: dict[str, Any] = {}
    eval_artifacts: dict[str, Any] = {}
    for view_name, blocks in {"full_sensor": FULL_SENSOR_BLOCKS, "watch_friendly": WATCH_SENSOR_BLOCKS}.items():
        reports[view_name], eval_artifacts[view_name] = evaluate_view(view_name, train, test, blocks, config)

    final_views = {
        "full_sensor": train_final_view(direct, FULL_SENSOR_BLOCKS, config),
        "watch_friendly": train_final_view(direct, WATCH_SENSOR_BLOCKS, config),
    }
    artifact = {
        "config": asdict(config),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "input_sha256": sha256_file(input_path),
        "target": "pain_high_4_plus",
        "rows": int(len(direct)),
        "positive_rate": float(direct["pain_high_4_plus"].mean()),
        "views": final_views,
        "evaluation": reports,
        "routing": {
            "watch_local": "watch_friendly soft-vote ensemble; tolerate missing sensor blocks via dropout-trained imputation",
            "server_full": "full_sensor soft-vote ensemble when non-watch sensor blocks are available",
        },
    }
    model_path = output_dir / "model.joblib"
    joblib.dump(artifact, model_path, compress=3)
    exports = {} if skip_exports else export_artifacts(artifact, output_dir)
    manifest = {
        "model_alias": config.model_alias,
        "model_version": config.model_version,
        "created_at_utc": artifact["trained_at_utc"],
        "artifact_path": str(model_path),
        "artifact_sha256": sha256_file(model_path),
        "artifact_bytes": model_path.stat().st_size,
        "input_path": str(input_path),
        "input_sha256": artifact["input_sha256"],
        "rows": artifact["rows"],
        "positive_rate": artifact["positive_rate"],
        "evaluation": reports,
        "exports": exports,
        "note": "All nine portable members are retained; dropout handling is trained by sensor-block masking instead of creating format-specific model versions.",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train dropout-tolerant portable pain ensembles.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--dropout-copies", type=int, default=1)
    parser.add_argument("--dropout-probability", type=float, default=0.35)
    parser.add_argument("--max-kernel-rows", type=int, default=3_000)
    parser.add_argument("--skip-exports", action="store_true")
    return parser


def main() -> int:
    warnings.simplefilter("ignore", PerformanceWarning)
    args = build_parser().parse_args()
    config = DropoutConfig(
        random_state=args.random_state,
        dropout_copies=args.dropout_copies,
        dropout_probability=args.dropout_probability,
        max_kernel_rows=args.max_kernel_rows,
    )
    manifest = build_artifact(Path(args.input), Path(args.output), config, skip_exports=args.skip_exports)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
