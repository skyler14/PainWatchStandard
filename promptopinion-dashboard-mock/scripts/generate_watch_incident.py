#!/usr/bin/env python3
"""Generate a deterministic watch-like incident and score it with the trained ensemble."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "inference_flow" / "models" / "pain-thermometer-dropout-ensemble" / "model.joblib"
OUTPUT_PATH = ROOT / "promptopinion-dashboard-mock" / "src" / "data" / "generatedIncident.json"
RUN_ID = "inc_watch_2026_05_11_001"
DEVICE_ID = "watch_test_patient_series_6"
START = datetime(2026, 5, 11, 16, 42, 18, tzinfo=timezone.utc)


def score_values(model: Any, x: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(x)[:, 1]
    if hasattr(model, "decision_function"):
        scores = model.decision_function(x)
        return 1.0 / (1.0 + np.exp(-np.clip(scores, -50, 50)))
    return model.predict(x)


def ensemble_score(artifact: dict[str, Any], row: dict[str, float | int | None]) -> float:
    view = artifact["views"]["watch_friendly"]
    columns = view["columns"]
    frame = pd.DataFrame([{column: row.get(column, np.nan) for column in columns}], columns=columns)
    scores = [score_values(model, frame)[0] for model in view["members"].values()]
    return float(np.mean(scores))


def random_walk(start: float, drift: float, noise: float, count: int, rng: np.random.Generator) -> np.ndarray:
    steps = rng.normal(drift, noise, count)
    return start + np.cumsum(steps)


def slope_per_s(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    return float((values[-1] - values[0]) / max(1, len(values) - 1))


def peak_count(values: np.ndarray) -> int:
    if len(values) < 3:
        return 0
    center = values[1:-1]
    return int(np.sum((center > values[:-2]) & (center > values[2:])))


def stats(prefix: str, values: np.ndarray) -> dict[str, float]:
    return {
        f"{prefix}__present": 1.0,
        f"{prefix}__valid_count": float(len(values)),
        f"{prefix}__valid_frac": 1.0,
        f"{prefix}__mean": float(np.mean(values)),
        f"{prefix}__std": float(np.std(values)),
        f"{prefix}__min": float(np.min(values)),
        f"{prefix}__max": float(np.max(values)),
        f"{prefix}__last": float(values[-1]),
        f"{prefix}__slope_per_s": slope_per_s(values),
        f"{prefix}__peak_count": float(peak_count(values)),
    }


def baseline_fields(prefix: str, values: np.ndarray, baseline_mean: float, baseline_std: float) -> dict[str, float]:
    mean = float(np.mean(values))
    std = max(1e-6, baseline_std)
    return {
        f"{prefix}__mean__baseline_mean": baseline_mean,
        f"{prefix}__mean__baseline_std": baseline_std,
        f"{prefix}__mean__delta_from_baseline": mean - baseline_mean,
        f"{prefix}__mean__z_from_baseline": (mean - baseline_mean) / std,
    }


def build_feature_row(samples: list[dict[str, float | str]]) -> tuple[dict[str, float], dict[str, float]]:
    arrays = {
        "bvp": np.array([float(sample["bvp"]) for sample in samples]),
        "temperature": np.array([float(sample["temperature"]) for sample in samples]),
        "acc_x": np.array([float(sample["acc_x"]) for sample in samples]),
        "acc_y": np.array([float(sample["acc_y"]) for sample in samples]),
        "acc_z": np.array([float(sample["acc_z"]) for sample in samples]),
    }
    arrays["acc__mag"] = np.sqrt(arrays["acc_x"] ** 2 + arrays["acc_y"] ** 2 + arrays["acc_z"] ** 2)

    baselines = {
        "bvp": (0.58, 0.08),
        "temperature": (33.2, 0.22),
        "acc_x": (0.02, 0.05),
        "acc_y": (0.01, 0.05),
        "acc_z": (0.98, 0.06),
        "acc__mag": (0.99, 0.07),
    }

    row: dict[str, float] = {}
    for prefix, values in arrays.items():
        row.update(stats(prefix, values))
        mean, std = baselines[prefix]
        row.update(baseline_fields(prefix, values, mean, std))

    row.update(
        {
            "acc__present": 1.0,
            "acc__valid_count": float(len(samples)),
            "acc__valid_frac": 1.0,
            "acc__stillness_frac": float(np.mean(arrays["acc__mag"] < 1.05)),
            "hr__present": 1.0,
            "hr__valid_count": float(len(samples)),
            "hr__valid_frac": 1.0,
            "spo2__present": 1.0,
            "spo2__valid_count": float(len(samples)),
            "spo2__valid_frac": 1.0,
            "ibi__present": 1.0,
            "ibi__valid_count": float(len(samples)),
            "ibi__valid_frac": 1.0,
            "ecg__present": 0.0,
            "ecg__valid_count": 0.0,
            "ecg__valid_frac": 0.0,
            "gyro__present": 1.0,
            "gyro__valid_count": float(len(samples)),
            "gyro__valid_frac": 1.0,
        }
    )

    baseline_z = [
        abs(row["bvp__mean__z_from_baseline"]),
        abs(row["temperature__mean__z_from_baseline"]),
        abs(row["acc_x__mean__z_from_baseline"]),
        abs(row["acc_y__mean__z_from_baseline"]),
        abs(row["acc_z__mean__z_from_baseline"]),
        abs(row["acc__mag__mean__z_from_baseline"]),
    ]
    row.update(
        {
            "baseline_abs_delta_mean": float(np.mean(baseline_z)),
            "baseline_abs_delta_max": float(np.max(baseline_z)),
            "baseline_feature_count": float(len(baseline_z)),
            "baseline_missing": 0.0,
            "state_cluster_id": 2.0,
            "baseline_l2_delta": float(np.sqrt(np.sum(np.square(baseline_z)))),
            "baseline_anchor_available": 1.0,
        }
    )

    baseline_lookup = {key: value[0] for key, value in baselines.items()}
    return row, baseline_lookup


def neutralize_block(row: dict[str, float], block: str, baseline_lookup: dict[str, float]) -> dict[str, float]:
    out = dict(row)
    prefixes = {
        "bvp": ["bvp"],
        "temperature": ["temperature"],
        "motion": ["acc_x", "acc_y", "acc_z", "acc__mag", "acc"],
        "availability": ["hr", "spo2", "ibi", "ecg", "gyro"],
        "baseline": ["baseline"],
    }[block]

    for column in list(out):
        if block == "baseline":
            if "baseline" in column or column in {"baseline_abs_delta_mean", "baseline_abs_delta_max", "baseline_l2_delta", "baseline_missing", "baseline_anchor_available"}:
                out[column] = 0.0
            if column == "baseline_feature_count":
                out[column] = row[column]
            continue
        if any(column.startswith(f"{prefix}__") for prefix in prefixes):
            if column.endswith("__present") or column.endswith("__valid_count") or column.endswith("__valid_frac"):
                out[column] = 0.0
            elif column.endswith("__baseline_mean"):
                out[column] = row[column]
            elif column.endswith("__baseline_std"):
                out[column] = row[column]
            elif column.endswith("__delta_from_baseline") or column.endswith("__z_from_baseline"):
                out[column] = 0.0
            elif "__mean" in column:
                sensor = column.split("__mean", 1)[0]
                out[column] = baseline_lookup.get(sensor, 0.0)
            else:
                out[column] = 0.0
    return out


def generate() -> dict[str, Any]:
    rng = np.random.default_rng(78)
    count = 100
    seconds = np.arange(count)
    pain_ramp = 1 / (1 + np.exp(-(seconds - 45) / 7))

    hr = random_walk(74, 0.02, 0.34, count, rng) + pain_ramp * 23
    bvp = random_walk(0.55, 0.0005, 0.015, count, rng) + pain_ramp * 0.16
    respiration = random_walk(15.0, 0.01, 0.08, count, rng) + pain_ramp * 5.0
    temperature = random_walk(33.1, 0.001, 0.012, count, rng) + pain_ramp * 0.42
    spo2 = np.clip(random_walk(97.2, -0.002, 0.03, count, rng) - pain_ramp * 0.45, 94.5, 99.2)
    ibi = 60000 / np.clip(hr, 45, 145)
    acc_x = random_walk(0.01, 0.0002, 0.01, count, rng) + pain_ramp * 0.12
    acc_y = random_walk(0.02, 0.0001, 0.012, count, rng) + pain_ramp * 0.08
    acc_z = random_walk(0.98, 0.0002, 0.012, count, rng) + np.sin(seconds / 9) * 0.04 + pain_ramp * 0.10
    gyro = np.abs(random_walk(0.02, 0.0001, 0.006, count, rng)) + pain_ramp * 0.09

    samples = []
    for index in range(count):
        samples.append(
            {
                "t": (START + timedelta(seconds=int(index))).isoformat().replace("+00:00", "Z"),
                "hr": round(float(hr[index]), 2),
                "bvp": round(float(bvp[index]), 4),
                "respiration": round(float(respiration[index]), 2),
                "temperature": round(float(temperature[index]), 3),
                "spo2": round(float(spo2[index]), 2),
                "ibi": round(float(ibi[index]), 2),
                "acc_x": round(float(acc_x[index]), 4),
                "acc_y": round(float(acc_y[index]), 4),
                "acc_z": round(float(acc_z[index]), 4),
                "gyro": round(float(gyro[index]), 4),
            }
        )

    row, baseline_lookup = build_feature_row(samples[-30:])
    artifact = joblib.load(MODEL_PATH)
    score = ensemble_score(artifact, row)

    blocks = ["bvp", "temperature", "motion", "availability", "baseline"]
    contributions = []
    for block in blocks:
        neutral_score = ensemble_score(artifact, neutralize_block(row, block, baseline_lookup))
        delta = max(0.0, score - neutral_score)
        contributions.append(
            {
                "factor": block,
                "label": {
                    "bvp": "BVP pulse waveform",
                    "temperature": "Wrist temperature",
                    "motion": "Acceleration and motion",
                    "availability": "Sensor availability flags",
                    "baseline": "Baseline departure fields",
                }[block],
                "score_drop_0_1": round(delta, 4),
                "strength_0_1": 0.0,
                "method": "trained_ensemble_sensor_block_perturbation",
            }
        )
    total_delta = sum(item["score_drop_0_1"] for item in contributions) or 1.0
    for item in contributions:
        item["strength_0_1"] = round(item["score_drop_0_1"] / total_delta, 4)
    contributions.sort(key=lambda item: item["score_drop_0_1"], reverse=True)

    biometric_rows = [
        ("Heart rate", "watch.hr", f"{np.mean(hr[-30:]):.1f} bpm", (np.mean(hr[-30:]) - 74) / 9, "Captured; not a magnitude feature in this ensemble"),
        ("BVP pulse waveform", "watch.bvp", f"{np.mean(bvp[-30:]):.3f}", row["bvp__mean__z_from_baseline"], "Model feature block"),
        ("Respiratory rate", "watch.respiration", f"{np.mean(respiration[-30:]):.1f} rpm", (np.mean(respiration[-30:]) - 15) / 2.5, "Captured for dashboard context"),
        ("Wrist temperature", "watch.temperature", f"{np.mean(temperature[-30:]):.2f} C", row["temperature__mean__z_from_baseline"], "Model feature block"),
        ("Motion magnitude", "watch.acc", f"{row['acc__mag__mean']:.2f} g", row["acc__mag__mean__z_from_baseline"], "Model feature block"),
        ("SpO2", "watch.spo2", f"{np.mean(spo2[-30:]):.1f}%", (np.mean(spo2[-30:]) - 97.2) / 1.2, "Availability feature in this ensemble"),
    ]

    pain_score = int(round(score * 100))
    positive_windows = max(7, min(10, int(round(score * 10))))
    incident = {
        "id": RUN_ID,
        "startedAt": START.isoformat().replace("+00:00", "Z"),
        "durationMinutes": 8,
        "sourceDevice": "PainThermometer Watch",
        "model": {
            "alias": artifact["config"]["model_alias"],
            "version": artifact["config"]["model_version"],
            "view": "watch_friendly",
            "contributionMethod": "trained_ensemble_sensor_block_perturbation",
        },
        "activation": {
            "positiveWindows": positive_windows,
            "windowCount": 10,
            "triggerScore": round(score, 4),
        },
        "survey": {
            "id": "survey_gpm_001",
            "status": "completed",
            "finalGpmScore": 26,
            "adjustedGpmScore": 31,
            "adjustmentReason": "Interview evidence added sleep interruption and help-needed context after the initial numeric answers.",
            "questions": [
                {
                    "id": "what_happened",
                    "question": "What happened around when the pain started?",
                    "answer": "I stood up from the kitchen chair and felt my left knee tighten sharply.",
                    "confidence": 0.94,
                },
                {"id": "location", "question": "Where did you feel it most?", "answer": "Left knee, mostly around the inside edge.", "confidence": 0.91},
                {"id": "quality", "question": "What did it feel like?", "answer": "Sharp at first, then dull and throbbing.", "confidence": 0.86},
                {"id": "gpm_today_0_10", "question": "On a zero to ten scale, how bad is it today?", "answer": "Six out of ten during the incident, four after resting.", "confidence": 0.82},
                {"id": "sleep_trouble", "question": "Has it been interfering with sleep?", "answer": "Yes, I woke up twice last night when turning over.", "confidence": 0.79},
            ],
        },
        "biometrics": [
            {"metric": metric, "sensor": sensor, "value": value, "zScore": round(float(z), 2), "interpretation": interpretation}
            for metric, sensor, value, z, interpretation in biometric_rows
        ],
        "scores": [
            {"name": "Pain likelihood", "score": pain_score, "scale": "0-100", "severity": "high" if pain_score >= 65 else "moderate", "note": "From trained watch-friendly ensemble"},
            {"name": "GPM raw", "score": 26, "scale": "0-42", "severity": "moderate", "note": "Completed survey total"},
            {"name": "GPM adjusted", "score": 31, "scale": "0-100", "severity": "moderate", "note": "Adjusted after interview testimony"},
            {"name": "Baseline departure", "score": int(round(min(1, row["baseline_abs_delta_mean"] / 4) * 100)), "scale": "0-100", "severity": "moderate", "note": "Computed from supplied baseline fields"},
        ],
        "contributions": contributions,
        "timeseries": samples,
        "chat": [
            {"id": "msg_1", "speaker": "assistant", "time": "09:43", "text": "I noticed a pain signal. What happened around when the pain started?"},
            {"id": "msg_2", "speaker": "patient", "time": "09:44", "text": "I stood up from the kitchen chair and my left knee tightened sharply."},
            {"id": "msg_3", "speaker": "assistant", "time": "09:44", "text": "Where did you feel it most?"},
            {"id": "msg_4", "speaker": "patient", "time": "09:45", "text": "Inside edge of the left knee. It was sharp first, then a dull throb."},
            {"id": "msg_5", "speaker": "assistant", "time": "09:46", "text": "Has it been interfering with sleep or making you need help?"},
            {"id": "msg_6", "speaker": "patient", "time": "09:47", "text": "Yes, sleep was bad last night. I also asked my daughter to help with groceries."},
        ],
        "summaries": [
            "Incident is consistent with a left-knee pain flare during sit-to-stand transition. The trained watch-friendly ensemble crossed the sustained activation threshold.",
            "Survey adjustment increased because the interview added sleep disruption and help-needed impact, moving the session into moderate impact.",
        ],
    }
    return incident


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(generate(), indent=2), encoding="utf-8")
    print(OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
