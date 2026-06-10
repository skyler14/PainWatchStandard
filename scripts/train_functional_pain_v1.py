#!/usr/bin/env python3
"""Train exploratory Functional Pain V1 state learners.

This run intentionally uses weak autonomic/state labels. It is for architecture
and feature discovery, not a deployable clinical pain model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import warnings
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/functional_pain_v1_run"
FEATURE_INPUTS = {
    5: ROOT / "outputs/temporal_shape_exploration_5s/temporal_shape_features.parquet",
    10: ROOT / "outputs/temporal_shape_exploration_10s/temporal_shape_features.parquet",
    30: ROOT / "outputs/temporal_shape_exploration/temporal_shape_features.parquet",
}
RANKING_INPUT = ROOT / "outputs/temporal_shape_r/univariate_feature_ranking.csv"


TARGETS = ("sympathetic_activation", "parasympathetic_recovery_proxy", "homeostasis")


@dataclass(frozen=True)
class MetricRow:
    target: str
    split: str
    model: str
    feature_set: str
    train_rows: int
    test_rows: int
    feature_count: int
    prevalence: float
    auc: float | None
    average_precision: float | None
    brier: float | None


def load_features() -> pd.DataFrame:
    frames = []
    for window_s, path in FEATURE_INPUTS.items():
        frame = pd.read_parquet(path)
        frame["window_s"] = float(window_s)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    combined["subject_group"] = combined["dataset_id"].astype(str) + "::" + combined["subject_id"].astype(str)
    return combined


def _ranked_shape_features() -> set[str]:
    if not RANKING_INPUT.exists():
        return set()
    ranking = pd.read_csv(RANKING_INPUT)
    if "feature" not in ranking:
        return set()
    top = (
        ranking.loc[~ranking["feature_group"].isin(["quality", "shuffle", "reverse"])]
        .groupby(["task", "dataset_id"], group_keys=False)
        .head(25)
    )
    return set(top["feature"].astype(str))


def feature_sets(frame: pd.DataFrame) -> dict[str, list[str]]:
    numeric = [
        column
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column])
        and column
        not in {
            "y",
            "target_value",
            "window_end_s",
        }
        and frame[column].notna().any()
    ]
    quality = [column for column in numeric if "__quality__" in column or column == "source_rows"]
    base = [column for column in numeric if "__base__" in column or column == "window_s"]
    shape = [
        column
        for column in numeric
        if ("__shape__" in column or "__coupling__" in column)
        and "__shuffle__" not in column
        and "__reverse__" not in column
    ]
    ranked = [column for column in shape if column in _ranked_shape_features()]
    if not ranked:
        ranked = shape[:250]
    dataset_only = ["dataset_id", "window_s"]
    return {
        "portable_base_shape": sorted(set(base + ranked)),
        "aggressive_shape": sorted(set(base + shape)),
        "quality_only": sorted(set(quality)),
        "dataset_only": dataset_only,
    }


def derive_targets(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    task = out["task"].astype(str)
    dataset = out["dataset_id"].astype(str)
    y = pd.to_numeric(out["y"], errors="coerce")

    out["sympathetic_activation"] = np.nan
    sns_positive = (
        ((task == "wesad_stress") & (y == 1))
        | ((task == "stress_vs_exercise") & (y == 1))
        | ((task == "cognitive_load_vs_baseline") & (y == 1))
        | ((task == "pain_high_4_plus") & (y == 1))
    )
    sns_negative = (
        ((task == "wesad_stress") & (y == 0))
        | ((task == "cognitive_load_vs_baseline") & (y == 0))
        | ((task == "pain_high_4_plus") & (y == 0))
    )
    out.loc[sns_positive, "sympathetic_activation"] = 1
    out.loc[sns_negative, "sympathetic_activation"] = 0

    out["homeostasis"] = np.nan
    home_positive = (
        ((task == "wesad_stress") & (y == 0))
        | ((task == "cognitive_load_vs_baseline") & (y == 0))
        | ((task == "pain_high_4_plus") & (y == 0) & ~dataset.eq("painmonit_pmed"))
    )
    home_negative = (
        ((task == "wesad_stress") & (y == 1))
        | ((task == "stress_vs_exercise") & (y == 1))
        | ((task == "cognitive_load_vs_baseline") & (y == 1))
        | ((task == "pain_high_4_plus") & (y == 1))
    )
    out.loc[home_positive, "homeostasis"] = 1
    out.loc[home_negative, "homeostasis"] = 0

    pns_score = pns_proxy_score(out)
    out["pns_proxy_score"] = pns_score
    out["parasympathetic_recovery_proxy"] = np.nan
    pns_candidates = home_positive & pns_score.notna()
    if pns_candidates.sum() >= 20:
        high = pns_score.loc[pns_candidates].quantile(0.70)
        low = pns_score.loc[pns_candidates].quantile(0.30)
        out.loc[pns_candidates & (pns_score >= high), "parasympathetic_recovery_proxy"] = 1
        out.loc[pns_candidates & (pns_score <= low), "parasympathetic_recovery_proxy"] = 0
        out.loc[sns_positive & pns_score.notna(), "parasympathetic_recovery_proxy"] = 0

    out["activity_control"] = np.nan
    out.loc[(task == "stress_vs_exercise") & (y == 0), "activity_control"] = 1
    out.loc[(task != "stress_vs_exercise") & y.notna(), "activity_control"] = 0

    return out


def _series_scaled(frame: pd.DataFrame, column: str, invert: bool = False) -> pd.Series:
    if column not in frame:
        return pd.Series(np.nan, index=frame.index)
    values = pd.to_numeric(frame[column], errors="coerce")
    lo = values.quantile(0.05)
    hi = values.quantile(0.95)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(np.nan, index=frame.index)
    scaled = ((values - lo) / (hi - lo)).clip(0, 1)
    return 1.0 - scaled if invert else scaled


def pns_proxy_score(frame: pd.DataFrame) -> pd.Series:
    parts = [
        _series_scaled(frame, "ibi__base__mean"),
        _series_scaled(frame, "hr__base__mean", invert=True),
        _series_scaled(frame, "eda__base__mean", invert=True),
        _series_scaled(frame, "eda__shape__late_minus_early_z", invert=True),
        _series_scaled(frame, "acc_mag__base__std", invert=True),
    ]
    return pd.concat(parts, axis=1).mean(axis=1, skipna=True)


def make_model(name: str, feature_set: str, columns: list[str]) -> Pipeline:
    categorical = [column for column in columns if column == "dataset_id"]
    numeric = [column for column in columns if column not in categorical]
    transformers = []
    if numeric:
        transformers.append(
            (
                "num",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                numeric,
            )
        )
    if categorical:
        transformers.append(
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical,
            )
        )
    preprocess = ColumnTransformer(transformers)
    if name == "logistic":
        clf = LogisticRegression(max_iter=800, class_weight="balanced", C=0.7)
    elif name == "hist_gradient_boosting":
        clf = HistGradientBoostingClassifier(max_iter=60, learning_rate=0.07, l2_regularization=0.05, random_state=42)
    elif name == "extra_trees":
        clf = ExtraTreesClassifier(
            n_estimators=90,
            min_samples_leaf=4,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
    else:
        raise ValueError(name)
    return Pipeline([("preprocess", preprocess), ("model", clf)])


def metric_row(
    target: str,
    split: str,
    model: str,
    feature_set: str,
    train_rows: int,
    y_true: pd.Series,
    score: np.ndarray,
    feature_count: int,
) -> MetricRow:
    y_arr = y_true.to_numpy(dtype=int)
    if len(np.unique(y_arr)) < 2:
        auc = average_precision = brier = None
    else:
        auc = float(roc_auc_score(y_arr, score))
        average_precision = float(average_precision_score(y_arr, score))
        brier = float(brier_score_loss(y_arr, score))
    return MetricRow(
        target=target,
        split=split,
        model=model,
        feature_set=feature_set,
        train_rows=train_rows,
        test_rows=len(y_arr),
        feature_count=feature_count,
        prevalence=float(np.mean(y_arr)),
        auc=auc,
        average_precision=average_precision,
        brier=brier,
    )


def evaluate_group_cv(frame: pd.DataFrame, target: str, model_name: str, feature_set_name: str, columns: list[str]) -> MetricRow:
    data = frame.loc[frame[target].notna()].reset_index(drop=True)
    columns = [column for column in columns if column == "dataset_id" or data[column].notna().any()]
    groups = data["subject_group"].astype(str)
    y = data[target].astype(int)
    folds = min(5, groups.nunique())
    predictions = np.full(len(data), np.nan)
    for train_index, test_index in GroupKFold(n_splits=folds).split(data, y, groups):
        model = make_model(model_name, feature_set_name, columns)
        model.fit(data.loc[train_index, columns], y.iloc[train_index])
        predictions[test_index] = model.predict_proba(data.loc[test_index, columns])[:, 1]
    valid = np.isfinite(predictions)
    return metric_row(
        target,
        "group_subject_cv",
        model_name,
        feature_set_name,
        int(valid.sum() * (folds - 1) / folds),
        y.loc[valid],
        predictions[valid],
        len(columns),
    )


def evaluate_leave_dataset(frame: pd.DataFrame, target: str, model_name: str, feature_set_name: str, columns: list[str]) -> list[MetricRow]:
    data = frame.loc[frame[target].notna()].reset_index(drop=True)
    columns = [column for column in columns if column == "dataset_id" or data[column].notna().any()]
    rows: list[MetricRow] = []
    for heldout in sorted(data["dataset_id"].astype(str).unique()):
        train = data.loc[~data["dataset_id"].astype(str).eq(heldout)]
        test = data.loc[data["dataset_id"].astype(str).eq(heldout)]
        if train[target].nunique() < 2 or test[target].nunique() < 2:
            continue
        model = make_model(model_name, feature_set_name, columns)
        model.fit(train[columns], train[target].astype(int))
        score = model.predict_proba(test[columns])[:, 1]
        rows.append(
            metric_row(
                target,
                f"leave_dataset_out:{heldout}",
                model_name,
                feature_set_name,
                len(train),
                test[target].astype(int),
                score,
                len(columns),
            )
        )
    return rows


def fit_final_logistic(frame: pd.DataFrame, feature_sets_: dict[str, list[str]]) -> dict[str, Any]:
    columns = feature_sets_["portable_base_shape"]
    payload: dict[str, Any] = {
        "method": "functional_pain_v1_portable_logistic",
        "targets": {},
        "feature_set": "portable_base_shape",
        "features": columns,
        "note": "Weak-label exploratory model. Use for architecture/dev only until calibrated.",
    }
    for target in TARGETS:
        data = frame.loc[frame[target].notna()].reset_index(drop=True)
        target_columns = [column for column in columns if data[column].notna().any()]
        y = data[target].astype(int)
        model = make_model("logistic", "portable_base_shape", target_columns)
        model.fit(data[target_columns], y)
        payload["targets"][target] = export_logistic(model, target_columns, int(len(data)), float(y.mean()))
        joblib.dump(model, OUTPUT / f"{target}_portable_base_shape_logistic.joblib")
    return payload


def export_logistic(model: Pipeline, columns: list[str], rows: int, prevalence: float) -> dict[str, Any]:
    preprocess: ColumnTransformer = model.named_steps["preprocess"]
    clf: LogisticRegression = model.named_steps["model"]
    num_pipe: Pipeline = preprocess.named_transformers_.get("num")  # type: ignore[assignment]
    numeric = list(preprocess.transformers_[0][2]) if preprocess.transformers_ else columns
    imputer: SimpleImputer = num_pipe.named_steps["imputer"]
    scaler: StandardScaler = num_pipe.named_steps["scaler"]
    return {
        "rows": rows,
        "prevalence": prevalence,
        "numeric_features": numeric,
        "imputer_median": [float(x) for x in imputer.statistics_],
        "scaler_mean": [float(x) for x in scaler.mean_],
        "scaler_scale": [float(x) for x in scaler.scale_],
        "coef": [float(x) for x in clf.coef_[0]],
        "intercept": float(clf.intercept_[0]),
        "activation": "sigmoid",
    }


def feature_importance(frame: pd.DataFrame, feature_sets_: dict[str, list[str]]) -> pd.DataFrame:
    columns = feature_sets_["portable_base_shape"]
    rows = []
    for target in TARGETS:
        data = frame.loc[frame[target].notna()].reset_index(drop=True)
        target_columns = [column for column in columns if data[column].notna().any()]
        y = data[target].astype(int)
        if y.nunique() < 2:
            continue
        model = make_model("extra_trees", "portable_base_shape", target_columns)
        model.fit(data[target_columns], y)
        clf: ExtraTreesClassifier = model.named_steps["model"]
        for feature, importance in zip(model.named_steps["preprocess"].get_feature_names_out(), clf.feature_importances_):
            rows.append({"target": target, "feature": feature, "importance": float(importance)})
    return pd.DataFrame(rows).sort_values(["target", "importance"], ascending=[True, False])


def write_report(metrics: pd.DataFrame, labels: pd.DataFrame, export_payload: dict[str, Any]) -> None:
    best = (
        metrics.loc[metrics["split"].eq("group_subject_cv")]
        .sort_values(["target", "auc"], ascending=[True, False])
        .groupby("target")
        .head(5)
    )
    transfer = metrics.loc[metrics["split"].str.startswith("leave_dataset_out")].copy()
    text = f"""# Functional Pain V1 Learning Run

