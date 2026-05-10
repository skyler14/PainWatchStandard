#!/usr/bin/env python3
"""Core ML conversion sweep for watch-local pain trigger candidates.

This benchmark intentionally uses the direct-pain high-pain classification
target only. It compares candidate classifiers against the current
HistGradientBoosting pain head on small stratified data fractions, then attempts
Core ML conversion for each trained sklearn pipeline.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import coremltools as ct
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (
    AdaBoostClassifier,
    BaggingClassifier,
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import (
    LogisticRegression,
    PassiveAggressiveClassifier,
    Perceptron,
    RidgeClassifier,
    SGDClassifier,
)
from sklearn.metrics import accuracy_score, average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import BernoulliNB, GaussianNB
from sklearn.neighbors import KNeighborsClassifier, NearestCentroid
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MaxAbsScaler, MinMaxScaler, Normalizer, RobustScaler, StandardScaler
from sklearn.svm import LinearSVC, SVC
from sklearn.tree import DecisionTreeClassifier, ExtraTreeClassifier


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "_normalized" / "phase3" / "target_hz=1" / "window_features.parquet"
DEFAULT_OUTPUT = ROOT / "inference_flow" / "experiments" / "coreml_sweep_results.json"

SENSOR_PREFIXES = {
    "bvp": ("bvp__",),
    "hr": ("hr__",),
    "ibi": ("ibi__",),
    "ecg": ("ecg__",),
    "temperature": ("temperature__",),
    "acc": ("acc_x__", "acc_y__", "acc_z__", "acc__"),
    "gyro": ("gyro_x__", "gyro_y__", "gyro_z__", "gyro__"),
    "spo2": ("spo2__",),
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
ID_COLUMNS = {"phase3_window_id", "original_all_window_id", "subject_id", "session_id", "phase3_eval_group", "baseline_anchor_id"}
LEAKY_COLUMNS = {"window_start_s", "window_end_s", "source_archive", "source_member", "source_table", "phase3_source_table"}
TARGET_PREFIXES = ("target_",)


@dataclass
class TrialResult:
    fraction: float
    model_name: str
    train_rows: int
    test_rows: int
    features: int
    train_seconds: float | None
    convert_seconds: float | None
    auc: float | None
    average_precision: float | None
    balanced_accuracy: float | None
    accuracy: float | None
    relative_auc_vs_hgb: float | None
    kept_for_next_round: bool
    conversion_status: str
    conversion_error: str | None = None
    fit_status: str = "ok"
    fit_error: str | None = None


def apple_watch_like_columns(frame: pd.DataFrame) -> list[str]:
    prefixes = tuple(prefix for sensor in SENSOR_PREFIXES.values() for prefix in sensor)
    excluded = set(ID_COLUMNS) | set(LEAKY_COLUMNS)
    excluded.update(column for column in frame.columns if column.startswith(TARGET_PREFIXES))
    selected = [
        column
        for column in frame.columns
        if column.startswith(prefixes)
        and column not in excluded
        and frame[column].notna().any()
    ]
    selected.extend(column for column in STATE_COLUMNS if column in frame.columns and frame[column].notna().any())
    out: list[str] = []
    seen: set[str] = set()
    for column in selected:
        if column not in seen:
            if pd.api.types.is_numeric_dtype(frame[column]) or pd.api.types.is_bool_dtype(frame[column]):
                out.append(column)
                seen.add(column)
    return out


def preprocessing_steps(scaler: str | None) -> list[tuple[str, Any]]:
    num_steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median"))]
    if scaler == "standard":
        num_steps.append(("scaler", StandardScaler()))
    elif scaler == "minmax":
        num_steps.append(("scaler", MinMaxScaler()))
    elif scaler == "maxabs":
        num_steps.append(("scaler", MaxAbsScaler()))
    elif scaler == "robust":
        num_steps.append(("scaler", RobustScaler()))
    elif scaler == "normalizer":
        num_steps.append(("scaler", Normalizer()))
    return num_steps


def candidates(seed: int) -> dict[str, tuple[Callable[[], Any], str | None]]:
    return {
        "hgb_current_family": (lambda: HistGradientBoostingClassifier(max_iter=80, learning_rate=0.05, l2_regularization=0.08, max_leaf_nodes=31, early_stopping=True, random_state=seed), None),
        "logreg_l2_lbfgs": (lambda: LogisticRegression(max_iter=500, solver="lbfgs", class_weight="balanced", random_state=seed), "standard"),
        "logreg_l1_liblinear": (lambda: LogisticRegression(max_iter=500, solver="liblinear", penalty="l1", class_weight="balanced", random_state=seed), "standard"),
        "logreg_elastic_saga": (lambda: LogisticRegression(max_iter=700, solver="saga", penalty="elasticnet", l1_ratio=0.25, class_weight="balanced", random_state=seed), "standard"),
        "ridge_classifier": (lambda: RidgeClassifier(class_weight="balanced", random_state=seed), "standard"),
        "sgd_log_loss": (lambda: SGDClassifier(loss="log_loss", penalty="elasticnet", alpha=0.0005, class_weight="balanced", max_iter=1000, random_state=seed), "standard"),
        "sgd_modified_huber": (lambda: SGDClassifier(loss="modified_huber", penalty="elasticnet", alpha=0.0005, class_weight="balanced", max_iter=1000, random_state=seed), "standard"),
        "linear_svc": (lambda: LinearSVC(class_weight="balanced", max_iter=3000, random_state=seed), "standard"),
        "svc_linear": (lambda: SVC(kernel="linear", probability=True, class_weight="balanced", random_state=seed), "standard"),
        "svc_rbf": (lambda: SVC(kernel="rbf", probability=True, class_weight="balanced", random_state=seed), "standard"),
        "decision_tree_depth3": (lambda: DecisionTreeClassifier(max_depth=3, class_weight="balanced", random_state=seed), None),
        "decision_tree_depth6": (lambda: DecisionTreeClassifier(max_depth=6, class_weight="balanced", random_state=seed), None),
        "extra_tree_depth6": (lambda: ExtraTreeClassifier(max_depth=6, class_weight="balanced", random_state=seed), None),
        "random_forest_50_depth6": (lambda: RandomForestClassifier(n_estimators=50, max_depth=6, class_weight="balanced_subsample", n_jobs=-1, random_state=seed), None),
        "random_forest_100_depth8": (lambda: RandomForestClassifier(n_estimators=100, max_depth=8, class_weight="balanced_subsample", n_jobs=-1, random_state=seed), None),
        "extra_trees_100_depth8": (lambda: ExtraTreesClassifier(n_estimators=100, max_depth=8, class_weight="balanced", n_jobs=-1, random_state=seed), None),
        "gradient_boosting_50_depth2": (lambda: GradientBoostingClassifier(n_estimators=50, learning_rate=0.06, max_depth=2, random_state=seed), None),
        "gradient_boosting_100_depth2": (lambda: GradientBoostingClassifier(n_estimators=100, learning_rate=0.04, max_depth=2, random_state=seed), None),
        "adaboost_50_stump": (lambda: AdaBoostClassifier(n_estimators=50, learning_rate=0.5, random_state=seed), None),
        "bagging_tree_30": (lambda: BaggingClassifier(estimator=DecisionTreeClassifier(max_depth=5, class_weight="balanced", random_state=seed), n_estimators=30, random_state=seed, n_jobs=-1), None),
        "gaussian_nb": (lambda: GaussianNB(), None),
        "bernoulli_nb": (lambda: BernoulliNB(), None),
        "knn_3": (lambda: KNeighborsClassifier(n_neighbors=3), "standard"),
        "knn_7_distance": (lambda: KNeighborsClassifier(n_neighbors=7, weights="distance"), "standard"),
        "nearest_centroid": (lambda: NearestCentroid(), "standard"),
        "mlp_16": (lambda: MLPClassifier(hidden_layer_sizes=(16,), alpha=0.001, max_iter=400, early_stopping=True, random_state=seed), "standard"),
        "mlp_32_16": (lambda: MLPClassifier(hidden_layer_sizes=(32, 16), alpha=0.001, max_iter=400, early_stopping=True, random_state=seed), "standard"),
        "perceptron": (lambda: Perceptron(class_weight="balanced", max_iter=1000, random_state=seed), "standard"),
        "passive_aggressive": (lambda: PassiveAggressiveClassifier(class_weight="balanced", max_iter=1000, random_state=seed), "standard"),
        "gaussian_process_rbf": (lambda: GaussianProcessClassifier(random_state=seed, max_iter_predict=50), "standard"),
        "dummy_stratified": (lambda: DummyClassifier(strategy="stratified", random_state=seed), None),
    }


def score_values(model: Any, x_test: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(x_test)[:, 1]
    if hasattr(model, "decision_function"):
        return model.decision_function(x_test)
    return model.predict(x_test)


def convert_model(model: Any, columns: list[str], out_path: Path) -> tuple[str, float | None, str | None]:
    started = time.perf_counter()
    try:
        coreml_model = ct.converters.sklearn.convert(
            model,
            input_features=columns,
            output_feature_names=("pain_flag", "pain_scores"),
        )
        if not hasattr(coreml_model, "save"):
            coreml_model = ct.models.MLModel(coreml_model)
        coreml_model.save(str(out_path))
        return "converted", time.perf_counter() - started, None
    except Exception as exc:  # noqa: BLE001
        return "failed", time.perf_counter() - started, f"{type(exc).__name__}: {exc}"


def run_fraction(frame: pd.DataFrame, fraction: float, names: list[str], seed: int, output_dir: Path) -> list[TrialResult]:
    direct = frame.loc[frame["label_family"].eq("direct_pain") & frame["target_pain_nrs_0_10"].notna()].copy()
    direct["pain_high_4_plus"] = (direct["target_pain_nrs_0_10"].astype(float) >= 4.0).astype(int)
    sample = (
        direct.groupby("pain_high_4_plus", group_keys=False)
        .sample(frac=fraction, random_state=seed)
        .reset_index(drop=True)
    )
    columns = [column for column in apple_watch_like_columns(sample) if sample[column].notna().any()]
    x = sample[columns].copy()
    y = sample["pain_high_4_plus"].astype(int)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.35, stratify=y, random_state=seed)
    all_candidates = candidates(seed)
    results: list[TrialResult] = []

    baseline_auc: float | None = None
    trained_results: dict[str, float | None] = {}
    models_to_run = names if names else list(all_candidates)
    if "hgb_current_family" not in models_to_run:
        models_to_run = ["hgb_current_family", *models_to_run]

    for name in models_to_run:
        factory, scaler = all_candidates[name]
        model = Pipeline([*preprocessing_steps(scaler), ("model", factory())])
        train_seconds = None
        try:
            started = time.perf_counter()
            model.fit(x_train, y_train)
            train_seconds = time.perf_counter() - started
            scores = score_values(model, x_test)
            predictions = model.predict(x_test)
            auc = float(roc_auc_score(y_test, scores))
            average_precision = float(average_precision_score(y_test, scores))
            balanced_accuracy = float(balanced_accuracy_score(y_test, predictions))
            accuracy = float(accuracy_score(y_test, predictions))
            fit_status = "ok"
            fit_error = None
        except Exception as exc:  # noqa: BLE001
            auc = average_precision = balanced_accuracy = accuracy = None
            fit_status = "failed"
            fit_error = f"{type(exc).__name__}: {exc}"

        if name == "hgb_current_family":
            baseline_auc = auc
        trained_results[name] = auc

        conversion_status = "not_attempted"
        convert_seconds = None
        conversion_error = None
        if fit_status == "ok":
            conversion_status, convert_seconds, conversion_error = convert_model(
                model,
                columns,
                output_dir / f"{fraction:.2f}_{name}.mlmodel",
            )

        relative = None if auc is None or baseline_auc in (None, 0) else auc / baseline_auc
        results.append(TrialResult(
            fraction=fraction,
            model_name=name,
            train_rows=len(x_train),
            test_rows=len(x_test),
            features=len(columns),
            train_seconds=train_seconds,
            convert_seconds=convert_seconds,
            auc=auc,
            average_precision=average_precision,
            balanced_accuracy=balanced_accuracy,
            accuracy=accuracy,
            relative_auc_vs_hgb=relative,
            kept_for_next_round=False,
            conversion_status=conversion_status,
            conversion_error=conversion_error,
            fit_status=fit_status,
            fit_error=fit_error,
        ))

    baseline_auc = trained_results.get("hgb_current_family")
    threshold = None if baseline_auc is None else baseline_auc * 0.9
    for result in results:
        result.kept_for_next_round = (
            result.model_name != "hgb_current_family"
            and result.auc is not None
            and threshold is not None
            and result.auc >= threshold
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--stage", choices=["one-percent", "ten-percent"], default="one-percent")
    parser.add_argument("--names", nargs="*", default=[])
    args = parser.parse_args()

    output_path = Path(args.output)
    model_output_dir = output_path.with_suffix("")
    model_output_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_parquet(args.input)
    if args.stage == "one-percent":
        results = run_fraction(frame, 0.01, args.names, args.seed, model_output_dir)
    else:
        results = run_fraction(frame, 0.10, args.names, args.seed, model_output_dir)

    payload = {
        "created_at_utc": pd.Timestamp.utcnow().isoformat(),
        "stage": args.stage,
        "sklearn_version": __import__("sklearn").__version__,
        "coremltools_version": ct.__version__,
        "results": [asdict(result) for result in results],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
