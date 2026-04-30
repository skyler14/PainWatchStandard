#!/usr/bin/env python3
"""Reference analysis for xalentis/Stress packaged CSVs.

The original repository is R-based and this environment does not have Rscript.
This script runs a sklearn equivalent over the two bundled derived datasets:
StressData.zip and SynthesizedStressData.zip.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference" / "Stress"
OUTPUT = ROOT / "analysis" / "outputs"

FEATURES = [
    "hrrange",
    "hrvar",
    "hrstd",
    "hrmin",
    "edarange",
    "edastd",
    "edavar",
    "hrkurt",
    "edamin",
    "hrmax",
]

SOURCE_PREFIX = {
    "N": "NEURO",
    "S": "SWELL",
    "W": "WESAD",
    "U": "UBFC",
    "X": "SYNTHETIC",
}


@dataclass(frozen=True)
class ModelSpec:
    name: str
    random_state: int = 42


def load_zipped_csv(zip_path: Path, csv_name: str) -> pd.DataFrame:
    with ZipFile(zip_path) as archive, archive.open(csv_name) as handle:
        frame = pd.read_csv(handle)
    frame["Subject"] = frame["Subject"].astype(str)
    frame["metric"] = pd.to_numeric(frame["metric"], errors="coerce").astype(int)
    frame["source_prefix"] = frame["Subject"].str.extract(r"^([A-Za-z]+)", expand=False).str[0]
    frame["source_dataset"] = frame["source_prefix"].map(SOURCE_PREFIX).fillna("UNKNOWN")
    return frame


def make_model(spec: ModelSpec):
    if spec.name == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            learning_rate=0.06,
            max_iter=180,
            l2_regularization=0.05,
            max_leaf_nodes=31,
            early_stopping=True,
            random_state=spec.random_state,
        )
    if spec.name == "random_forest":
        return RandomForestClassifier(
            n_estimators=220,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            random_state=spec.random_state,
            n_jobs=-1,
        )
    raise ValueError(f"Unknown model: {spec.name}")


def evaluate(y_true: np.ndarray, score: np.ndarray, threshold: float = 0.5) -> dict[str, float | None]:
    pred = (score >= threshold).astype(int)
    return {
        "rows": int(len(y_true)),
        "prevalence": float(np.mean(y_true)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, score)) if np.unique(y_true).size > 1 else None,
        "average_precision": (
            float(average_precision_score(y_true, score)) if np.unique(y_true).size > 1 else None
        ),
    }


def fit_eval(train: pd.DataFrame, test: pd.DataFrame, model_spec: ModelSpec) -> dict[str, float | None]:
    model = make_model(model_spec)
    model.fit(train[FEATURES], train["metric"])
    if hasattr(model, "predict_proba"):
        score = model.predict_proba(test[FEATURES])[:, 1]
    else:
        score = model.predict(test[FEATURES])
    return evaluate(test["metric"].to_numpy(), score)


def subject_holdout(frame: pd.DataFrame, dataset_name: str, model_specs: list[ModelSpec]) -> list[dict]:
    rows = []
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_idx, test_idx = next(splitter.split(frame, groups=frame["Subject"]))
    train = frame.iloc[train_idx]
    test = frame.iloc[test_idx]
    for spec in model_specs:
        metrics = fit_eval(train, test, spec)
        rows.append(
            {
                "experiment": "subject_holdout",
                "train_source": dataset_name,
                "test_source": dataset_name,
                "model": spec.name,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "train_subjects": int(train["Subject"].nunique()),
                "test_subjects": int(test["Subject"].nunique()),
                **metrics,
            }
        )
    return rows


def source_transfer(real: pd.DataFrame, synth: pd.DataFrame, model_specs: list[ModelSpec]) -> list[dict]:
    rows = []
    real_sources = sorted(real["source_dataset"].dropna().unique())
    for heldout in real_sources:
        test = real.loc[real["source_dataset"] == heldout].copy()
        train_real_other = real.loc[real["source_dataset"] != heldout].copy()
        train_synth = synth.copy()
        train_combined = pd.concat([train_real_other, train_synth], ignore_index=True)
        train_sets = {
            "real_other_sources": train_real_other,
            "synthetic_only": train_synth,
            "real_other_plus_synthetic": train_combined,
        }
        for train_name, train in train_sets.items():
            for spec in model_specs:
                metrics = fit_eval(train, test, spec)
                rows.append(
                    {
                        "experiment": "source_transfer",
                        "train_source": train_name,
                        "test_source": heldout,
                        "model": spec.name,
                        "train_rows": int(len(train)),
                        "test_rows": int(len(test)),
                        "train_subjects": int(train["Subject"].nunique()),
                        "test_subjects": int(test["Subject"].nunique()),
                        **metrics,
                    }
                )
    return rows


def lift_table(metrics: pd.DataFrame) -> pd.DataFrame:
    transfer = metrics.loc[metrics["experiment"].eq("source_transfer")].copy()
    rows = []
    for (test_source, model), group in transfer.groupby(["test_source", "model"]):
        base = group.loc[group["train_source"].eq("real_other_sources")]
        synth = group.loc[group["train_source"].eq("synthetic_only")]
        combined = group.loc[group["train_source"].eq("real_other_plus_synthetic")]
        if base.empty or synth.empty or combined.empty:
            continue
        base_row = base.iloc[0]
        synth_row = synth.iloc[0]
        combined_row = combined.iloc[0]
        rows.append(
            {
                "test_source": test_source,
                "model": model,
                "base_real_other_auc": base_row["roc_auc"],
                "synthetic_auc": synth_row["roc_auc"],
                "combined_auc": combined_row["roc_auc"],
                "synthetic_auc_lift": synth_row["roc_auc"] - base_row["roc_auc"],
                "combined_auc_lift": combined_row["roc_auc"] - base_row["roc_auc"],
                "base_real_other_bal_acc": base_row["balanced_accuracy"],
                "synthetic_bal_acc": synth_row["balanced_accuracy"],
                "combined_bal_acc": combined_row["balanced_accuracy"],
                "synthetic_bal_acc_lift": synth_row["balanced_accuracy"] - base_row["balanced_accuracy"],
                "combined_bal_acc_lift": combined_row["balanced_accuracy"] - base_row["balanced_accuracy"],
            }
        )
    return pd.DataFrame(rows).sort_values(["model", "test_source"])


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    real = load_zipped_csv(REFERENCE / "StressData.zip", "StressData.csv")
    synth = load_zipped_csv(REFERENCE / "SynthesizedStressData.zip", "SynthesizedStressData.csv")
    model_specs = [ModelSpec("hist_gradient_boosting"), ModelSpec("random_forest")]

    rows = []
    rows.extend(subject_holdout(real, "StressData", model_specs))
    rows.extend(subject_holdout(synth, "SynthesizedStressData", model_specs))
    rows.extend(source_transfer(real, synth, model_specs))
    metrics = pd.DataFrame(rows)
    lifts = lift_table(metrics)

    metrics.to_csv(OUTPUT / "stress_reference_metrics.csv", index=False)
    lifts.to_csv(OUTPUT / "stress_reference_lifts.csv", index=False)

    audit = {
        "real_rows": int(len(real)),
        "synthetic_rows": int(len(synth)),
        "real_subjects": int(real["Subject"].nunique()),
        "synthetic_subjects": int(synth["Subject"].nunique()),
        "real_by_source": real.groupby("source_dataset").agg(
            rows=("metric", "size"),
            subjects=("Subject", "nunique"),
            prevalence=("metric", "mean"),
        ).reset_index().to_dict(orient="records"),
        "synthetic_prevalence": float(synth["metric"].mean()),
        "features": FEATURES,
        "models": [asdict(spec) for spec in model_specs],
    }
    (OUTPUT / "stress_reference_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps({"audit": audit, "metrics": str(OUTPUT / "stress_reference_metrics.csv"), "lifts": str(OUTPUT / "stress_reference_lifts.csv")}, indent=2))


if __name__ == "__main__":
    main()
