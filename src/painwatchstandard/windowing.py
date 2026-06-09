"""Causal trailing-window feature builder."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from painwatchstandard.sensors import SENSOR_BLOCKS, sensor_block_features


CONTEXT_COLUMNS = (
    "condition",
    "label_family",
    "pain_type",
    "device",
    "cohort",
    "record_type",
    "baseline_pair_session_id",
    "pain_protocol_kind",
    "aux_state_label",
    "target_stress_binary",
    "target_stress_score_0_10",
    "target_stress_score_mean_0_10",
    "survey_age",
    "survey_gender",
    "survey_sleep_hours_avg",
    "survey_sleep_hours_before_test",
    "survey_daily_stress_ordinal",
    "survey_chronic_pain_flag",
    "survey_regular_medication_flag",
    "survey_pain_context_score",
    "survey_pain_type",
    "workbook_age",
    "workbook_sex",
    "workbook_diagnosis",
    "workbook_pain_rest",
    "workbook_pain_exercise",
    "workbook_exercise_duration_text",
    "wesad_protocol_segment",
    "wesad_protocol_start_s",
    "wesad_protocol_end_s",
)


@dataclass(frozen=True)
class WindowConfig:
    target_hz: float = 1.0
    window_seconds: float = 30.0
    include_partial_windows: bool = False
    min_window_rows: int = 2

    @property
    def step_seconds(self) -> float:
        return 1.0 / self.target_hz


def validate_window_config(config: WindowConfig) -> None:
    if not 1.0 <= config.target_hz <= 10.0:
        raise ValueError("target_hz must be between 1 and 10")
    if config.window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    if config.min_window_rows < 1:
        raise ValueError("min_window_rows must be at least 1")


def make_window_anchors(session: pd.DataFrame, config: WindowConfig) -> np.ndarray:
    validate_window_config(config)
    times = pd.to_numeric(session["sample_offset_s"], errors="coerce").dropna()
    if times.empty:
        return np.array([], dtype=float)
    min_time = float(times.min())
    max_time = float(times.max())
    first_anchor = min_time if config.include_partial_windows else min_time + config.window_seconds
    if first_anchor > max_time:
        return np.array([], dtype=float)
    count = int(math.floor((max_time - first_anchor) / config.step_seconds)) + 1
    return first_anchor + np.arange(count, dtype=float) * config.step_seconds


def _first_valid(series: pd.Series) -> Any:
    valid = series.dropna()
    if valid.empty:
        return None
    value = valid.iloc[0]
    if isinstance(value, np.generic):
        return value.item()
    return value


def aggregate_pain_labels(window: pd.DataFrame) -> dict[str, Any]:
    pain = pd.to_numeric(window.get("pain_intensity", pd.Series(dtype=float)), errors="coerce").dropna()
    return {
        "target_available": int(not pain.empty),
        "target_pain_nrs_0_10": float(pain.mean()) if not pain.empty else None,
        "target_pain_min": float(pain.min()) if not pain.empty else None,
        "target_pain_max": float(pain.max()) if not pain.empty else None,
        "target_pain_count": int(pain.shape[0]),
        "target_pain_coverage": float(pain.shape[0] / max(len(window), 1)),
    }


def build_windows_for_session(session: pd.DataFrame, config: WindowConfig) -> pd.DataFrame:
    validate_window_config(config)
    if session.empty:
        return pd.DataFrame()
    session = session.sort_values("sample_offset_s", kind="mergesort").reset_index(drop=True).copy()
    if {"acc_x", "acc_y", "acc_z"}.issubset(session.columns) and "acc_mag" not in session.columns:
        session["acc_mag"] = np.sqrt(session["acc_x"] ** 2 + session["acc_y"] ** 2 + session["acc_z"] ** 2)
    anchors = make_window_anchors(session, config)
    times = session["sample_offset_s"].to_numpy(dtype=float)
    rows: list[dict[str, Any]] = []
    for anchor in anchors:
        start = anchor - config.window_seconds
        if config.include_partial_windows:
            start = max(float(session["sample_offset_s"].min()), start)
        left = int(np.searchsorted(times, start, side="right"))
        right = int(np.searchsorted(times, anchor, side="right"))
        window = session.iloc[left:right]
        if len(window) < config.min_window_rows:
            continue
        row: dict[str, Any] = {
            "dataset_id": _first_valid(window["dataset_id"]) if "dataset_id" in window else None,
            "subject_id": _first_valid(window["subject_id"]) if "subject_id" in window else None,
            "session_id": _first_valid(window["session_id"]) if "session_id" in window else None,
            "window_start_s": float(start),
            "window_end_s": float(anchor),
            "window_seconds": float(anchor - start),
            "target_hz": float(config.target_hz),
            "source_rows": int(len(window)),
        }
        for column in CONTEXT_COLUMNS:
            if column in window:
                row[column] = _first_valid(window[column])
        for block, columns in SENSOR_BLOCKS.items():
            row.update(sensor_block_features(window, block, columns))
        row.update(aggregate_pain_labels(window))
        rows.append(row)
    return pd.DataFrame(rows)
