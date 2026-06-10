import math

from painwatchstandard.functional_pain_v1 import functional_pain_v1


def test_functional_pain_v1_balances_to_ternary_sum():
    result = functional_pain_v1(
        {
            "eda__present": 1,
            "eda__mean": 0.2,
            "eda__slope_per_s": -0.01,
            "hr__present": 1,
            "hr__mean": 65,
            "hr__slope_per_s": -0.2,
            "ibi__present": 1,
            "ibi__rmssd_ms": 70,
            "ibi__sdnn_ms": 80,
            "temperature__present": 1,
            "temperature__slope_per_s": 0.0,
            "acc__present": 1,
            "acc__mag__std": 0.02,
            "baseline_distance_l1": 0.05,
        }
    )

    assert math.isclose(result.sympathetic + result.parasympathetic + result.homeostasis, 1.0)
    assert 0.0 <= result.ternary_x <= 1.0
    assert 0.0 <= result.ternary_y <= math.sqrt(3.0) / 2.0


def test_functional_pain_v1_arousal_pushes_sympathetic_and_pain_up():
    calm = functional_pain_v1(
        {
            "eda__present": 1,
            "eda__mean": 0.1,
            "eda__slope_per_s": -0.01,
            "hr__present": 1,
            "hr__mean": 62,
            "ibi__present": 1,
            "ibi__rmssd_ms": 80,
            "baseline_distance_l1": 0.05,
        }
    )
    aroused = functional_pain_v1(
        {
            "eda__present": 1,
            "eda__mean": 3.0,
            "eda__slope_per_s": 0.05,
            "eda__peak_count": 8,
            "hr__present": 1,
            "hr__mean": 115,
            "ibi__present": 1,
            "ibi__rmssd_ms": 12,
            "temperature__present": 1,
            "temperature__slope_per_s": -0.04,
            "baseline_distance_l1": 0.9,
        }
    )

    assert aroused.sympathetic > calm.sympathetic
    assert aroused.functional_pain_0_1 > calm.functional_pain_0_1


def test_functional_pain_v1_recovery_pushes_parasympathetic_and_homeostasis():
    result = functional_pain_v1(
        {
            "eda__present": 1,
            "eda__mean": 0.2,
            "eda__slope_per_s": -0.03,
            "eda__std": 0.05,
            "hr__present": 1,
            "hr__mean": 60,
            "hr__slope_per_s": -0.5,
            "hr__std": 3,
            "ibi__present": 1,
            "ibi__rmssd_ms": 95,
            "ibi__sdnn_ms": 100,
            "respiration__present": 1,
            "respiration__std": 0.1,
            "baseline_distance_l1": 0.01,
        }
    )

    assert result.recovery_0_1 > result.functional_pain_0_1
    assert result.parasympathetic > result.sympathetic
