"""Sensor block feature extraction."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd


SENSOR_BLOCKS: dict[str, tuple[str, ...]] = {
    "bvp": ("bvp",),
    "bvp_rb": ("bvp_rb",),
    "eda": ("eda",),
    "eda_rb": ("eda_rb",),
    "temperature": ("temperature",),
    "acc": ("acc_x", "acc_y", "acc_z"),
    "hr": ("hr",),
    "ibi": ("ibi",),
    "ecg": ("ecg",),
    "respiration": ("respiration",),
    "emg": ("emg",),
    "grip": ("grip",),
    "steps": ("steps",),
    "spo2": ("spo2",),
}


def _slope_per_second(times: np.ndarray, values: np.ndarray) -> float | None:
    mask = np.isfinite(times) & np.isfinite(values)
    if mask.sum() < 2:
        return None
    x = times[mask].astype(float)
    y = values[mask].astype(float)
    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom <= 0:
        return None
    return float(np.dot(x, y - y.mean()) / denom)


def _peak_count(values: np.ndarray) -> int:
    valid = values[np.isfinite(values)]
    if valid.size < 3:
        return 0
    spread = float(np.nanstd(valid))
    threshold = float(np.nanmean(valid)) + 0.25 * spread
    peaks = (valid[1:-1] > valid[:-2]) & (valid[1:-1] >= valid[2:]) & (valid[1:-1] > threshold)
    return int(peaks.sum())


def series_features(prefix: str, times: np.ndarray, values: np.ndarray, denominator: int) -> dict[str, Any]:
    mask = np.isfinite(values)
    valid = values[mask].astype(float)
    features: dict[str, Any] = {
        f"{prefix}__present": int(valid.size > 0),
        f"{prefix}__valid_count": int(valid.size),
        f"{prefix}__valid_frac": float(valid.size / denominator) if denominator else 0.0,
        f"{prefix}__mean": None,
        f"{prefix}__std": None,
        f"{prefix}__min": None,
        f"{prefix}__max": None,
        f"{prefix}__last": None,
        f"{prefix}__slope_per_s": None,
        f"{prefix}__peak_count": 0,
    }
    if valid.size == 0:
        if prefix == "ibi":
            features["ibi__rmssd_ms"] = None
            features["ibi__sdnn_ms"] = None
        return features
    features[f"{prefix}__mean"] = float(np.nanmean(valid))
    features[f"{prefix}__std"] = float(np.nanstd(valid, ddof=0))
    features[f"{prefix}__min"] = float(np.nanmin(valid))
    features[f"{prefix}__max"] = float(np.nanmax(valid))
    features[f"{prefix}__last"] = float(valid[-1])
    features[f"{prefix}__slope_per_s"] = _slope_per_second(times, values)
    features[f"{prefix}__peak_count"] = _peak_count(values)
    if prefix == "ibi":
        ibi_ms = valid * 1000.0
        diffs = np.diff(ibi_ms)
        features["ibi__rmssd_ms"] = float(np.sqrt(np.mean(diffs**2))) if diffs.size else None
        features["ibi__sdnn_ms"] = float(np.nanstd(ibi_ms, ddof=1)) if ibi_ms.size > 1 else None
    return features


def sensor_block_features(window: pd.DataFrame, block: str, columns: Iterable[str]) -> dict[str, Any]:
    times = window["sample_offset_s"].to_numpy(dtype=float)
    denominator = max(len(window), 1)
    available = [column for column in columns if column in window.columns]
    if not available:
        if block == "acc":
            features: dict[str, Any] = {}
            empty = np.full(len(window), np.nan)
            for prefix in ("acc_x", "acc_y", "acc_z", "acc__mag"):
                features.update(series_features(prefix, times, empty, denominator))
            features["acc__present"] = 0
            features["acc__valid_count"] = 0
            features["acc__valid_frac"] = 0.0
            features["acc__stillness_frac"] = None
            return features
        features = {
            f"{block}__present": 0,
            f"{block}__valid_count": 0,
            f"{block}__valid_frac": 0.0,
            f"{block}__mean": None,
            f"{block}__std": None,
            f"{block}__min": None,
            f"{block}__max": None,
            f"{block}__last": None,
            f"{block}__slope_per_s": None,
            f"{block}__peak_count": 0,
        }
        if block == "ibi":
            features["ibi__rmssd_ms"] = None
            features["ibi__sdnn_ms"] = None
        return features
    if block == "acc":
        features: dict[str, Any] = {}
        for axis in ("acc_x", "acc_y", "acc_z"):
            if axis in window.columns:
                values = pd.to_numeric(window[axis], errors="coerce").to_numpy(dtype=float)
            else:
                values = np.full(len(window), np.nan)
            features.update(series_features(axis, times, values, denominator))
        if "acc_mag" in window.columns:
            mag = pd.to_numeric(window["acc_mag"], errors="coerce").to_numpy(dtype=float)
        else:
            axes = [pd.to_numeric(window.get(axis, np.nan), errors="coerce").to_numpy(dtype=float) for axis in ("acc_x", "acc_y", "acc_z")]
            mag = np.sqrt(axes[0] ** 2 + axes[1] ** 2 + axes[2] ** 2)
        features.update(series_features("acc__mag", times, mag, denominator))
        valid = mag[np.isfinite(mag)]
        features["acc__present"] = int(valid.size > 0)
        features["acc__valid_count"] = int(valid.size)
        features["acc__valid_frac"] = float(valid.size / denominator)
        features["acc__stillness_frac"] = float((np.abs(np.diff(valid)) < 0.02).mean()) if valid.size > 1 else None
        return features
    values = pd.to_numeric(window[available[0]], errors="coerce").to_numpy(dtype=float)
    return series_features(block, times, values, denominator)
