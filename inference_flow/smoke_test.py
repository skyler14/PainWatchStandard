#!/usr/bin/env python3
"""Smoke-test the dashboard inference artifacts.

This does not rebuild raw archives. It verifies that the dashboard branch can
consume the Phase 1/2/3 outputs, regenerate a compact PostgreSQL dump, load the
frozen model, and produce a live inference-shaped response from a Phase 3 row.
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from inference import DEFAULT_MODEL, score_feature_row


ROOT = Path(__file__).resolve().parents[1]


REQUIRED = {
    "phase1_windows": ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "window_features.parquet",
    "phase1_state_atlas": ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "state_atlas" / "baseline_state_assignments.parquet",
    "phase2_stress_rows": ROOT / "pain-thermometer-exploration" / "phase_2" / "analysis" / "outputs" / "stress_reference_feeder_rows.parquet",
    "phase3_windows": ROOT / "_normalized" / "phase3" / "target_hz=1" / "window_features.parquet",
    "phase3_metrics": ROOT / "_normalized" / "phase3" / "target_hz=1" / "baselines" / "phase3_metrics.csv",
    "full_dashboard_dump": ROOT / "_exports" / "pain_demo_postgres_phase3_all_datasets.sql.gz",
    "frozen_model": DEFAULT_MODEL,
}


def assert_exists() -> dict[str, str]:
    status = {}
    missing = []
    for name, path in REQUIRED.items():
        if path.exists():
            status[name] = str(path)
        else:
            missing.append(f"{name}: {path}")
    if missing:
        raise FileNotFoundError("Missing required artifacts:\n" + "\n".join(missing))
    return status


def gzip_check(path: Path) -> None:
    with gzip.open(path, "rb") as handle:
        while handle.read(1024 * 1024):
            pass


def run_small_export() -> Path:
    out = Path(tempfile.gettempdir()) / "pain_demo_postgres_phase3_smoke.sql.gz"
    cmd = [
        sys.executable,
        str(ROOT / "postgres_demo_export.py"),
        "--output",
        str(out),
        "--schema-name",
        "pain_demo_phase3_smoke",
        "--batch-size",
        "25000",
        "--small-sample",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    gzip_check(out)
    return out


def score_sample_row() -> dict:
    frame = pd.read_parquet(REQUIRED["phase3_windows"])
    sample = frame.loc[frame["label_family"].eq("direct_pain")].head(1)
    if sample.empty:
        sample = frame.head(1)
    row = sample.iloc[0].to_dict()
    row["run_id"] = "smoke-test-run"
    row["device_id"] = "smoke-test-device"
    return score_feature_row(row, DEFAULT_MODEL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run dashboard inference artifact smoke tests.")
    parser.add_argument("--skip-export", action="store_true", help="Skip regenerating the compact PostgreSQL dump.")
    args = parser.parse_args()

    artifacts = assert_exists()
    gzip_check(REQUIRED["full_dashboard_dump"])
    export_path = None if args.skip_export else run_small_export()
    inference_response = score_sample_row()

    payload = {
        "ok": True,
        "artifacts": artifacts,
        "small_export": str(export_path) if export_path else None,
        "inference_score_available": inference_response.get("score_available"),
        "inference_model_alias": inference_response["latest_score"]["model_alias"],
        "inference_pain_blocks": len(inference_response["latest_score"]["pain_blocks_10"]),
        "inference_pain_likelihood_0_1": inference_response["latest_score"]["pain_likelihood_0_1"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
