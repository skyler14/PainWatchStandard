"""Inference helper functions independent of any model backend."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


DEFAULT_SENSOR_BLOCKS = ("hr", "acc", "gyro", "temperature", "spo2", "bvp", "eda", "ibi")


def summarize_sensor_blocks(
    row: Mapping[str, Any],
    expected_blocks: Sequence[str] = DEFAULT_SENSOR_BLOCKS,
) -> dict[str, list[str]]:
    sensors_used: list[str] = []
    missing_sensor_blocks: list[str] = []
    for block in expected_blocks:
        present_keys = [key for key in row if key.startswith(f"{block}__") and key.endswith("__present")]
        present = any(float(row.get(key) or 0) > 0 for key in present_keys)
        if present:
            sensors_used.append(block)
        else:
            missing_sensor_blocks.append(block)
    return {"sensors_used": sensors_used, "missing_sensor_blocks": missing_sensor_blocks}


def score_quality(sensors_used: Sequence[str], missing_sensor_blocks: Sequence[str]) -> float:
    if not sensors_used and missing_sensor_blocks:
        return 0.2
    quality = 1.0 - 0.07 * len(missing_sensor_blocks)
    return max(0.2, min(1.0, quality))


def confidence_from_probability(probability: float, quality_0_1: float) -> float:
    distance = abs(float(probability) - 0.5) * 2.0
    return max(0.05, min(0.95, 0.5 * quality_0_1 + 0.5 * distance))


def state_preference_normalize(state_scores: Mapping[str, float], temperature: float = 1.6) -> dict[str, float]:
    """Convert independent state scores into competing preferences.

    Independent binary heads can all return high positive likelihood. This
    normalizer preserves each head but adds a "which state does this row prefer"
    view. Missing/dropout-impossible heads should be omitted by caller, not set
    to confident zero.
    """
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    clean = {key: float(value) for key, value in state_scores.items() if value is not None and math.isfinite(float(value))}
    if not clean:
        return {}
    scaled = {key: value / temperature for key, value in clean.items()}
    offset = max(scaled.values())
    exp_values = {key: math.exp(value - offset) for key, value in scaled.items()}
    total = sum(exp_values.values())
    return {key: value / total for key, value in exp_values.items()}
