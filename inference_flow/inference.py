#!/usr/bin/env python3
"""Minimal scoring helpers for the frozen Phase 3 artifact.

The inference service can wrap these functions in its own HTTP/task surface. The expected input
is already-windowed Phase 3 style feature rows. Raw watch samples still need the
server-side feeder step described in `PainThermometer/Docs/ENDPOINT_SPEC.md`.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


DEFAULT_MODEL = Path(__file__).resolve().parent / "models" / "pain-thermometer-phase3-final-v1" / "model.joblib"


def _clean_row(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    return out[columns]


def _predict_classifier(model_payload: dict[str, Any], frame: pd.DataFrame) -> float:
    columns = model_payload["columns"]
    x = _clean_row(frame, columns)
    return float(model_payload["model"].predict_proba(x)[:, 1][0])


def _predict_regressor(model_payload: dict[str, Any], frame: pd.DataFrame) -> float:
    columns = model_payload["columns"]
    x = _clean_row(frame, columns)
    return float(model_payload["model"].predict(x)[0])


def block_state(pain_likelihood: float | None, confidence: float | None, threshold: float) -> str:
    if pain_likelihood is None or confidence is None:
        return "empty"
    if confidence < 0.5:
        return "uncertain"
    return "filled" if pain_likelihood >= threshold else "low"


def score_feature_row(row: dict[str, Any], model_path: str | Path = DEFAULT_MODEL, prior_scores: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    artifact = joblib.load(model_path)
    config = artifact["config"]
    frame = pd.DataFrame([row])

    pain_likelihood = _predict_classifier(artifact["models"]["pain_high_4_plus"], frame)
    pain_nrs = max(0.0, min(10.0, _predict_regressor(artifact["models"]["pain_nrs_regression"], frame)))
    stress_likelihood = _predict_classifier(artifact["models"]["stress_binary"], frame)
    baseline_like = _predict_classifier(artifact["models"]["baseline_state_binary"], frame)
    baseline_departure = 1.0 - baseline_like

    sensors_used = []
    missing_sensor_blocks = []
    for block in ("hr", "acc", "gyro", "temperature", "spo2", "bvp", "eda", "ibi"):
        present_cols = [column for column in frame.columns if column.startswith(f"{block}__") and column.endswith("__present")]
        present = any(float(frame[column].fillna(0).iloc[0]) > 0 for column in present_cols)
        if present:
            sensors_used.append(block)
        else:
            missing_sensor_blocks.append(block)

    quality = max(0.2, 1.0 - 0.07 * len(missing_sensor_blocks))
    confidence = max(0.05, min(0.95, 0.5 * quality + 0.5 * abs(pain_likelihood - 0.5) * 2))
    threshold = float(config["flag_threshold"])

    recent = list(prior_scores or [])[-9:]
    current_block = {
        "index": 9,
        "state": block_state(pain_likelihood, confidence, threshold),
        "pain_likelihood_0_1": pain_likelihood,
        "confidence_0_1": confidence,
    }
    blocks = recent + [current_block]
    while len(blocks) < 10:
        blocks.insert(0, {"index": 0, "state": "empty", "pain_likelihood_0_1": None, "confidence_0_1": None})
    for index, block in enumerate(blocks[-10:]):
        block["index"] = index

    filled_count = sum(1 for block in blocks if block["state"] == "filled")
    pain_flag = filled_count >= 6 and confidence >= 0.5 and quality >= 0.6

    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "score_available": True,
        "latest_score": {
            "schema_version": 1,
            "run_id": row.get("run_id"),
            "device_id": row.get("device_id"),
            "model_alias": config["model_alias"],
            "model_version": config["model_version"],
            "model_family": "hist_gradient_boosting_multitask_windows",
            "feature_set": config["pain_feature_set"],
            "anchor_time_utc": row.get("anchor_time_utc") or now,
            "window_seconds": config["window_seconds"],
            "anchor_cadence_hz": config["anchor_cadence_hz"],
            "pain_likelihood_0_1": pain_likelihood,
            "pain_score_0_100": round(pain_nrs * 10),
            "pain_flag": pain_flag,
            "flag_threshold": threshold,
            "confidence_0_1": confidence,
            "quality_0_1": quality,
            "stress_likelihood_0_1": stress_likelihood,
            "baseline_departure_0_1": baseline_departure,
            "sensors_used": sensors_used,
            "missing_sensor_blocks": missing_sensor_blocks,
            "pain_blocks_10": blocks[-10:],
            "contributory_factors": [
                {
                    "factor": "missing_sensor_blocks",
                    "label": "Missing sensor blocks",
                    "direction": "reduces_confidence",
                    "strength_0_1": min(1.0, len(missing_sensor_blocks) / 8),
                    "confidence_0_1": quality,
                }
            ],
            "display": {
                "primary_text": "Pain-like pattern" if pain_flag else "No sustained pain-like pattern",
                "secondary_text": "Moderate confidence" if confidence >= 0.5 else "Low confidence",
                "color_hint": "amber" if pain_flag else "neutral",
                "filled_block_count": filled_count,
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a single Phase 3 feature row JSON file.")
    parser.add_argument("row_json")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    args = parser.parse_args()
    row = json.loads(Path(args.row_json).read_text(encoding="utf-8"))
    print(json.dumps(score_feature_row(row, args.model), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