Rows: {len(labels)}

## Label Counts

```text
{labels[[*TARGETS, "activity_control"]].agg(["count", "mean"]).to_string()}
```

## Best Group-CV Metrics

```text
{best[["target", "model", "feature_set", "auc", "average_precision", "brier", "feature_count"]].round(4).to_string(index=False)}
```

## Leave-Dataset Holdout

```text
{transfer[["target", "split", "model", "feature_set", "auc", "average_precision", "brier"]].round(4).to_string(index=False)}
```

## Export Status

```yaml
portable_json: functional_pain_v1_portable_logistic.json
sklearn_joblib: written locally but ignored by git
onnx: not exported; skl2onnx not installed in this environment
coreml: not exported; coremltools not installed in this environment
portable_loss: none for logistic JSON if runtime implements median impute + standard scale + sigmoid exactly
```

## Interpretation

This run trains weak state proxies, not clinical pain truth. Sympathetic and
homeostasis labels have external task support. Parasympathetic recovery is the
weakest target because current datasets rarely label active recovery or vagal
state directly; it is bootstrapped from high-IBI, low-HR, low-EDA, low-motion
windows.

Feature/control divergence matters:

- if `dataset_only` approaches main model AUC, protocol shortcut risk remains.
- if `quality_only` performs well, sensor availability is leaking state.
- if leave-dataset-out collapses, model is not portable yet.

