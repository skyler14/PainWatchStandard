#!/usr/bin/env python3
"""Convert xalentis/Stress packaged features into auxiliary feeder rows.

These rows are not direct pain labels. They are useful for Phase 2 state
regularization because the stress repo already provides derived HR/EDA windows
and a binary stress metric.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "phase_2" / "reference" / "Stress"
DEFAULT_OUTPUT = ROOT / "phase_2" / "analysis" / "outputs" / "stress_reference_feeder_rows.parquet"

FEATURE_COLUMNS = [
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


def load_csv(reference: Path, zip_name: str, csv_name: str, dataset_id: str) -> pd.DataFrame:
    with ZipFile(reference / zip_name) as archive, archive.open(csv_name) as handle:
        frame = pd.read_csv(handle)
    frame["Subject"] = frame["Subject"].astype(str)
    frame["source_prefix"] = frame["Subject"].str.extract(r"^([A-Za-z]+)", expand=False).str[0]
    frame["source_dataset"] = frame["source_prefix"].map(SOURCE_PREFIX).fillna("UNKNOWN")
    frame["dataset_id"] = dataset_id
    return frame


def to_feeder_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows = pd.DataFrame(
        {
            "dataset_id": frame["dataset_id"],
            "subject_id": frame["Subject"],
            "session_id": frame["Subject"],
            "window_start_s": frame.groupby("Subject").cumcount().astype(float),
            "window_end_s": frame.groupby("Subject").cumcount().astype(float) + 1.0,
            "window_seconds": 25.0,
            "target_hz": 1.0,
            "source_rows": 25,
            "condition": frame["source_dataset"].str.lower(),
            "record_type": "stress_reference_derived_features",
            "device": "mixed_hr_eda_wearables",
            "source_modality": "derived_hr_eda",
            "source_dataset": frame["source_dataset"],
            "aux_stress_label": pd.to_numeric(frame["metric"], errors="coerce"),
            "target_available": 0,
            "target_pain_nrs_0_10": None,
            "target_pain_min": None,
            "target_pain_max": None,
            "target_pain_count": 0,
            "target_pain_coverage": 0.0,
            "target_pain_class_3": None,
            "target_scale": None,
            "target_granularity": "none",
            "target_confidence": 0.0,
            "hr__present": 1,
            "eda__present": 1,
            "hr__valid_frac": 1.0,
            "eda__valid_frac": 1.0,
            "hr__min": pd.to_numeric(frame["hrmin"], errors="coerce"),
            "hr__max": pd.to_numeric(frame["hrmax"], errors="coerce"),
            "hr__std": pd.to_numeric(frame["hrstd"], errors="coerce"),
            "eda__min": pd.to_numeric(frame["edamin"], errors="coerce"),
            "eda__std": pd.to_numeric(frame["edastd"], errors="coerce"),
            "eda__range": pd.to_numeric(frame["edarange"], errors="coerce"),
            "hr__range": pd.to_numeric(frame["hrrange"], errors="coerce"),
            "hr__var": pd.to_numeric(frame["hrvar"], errors="coerce"),
            "eda__var": pd.to_numeric(frame["edavar"], errors="coerce"),
            "hr__kurtosis": pd.to_numeric(frame["hrkurt"], errors="coerce"),
        }
    )
    rows["hr__mean"] = (rows["hr__min"] + rows["hr__max"]) / 2.0
    rows["eda__mean"] = rows["eda__min"] + rows["eda__range"] / 2.0
    return rows


def build(reference: Path, output: Path) -> dict:
    real = load_csv(reference, "StressData.zip", "StressData.csv", "stress_reference_real")
    synthetic = load_csv(
        reference,
        "SynthesizedStressData.zip",
        "SynthesizedStressData.csv",
        "stress_reference_synthetic",
    )
    rows = pd.concat([to_feeder_rows(real), to_feeder_rows(synthetic)], ignore_index=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(output, compression="zstd", index=False)
    manifest = {
        "output": str(output),
        "rows": int(len(rows)),
        "subjects": int(rows["subject_id"].nunique()),
        "datasets": rows.groupby("dataset_id").size().reset_index(name="rows").to_dict(orient="records"),
        "note": "Auxiliary stress/state rows only; not direct pain supervision.",
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    print(json.dumps(build(Path(args.reference), Path(args.output)), indent=2))


if __name__ == "__main__":
    main()
