"""Functional pain thermometer v1.

This method is a physiology-state display layer, not a trained pain model.
It maps one window row into a ternary balance among sympathetic activation,
parasympathetic activation/recovery, and homeostasis.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import math
from typing import Any


EPSILON = 1e-9


@dataclass(frozen=True)
class FunctionalPainV1:
    sympathetic: float
    parasympathetic: float
    homeostasis: float
    ternary_x: float
    ternary_y: float
    functional_pain_0_1: float
    recovery_0_1: float
    sensor_quality_0_1: float
    usable_sensor_count: int
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _scaled(value: Any, center: float, scale: float, invert: bool = False) -> float | None:
    number = _finite(value)
    if number is None:
        return None
    z = (number - center) / max(scale, EPSILON)
    if invert:
        z = -z
    return _clamp(0.5 + 0.25 * z)


def _robust_departure(row: Mapping[str, Any], key: str) -> float | None:
    z_key = f"{key}__robust_z_from_profile"
    delta_key = f"{key}__delta_from_profile_median"
    z = _finite(row.get(z_key))
    if z is not None:
        return _clamp(abs(z) / 3.0)
    delta = _finite(row.get(delta_key))
    if delta is not None:
        return _clamp(abs(delta) / 3.0)
    return None


def _value(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _finite(row.get(key))
        if value is not None:
            return value
    return None


def _present(row: Mapping[str, Any], prefix: str) -> bool:
    value = _finite(row.get(f"{prefix}__present"))
    if value is not None:
        return value > 0
    return any(key.startswith(f"{prefix}__") and _finite(row.get(key)) is not None for key in row)


def _mean(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    if not clean:
        return None
    return float(sum(clean) / len(clean))


def _weighted_mean(items: list[tuple[float | None, float]]) -> float | None:
    clean = [(value, weight) for value, weight in items if value is not None and weight > 0]
    if not clean:
        return None
    total = sum(weight for _, weight in clean)
    return float(sum(value * weight for value, weight in clean) / total)


def _normalize_three(sympathetic: float, parasympathetic: float, homeostasis: float) -> tuple[float, float, float]:
    values = [max(sympathetic, EPSILON), max(parasympathetic, EPSILON), max(homeostasis, EPSILON)]
    total = sum(values)
    return tuple(value / total for value in values)  # type: ignore[return-value]


def _ternary_xy(sympathetic: float, parasympathetic: float, homeostasis: float) -> tuple[float, float]:
    # Vertices: sympathetic=(0,0), parasympathetic=(1,0), homeostasis=(0.5,sqrt(3)/2).
    x = parasympathetic + 0.5 * homeostasis
    y = (math.sqrt(3.0) / 2.0) * homeostasis
    return float(x), float(y)


def functional_pain_v1(row: Mapping[str, Any]) -> FunctionalPainV1:
    """Score one window row as ternary autonomic balance.

    Inputs may be raw window features or baseline-relative features. Missing
    sensors lower quality and remove evidence; they do not create zero evidence.
    """
    notes: list[str] = []

    sensor_present = {
        "eda": _present(row, "eda"),
        "hr": _present(row, "hr"),
        "ibi": _present(row, "ibi"),
        "bvp": _present(row, "bvp"),
        "temperature": _present(row, "temperature"),
        "acc": _present(row, "acc"),
        "respiration": _present(row, "respiration"),
    }
    usable_sensor_count = sum(sensor_present.values())
    sensor_quality = _clamp(0.15 + 0.12 * usable_sensor_count)

    eda_level = _scaled(_value(row, "eda__mean", "eda__last"), center=0.5, scale=1.5)
    eda_slope = _scaled(row.get("eda__slope_per_s"), center=0.0, scale=0.02)
    eda_peaks = _scaled(row.get("eda__peak_count"), center=1.0, scale=4.0)
    hr_level = _scaled(_value(row, "hr__mean", "hr__last"), center=75.0, scale=35.0)
    bvp_instability = _scaled(row.get("bvp__std"), center=0.0, scale=35.0)
    temp_drop = _scaled(row.get("temperature__slope_per_s"), center=0.0, scale=0.03, invert=True)
    motion_load = _scaled(row.get("acc__mag__std"), center=0.03, scale=0.20)

    baseline_departure = _mean(
        [
            _robust_departure(row, "eda__mean"),
            _robust_departure(row, "hr__mean"),
            _robust_departure(row, "bvp__mean"),
            _robust_departure(row, "temperature__mean"),
            _finite(row.get("baseline_distance_l1")),
        ]
    )
    if baseline_departure is not None:
        baseline_departure = _clamp(baseline_departure)

    sympathetic_raw = _weighted_mean(
        [
            (eda_level, 1.4),
            (eda_slope, 1.1),
            (eda_peaks, 0.8),
            (hr_level, 1.0),
            (bvp_instability, 0.5),
            (temp_drop, 0.5),
            (baseline_departure, 0.9),
        ]
    )
    if sympathetic_raw is None:
        sympathetic_raw = 0.33
        notes.append("sympathetic_missing_core")

    rmssd = _scaled(row.get("ibi__rmssd_ms"), center=35.0, scale=45.0)
    sdnn = _scaled(row.get("ibi__sdnn_ms"), center=45.0, scale=55.0)
    hr_recovery = _scaled(_value(row, "hr__slope_per_s"), center=0.0, scale=0.6, invert=True)
    eda_recovery = _scaled(row.get("eda__slope_per_s"), center=0.0, scale=0.02, invert=True)
    resp_regular = _scaled(row.get("respiration__std"), center=0.0, scale=0.5, invert=True)
    pns_baseline = _mean(
        [
            _robust_departure(row, "ibi__rmssd_ms"),
            _robust_departure(row, "ibi__sdnn_ms"),
        ]
    )
    if pns_baseline is not None:
        pns_baseline = 1.0 - _clamp(pns_baseline)

    parasympathetic_raw = _weighted_mean(
        [
            (rmssd, 1.4),
            (sdnn, 0.9),
            (hr_recovery, 0.9),
            (eda_recovery, 0.6),
            (resp_regular, 0.8),
            (pns_baseline, 0.7),
        ]
    )
    if parasympathetic_raw is None:
        parasympathetic_raw = 0.33
        notes.append("parasympathetic_missing_core")

    low_departure = None if baseline_departure is None else 1.0 - baseline_departure
    low_motion = None if motion_load is None else 1.0 - motion_load
    low_arousal = 1.0 - sympathetic_raw
    stable_hr = _scaled(row.get("hr__std"), center=20.0, scale=20.0, invert=True)
    stable_eda = _scaled(row.get("eda__std"), center=0.8, scale=1.5, invert=True)

    homeostasis_raw = _weighted_mean(
        [
            (low_departure, 1.6),
            (low_arousal, 1.1),
            (low_motion, 0.7),
            (stable_hr, 0.5),
            (stable_eda, 0.5),
        ]
    )
    if homeostasis_raw is None:
        homeostasis_raw = _clamp(1.0 - sympathetic_raw)
        notes.append("homeostasis_missing_baseline")

    sympathetic, parasympathetic, homeostasis = _normalize_three(
        sympathetic_raw,
        parasympathetic_raw,
        homeostasis_raw,
    )
    x, y = _ternary_xy(sympathetic, parasympathetic, homeostasis)

    activity_penalty = 0.15 * (motion_load or 0.0)
    functional_pain = _clamp(sympathetic * (1.0 - homeostasis) * (1.0 - activity_penalty))
    recovery = _clamp(0.65 * parasympathetic + 0.35 * homeostasis)

    if usable_sensor_count < 2:
        notes.append("low_sensor_support")
    if not sensor_present["ibi"]:
        notes.append("pns_hrv_missing")
    if not sensor_present["eda"]:
        notes.append("sns_eda_missing")

    return FunctionalPainV1(
        sympathetic=float(sympathetic),
        parasympathetic=float(parasympathetic),
        homeostasis=float(homeostasis),
        ternary_x=x,
        ternary_y=y,
        functional_pain_0_1=functional_pain,
        recovery_0_1=recovery,
        sensor_quality_0_1=sensor_quality,
        usable_sensor_count=usable_sensor_count,
        notes=tuple(notes),
    )
