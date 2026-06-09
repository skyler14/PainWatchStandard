#!/usr/bin/env python3
"""Export compact Phase 3 CSV for R-only analysis fallback."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "_normalized" / "phase3" / "target_hz=1" / "window_features.parquet"
OUTPUT = Path(__file__).resolve().parents[1] / "outputs" / "phase3_r_compact.csv"

CORE_COLUMNS = [
    "dataset_id",
    "subject_id",
    "session_id",
    "label_family",
    "source_dataset",
    "condition",
    "baseline_state_bin",
    "target_pain_nrs_0_10",
    "target_stress_binary",
    "target_activity_binary",
    "target_baseline_binary",
    "target_confidence",
    "baseline_abs_delta_mean",
    "baseline_l2_delta",
]

SENSOR_COLUMNS = [
    "bvp__mean",
    "hr__mean",
    "eda__mean",
    "temperature__mean",
    "acc__mag__mean",
    "respiration__mean",
    "emg__mean",
    "grip__mean",
    "bvp__present",
    "hr__present",
    "eda__present",
    "temperature__present",
    "acc__present",
    "respiration__present",
    "emg__present",
    "grip__present",
]


def main() -> None:
    available = set(pq.ParquetFile(INPUT).schema.names)
    columns = [column for column in CORE_COLUMNS + SENSOR_COLUMNS if column in available]
    frame = pd.read_parquet(INPUT, columns=columns)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT, index=False)
    print(f"wrote {OUTPUT} rows={len(frame)} columns={len(frame.columns)}")


if __name__ == "__main__":
    main()