Final export payload targets: {list(export_payload["targets"].keys())}
"""
    (OUTPUT / "FUNCTIONAL_PAIN_V1_RUN_REPORT.md").write_text(text)


def main() -> None:
    warnings.filterwarnings("ignore", message="Skipping features without any observed values")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = derive_targets(load_features())
    sets = feature_sets(frame)
    model_names = ["logistic", "hist_gradient_boosting", "extra_trees"]
    rows: list[MetricRow] = []
    for target in [*TARGETS, "activity_control"]:
        for feature_set_name, columns in sets.items():
            if not columns:
                continue
            if feature_set_name == "aggressive_shape":
                allowed_models = ["logistic"]
            elif feature_set_name in {"dataset_only", "quality_only"}:
                allowed_models = ["logistic", "extra_trees"] if feature_set_name == "quality_only" else ["logistic"]
            else:
                allowed_models = model_names
            for model_name in allowed_models:
                if feature_set_name == "dataset_only" and model_name != "logistic":
                    continue
                try:
                    rows.append(evaluate_group_cv(frame, target, model_name, feature_set_name, columns))
                    if feature_set_name in {"portable_base_shape", "dataset_only", "quality_only"}:
                        rows.extend(evaluate_leave_dataset(frame, target, model_name, feature_set_name, columns))
                except Exception as error:
                    print(f"skip {target}/{feature_set_name}/{model_name}: {error}")
    metrics = pd.DataFrame([asdict(row) for row in rows])
    metrics.to_csv(OUTPUT / "metrics.csv", index=False)
    label_summary = frame[
        ["window_s", "task", "dataset_id", "subject_id", *TARGETS, "activity_control", "pns_proxy_score"]
    ].copy()
    label_summary.to_csv(OUTPUT / "weak_label_frame.csv", index=False)
    importance = feature_importance(frame, sets)
    importance.to_csv(OUTPUT / "feature_importance.csv", index=False)
    export_payload = fit_final_logistic(frame, sets)
    (OUTPUT / "functional_pain_v1_portable_logistic.json").write_text(json.dumps(export_payload, indent=2))
    manifest = {
        "inputs": {str(k): str(v) for k, v in FEATURE_INPUTS.items()},
        "rows": len(frame),
        "feature_sets": {key: len(value) for key, value in sets.items()},
        "targets": TARGETS,
        "controls": ["activity_control", "dataset_only", "quality_only"],
        "export": {
            "portable_json": "functional_pain_v1_portable_logistic.json",
            "onnx": "not_available_missing_skl2onnx",
            "coreml": "not_available_missing_coremltools",
        },
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    write_report(metrics, label_summary, export_payload)


if __name__ == "__main__":
    main()
