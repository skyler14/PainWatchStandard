#!/usr/bin/env python3
"""Bounded Functional Pain V2 professional-method and learner benchmark."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from sklearn.svm import SVC

from train_functional_pain_v1 import derive_targets, load_features


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/functional_pain_v2_benchmark"
TARGETS = ("sympathetic_activation", "parasympathetic_recovery_proxy", "homeostasis")

PROFILE_PREFIXES = {
    "native_full": (),
    "watch_core": ("hr__", "ibi__", "acc_", "acc__", "temperature__", "spo2__"),
    "watch_plus_eda": ("hr__", "ibi__", "acc_", "acc__", "temperature__", "spo2__", "eda__"),
    "watch_plus_respiration": (
        "hr__",
        "ibi__",
        "acc_",
        "acc__",
        "temperature__",
        "spo2__",
        "respiration__",
    ),
    "chest_reference": (
        "ecg__",
        "ibi__",
        "hr__",
        "respiration__",
        "eda__",
        "acc_",
        "acc__",
        "temperature__",
        "emg__",
    ),
}

ARM_PREFIXES = {
    "autonomic_space": ("hr__", "ibi__", "eda__", "temperature__", "respiration__", "acc_", "acc__", "bvp__"),
    "stress_ensemble": ("hr__", "eda__"),
    "wesad_multimodal": ("bvp__", "eda__", "hr__", "ibi__", "temperature__", "acc_", "acc__", "respiration__"),
    "cvxeda_proxy": ("eda__",),
    "hrv_biofeedback": ("ibi__", "hr__", "respiration__"),
    "multimodal_pain": ("bvp__", "eda__", "hr__", "ibi__", "temperature__", "acc_", "acc__", "respiration__", "ecg__", "emg__"),
}

ALLOWED_SUFFIXES = (
    "__base__mean",
    "__base__std",
    "__base__min",
    "__base__max",
    "__base__last",
    "__shape__median",
    "__shape__mad",
    "__shape__iqr",
    "__shape__late_minus_early_z",
    "__shape__last_minus_first_z",
    "__shape__mean_abs_diff_z",
    "__shape__std_diff_z",
    "__shape__autocorr_05s",
    "__shape__autocorr_1s",
    "__shape__autocorr_2s",
    "__shape__dominant_frequency",
    "__shape__spectral_entropy",
    "__shape__low_band_power",
    "__shape__mid_band_power",
    "__shape__high_band_power",
)


@dataclass(frozen=True)
class Result:
    stage: str
    target: str
    profile: str
    arm: str
    learner: str
    split: str
    rows: int
    subjects: int
    features: int
    prevalence: float
    auc: float
    average_precision: float
    brier: float


def numeric_candidates(frame: pd.DataFrame) -> list[str]:
    excluded = {"y", "target_value", "window_end_s", *TARGETS, "activity_control", "pns_proxy_score"}
    return [
        column
        for column in frame.columns
        if column not in excluded
        and pd.api.types.is_numeric_dtype(frame[column])
        and frame[column].notna().any()
        and ("__base__" in column or "__shape__" in column or column == "window_s")
        and "__shuffle__" not in column
        and "__reverse__" not in column
    ]


def select_features(frame: pd.DataFrame, profile: str, arm: str, max_features: int = 72) -> list[str]:
    candidates = numeric_candidates(frame)
    profile_prefixes = PROFILE_PREFIXES[profile]
    arm_prefixes = ARM_PREFIXES[arm]
    selected = []
    for column in candidates:
        if column == "window_s":
            selected.append(column)
            continue
        if profile_prefixes and not column.startswith(profile_prefixes):
            continue
        if not column.startswith(arm_prefixes):
            continue
        if not column.endswith(ALLOWED_SUFFIXES):
            continue
        selected.append(column)

    # Coverage-first ordering favors features usable across sources and devices.
    coverage = frame[selected].notna().mean() if selected else pd.Series(dtype=float)
    selected = sorted(selected, key=lambda column: (-float(coverage[column]), column))
    return selected[:max_features]


def preprocess(spline: bool = False) -> Pipeline:
    steps = [
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ]
    if spline:
        steps.insert(1, ("spline", SplineTransformer(n_knots=4, degree=2, include_bias=False)))
    return Pipeline(steps)


def learner(name: str) -> Pipeline:
    if name == "portable_logistic":
        model = LogisticRegression(max_iter=500, class_weight="balanced", C=0.7)
        prep = preprocess()
    elif name == "elastic_net":
        model = LogisticRegression(
            max_iter=700,
            class_weight="balanced",
            penalty="elasticnet",
            solver="saga",
            l1_ratio=0.35,
            C=0.5,
            random_state=42,
        )
        prep = preprocess()
    elif name == "gam_spline":
        model = LogisticRegression(max_iter=600, class_weight="balanced", C=0.3)
        prep = preprocess(spline=True)
    elif name == "lda":
        model = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
        prep = preprocess()
    elif name == "rbf_svm":
        model = SVC(C=1.0, gamma="scale", probability=True, class_weight="balanced", random_state=42)
        prep = preprocess()
    elif name == "random_forest":
        model = RandomForestClassifier(
            n_estimators=80,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        )
        prep = preprocess()
    elif name == "extra_trees":
        model = ExtraTreesClassifier(
            n_estimators=80,
            min_samples_leaf=5,
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
        )
        prep = preprocess()
    elif name == "gradient_boosting":
        model = HistGradientBoostingClassifier(
            max_iter=60,
            learning_rate=0.07,
            l2_regularization=0.08,
            random_state=42,
        )
        prep = preprocess()
    elif name == "small_mlp":
        model = MLPClassifier(
            hidden_layer_sizes=(24,),
            alpha=0.01,
            max_iter=180,
            early_stopping=True,
            random_state=42,
        )
        prep = preprocess()
    elif name == "stacked_vote":
        model = VotingClassifier(
            estimators=[
                ("lr", LogisticRegression(max_iter=400, class_weight="balanced", C=0.7)),
                (
                    "et",
                    ExtraTreesClassifier(
                        n_estimators=50,
                        min_samples_leaf=5,
                        class_weight="balanced",
                        n_jobs=-1,
                        random_state=42,
                    ),
                ),
                (
                    "mlp",
                    MLPClassifier(
                        hidden_layer_sizes=(16,),
                        alpha=0.02,
                        max_iter=140,
                        early_stopping=True,
                        random_state=42,
                    ),
                ),
            ],
            voting="soft",
            weights=(0.4, 0.4, 0.2),
        )
        prep = preprocess()
    else:
        raise KeyError(name)
    return Pipeline([("preprocess", prep), ("model", model)])


def group_cv(
    frame: pd.DataFrame,
    target: str,
    features: list[str],
    learner_name: str,
    folds: int = 3,
) -> tuple[np.ndarray, pd.DataFrame]:
    data = frame.loc[frame[target].notna()].reset_index(drop=True)
    features = [column for column in features if data[column].notna().any()]
    groups = data["subject_group"].astype(str)
    y = data[target].astype(int)
    predictions = np.full(len(data), np.nan)
    splitter = GroupKFold(n_splits=min(folds, groups.nunique()))
    for train_index, test_index in splitter.split(data, y, groups):
        model = learner(learner_name)
        model.fit(data.loc[train_index, features], y.iloc[train_index])
        predictions[test_index] = model.predict_proba(data.loc[test_index, features])[:, 1]
    return predictions, data


def metric(
    stage: str,
    target: str,
    profile: str,
    arm: str,
    learner_name: str,
    split: str,
    predictions: np.ndarray,
    data: pd.DataFrame,
    feature_count: int,
) -> Result:
    valid = np.isfinite(predictions)
    y = data.loc[valid, target].astype(int).to_numpy()
    score = predictions[valid]
    return Result(
        stage=stage,
        target=target,
        profile=profile,
        arm=arm,
        learner=learner_name,
        split=split,
        rows=len(y),
        subjects=data.loc[valid, "subject_group"].nunique(),
        features=feature_count,
        prevalence=float(y.mean()),
        auc=float(roc_auc_score(y, score)),
        average_precision=float(average_precision_score(y, score)),
        brier=float(brier_score_loss(y, score)),
    )


def screen_arms(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[tuple[str, str, str], list[str]]]:
    rows = []
    feature_map = {}
    for target in TARGETS:
        for profile in PROFILE_PREFIXES:
            for arm in ARM_PREFIXES:
                features = select_features(frame, profile, arm)
                if len(features) < 3:
                    continue
                feature_map[(target, profile, arm)] = features
                predictions, data = group_cv(frame, target, features, "elastic_net")
                rows.append(
                    asdict(
                        metric(
                            "literature_arm_screen",
                            target,
                            profile,
                            arm,
                            "elastic_net",
                            "group_subject_cv",
                            predictions,
                            data,
                            len(features),
                        )
                    )
                )
    return pd.DataFrame(rows), feature_map


def choose_finalists(screen: pd.DataFrame) -> pd.DataFrame:
    finalists = []
    for target, group in screen.groupby("target"):
        # Always compare watch-core winner and overall winner; add best chest/reference arm.
        overall = group.sort_values("auc", ascending=False).head(1)
        watch = group.loc[group["profile"].eq("watch_core")].sort_values("auc", ascending=False).head(1)
        chest = group.loc[group["profile"].eq("chest_reference")].sort_values("auc", ascending=False).head(1)
        finalists.append(pd.concat([overall, watch, chest]).drop_duplicates(["target", "profile", "arm"]))
    return pd.concat(finalists, ignore_index=True)


def benchmark_learners(
    frame: pd.DataFrame,
    finalists: pd.DataFrame,
    feature_map: dict[tuple[str, str, str], list[str]],
) -> pd.DataFrame:
    names = [
        "portable_logistic",
        "elastic_net",
        "gam_spline",
        "lda",
        "rbf_svm",
        "random_forest",
        "extra_trees",
        "gradient_boosting",
        "small_mlp",
        "stacked_vote",
    ]
    rows = []
    for finalist in finalists.itertuples(index=False):
        features = feature_map[(finalist.target, finalist.profile, finalist.arm)]
        for name in names:
            predictions, data = group_cv(frame, finalist.target, features, name)
            rows.append(
                asdict(
                    metric(
                        "learner_benchmark",
                        finalist.target,
                        finalist.profile,
                        finalist.arm,
                        name,
                        "group_subject_cv",
                        predictions,
                        data,
                        len(features),
                    )
                )
            )
    return pd.DataFrame(rows)


def leave_dataset_out(
    frame: pd.DataFrame,
    finalists: pd.DataFrame,
    feature_map: dict[tuple[str, str, str], list[str]],
    learner_results: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for finalist in finalists.itertuples(index=False):
        target = finalist.target
        profile = finalist.profile
        arm = finalist.arm
        features = feature_map[(target, profile, arm)]
        best_name = (
            learner_results.loc[
                learner_results["target"].eq(target)
                & learner_results["profile"].eq(profile)
                & learner_results["arm"].eq(arm)
            ]
            .sort_values("auc", ascending=False)
            .iloc[0]["learner"]
        )
        data = frame.loc[frame[target].notna()].reset_index(drop=True)
        for heldout in sorted(data["dataset_id"].astype(str).unique()):
            train = data.loc[~data["dataset_id"].astype(str).eq(heldout)]
            test = data.loc[data["dataset_id"].astype(str).eq(heldout)]
            if train[target].nunique() < 2 or test[target].nunique() < 2:
                continue
            model = learner(best_name)
            model.fit(train[features], train[target].astype(int))
            predictions = model.predict_proba(test[features])[:, 1]
            rows.append(
                asdict(
                    metric(
                        "best_learner_transfer",
                        target,
                        profile,
                        arm,
                        best_name,
                        f"leave_dataset_out:{heldout}",
                        predictions,
                        test.reset_index(drop=True),
                        len(features),
                    )
                )
            )
    return pd.DataFrame(rows)


def controls(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dataset_dummies = pd.get_dummies(
        frame["dataset_id"].astype(str),
        prefix="dataset",
        dtype=float,
    )
    control_frame = pd.concat([frame, dataset_dummies], axis=1)
    for target in TARGETS:
        for name, features in {
            "dataset_only": ["window_s", *dataset_dummies.columns.tolist()],
            "quality_only": [
                column
                for column in frame.columns
                if ("__quality__" in column or column == "source_rows") and frame[column].notna().any()
            ],
            "activity_only": [
                column
                for column in frame.columns
                if column.startswith(("acc_", "acc__")) and "__base__" in column and frame[column].notna().any()
            ][:24],
        }.items():
            predictions, data = group_cv(control_frame, target, features, "elastic_net")
            rows.append(
                asdict(
                    metric(
                        "control",
                        target,
                        name,
                        name,
                        "elastic_net",
                        "group_subject_cv",
                        predictions,
                        data,
                        len(features),
                    )
                )
            )
    return pd.DataFrame(rows)


def main() -> None:
    warnings.filterwarnings("ignore")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = derive_targets(load_features()).copy()

    screen, feature_map = screen_arms(frame)
    finalists = choose_finalists(screen)
    learner_results = benchmark_learners(frame, finalists, feature_map)
    transfer = leave_dataset_out(frame, finalists, feature_map, learner_results)
    control_results = controls(frame)

    screen.to_csv(OUTPUT / "literature_arm_screen.csv", index=False)
    finalists.to_csv(OUTPUT / "finalists.csv", index=False)
    learner_results.to_csv(OUTPUT / "learner_benchmark.csv", index=False)
    transfer.to_csv(OUTPUT / "leave_dataset_out.csv", index=False)
    control_results.to_csv(OUTPUT / "controls.csv", index=False)

    feature_payload = {
        f"{target}|{profile}|{arm}": features
        for (target, profile, arm), features in feature_map.items()
    }
    (OUTPUT / "feature_sets.json").write_text(json.dumps(feature_payload, indent=2))
    (OUTPUT / "manifest.json").write_text(
        json.dumps(
            {
                "rows": len(frame),
                "targets": TARGETS,
                "profiles_run": list(PROFILE_PREFIXES),
                "profile_not_run": {
                    "watch_guided_breath": "current feature tables lack guided inhale/exhale phase"
                },
                "literature_arms": list(ARM_PREFIXES),
                "learners": sorted(learner_results["learner"].unique()),
                "dataset_control": "one-hot dataset identity plus window length",
                "limitations": [
                    "cvxeda_proxy uses EDA shape features, not raw convex decomposition",
                    "hrv_biofeedback lacks true RSA for most rows",
                    "parasympathetic target is weak and partly physiology-bootstrapped",
                    "60-second history unavailable in prior feature tables",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
