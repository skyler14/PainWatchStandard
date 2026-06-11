#!/usr/bin/env python3
"""Evaluate current PNS-proxy learners against held-out WESAD protocol labels."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/wesad_pns_protocol_evaluation"
MASTER = ROOT / "_normalized/phase3_enriched/target_hz=1/window_features.parquet"

sys.path.insert(0, str(ROOT / "scripts"))
from run_functional_pain_v2_benchmark import learner, select_features  # noqa: E402
from train_functional_pain_v1 import derive_targets, load_features  # noqa: E402


def protocol_labels() -> pd.DataFrame:
    columns = [
        "dataset_id",
        "subject_id",
        "session_id",
        "window_end_s",
        "aux_state_label",
    ]
    frame = pd.read_parquet(MASTER, columns=columns)
    frame = frame.loc[frame["dataset_id"].astype(str).eq("wesad")].copy()
    frame["protocol"] = frame["aux_state_label"].astype("string")
    return frame.drop_duplicates(
        ["dataset_id", "subject_id", "session_id", "window_end_s"]
    )


def metric_row(
    data: pd.DataFrame,
    learner_name: str,
    contrast: str,
    positive_protocols: set[str],
) -> dict[str, object]:
    selected = data.loc[
        data["protocol"].isin(positive_protocols | {"tsst_stress"})
    ].copy()
    selected["label"] = selected["protocol"].isin(positive_protocols).astype(int)
    probability = selected["probability"].to_numpy()
    label = selected["label"].to_numpy()
    prediction = probability >= 0.5
    subject_auc = []
    for _, subject in selected.groupby("subject_id"):
        if subject["label"].nunique() == 2:
            subject_auc.append(roc_auc_score(subject["label"], subject["probability"]))
    return {
        "learner": learner_name,
        "contrast": contrast,
        "rows": len(selected),
        "subjects": selected["subject_id"].nunique(),
        "positive_prevalence": float(label.mean()),
        "auc": float(roc_auc_score(label, probability)),
        "average_precision": float(average_precision_score(label, probability)),
        "accuracy_at_0_5": float(accuracy_score(label, prediction)),
        "balanced_accuracy_at_0_5": float(balanced_accuracy_score(label, prediction)),
        "brier": float(brier_score_loss(label, probability)),
        "subject_auc_median": float(np.median(subject_auc)),
        "subject_auc_min": float(np.min(subject_auc)),
        "subject_auc_max": float(np.max(subject_auc)),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw = load_features()
    labels = protocol_labels()
    wesad = raw.loc[raw["dataset_id"].astype(str).eq("wesad")].merge(
        labels,
        on=["dataset_id", "subject_id", "session_id", "window_end_s"],
        how="left",
        validate="many_to_one",
    )
    train = derive_targets(raw).loc[
        ~raw["dataset_id"].astype(str).eq("wesad")
    ].copy()
    target = "parasympathetic_recovery_proxy"
    train = train.loc[train[target].notna()].copy()
    features = select_features(raw, "chest_reference", "autonomic_space")

    predictions = []
    metrics = []
    for learner_name in ("portable_logistic", "random_forest", "gradient_boosting"):
        model = learner(learner_name)
        model.fit(train[features], train[target].astype(int))
        scored = wesad[
            ["window_s", "subject_id", "session_id", "window_end_s", "protocol"]
        ].copy()
        scored["learner"] = learner_name
        scored["probability"] = model.predict_proba(wesad[features])[:, 1]
        predictions.append(scored)
        metrics.append(
            metric_row(
                scored,
                learner_name,
                "meditation_vs_tsst",
                {"medi_1", "medi_2"},
            )
        )
        metrics.append(
            metric_row(
                scored,
                learner_name,
                "meditation_or_baseline_vs_tsst",
                {"medi_1", "medi_2", "base"},
            )
        )

    prediction_frame = pd.concat(predictions, ignore_index=True)
    metric_frame = pd.DataFrame(metrics)
    strict = prediction_frame.loc[
        prediction_frame["protocol"].isin({"medi_1", "medi_2", "tsst_stress"})
    ].copy()
    strict["label"] = strict["protocol"].isin({"medi_1", "medi_2"}).astype(int)
    window_metrics = (
        strict.groupby(["learner", "window_s"])
        .apply(
            lambda group: pd.Series(
                {
                    "rows": len(group),
                    "auc": roc_auc_score(group["label"], group["probability"]),
                    "balanced_accuracy_at_0_5": balanced_accuracy_score(
                        group["label"], group["probability"] >= 0.5
                    ),
                    "meditation_probability_median": group.loc[
                        group["label"].eq(1), "probability"
                    ].median(),
                    "stress_probability_median": group.loc[
                        group["label"].eq(0), "probability"
                    ].median(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    protocol_summary = (
        prediction_frame.groupby(["learner", "protocol"], dropna=False)["probability"]
        .agg(rows="size", mean="mean", median="median", q25=lambda x: x.quantile(0.25), q75=lambda x: x.quantile(0.75))
        .reset_index()
    )
    metric_frame.to_csv(OUTPUT / "metrics.csv", index=False)
    window_metrics.to_csv(OUTPUT / "window_metrics.csv", index=False)
    protocol_summary.to_csv(OUTPUT / "protocol_probability_summary.csv", index=False)
    prediction_frame.to_csv(OUTPUT / "predictions.csv", index=False)
    (OUTPUT / "manifest.json").write_text(
        json.dumps(
            {
                "training": "all current weak-label rows except WESAD",
                "test": "WESAD protocol labels never used for training",
                "profile": "chest_reference-compatible features available in WESAD",
                "arm": "autonomic_space",
                "features": len(features),
                "limitations": [
                    "meditation and baseline are protocol contexts, not direct PNS measurements",
                    "current target construction is a physiology-derived PNS proxy",
                    "sampled temporal-feature anchors are used rather than every WESAD second",
                    "0.5 accuracy uses an uncalibrated threshold",
                ],
            },
            indent=2,
        )
    )
    print(metric_frame.to_string(index=False))
    print("\nProtocol probabilities")
    print(protocol_summary.to_string(index=False))


if __name__ == "__main__":
    main()
