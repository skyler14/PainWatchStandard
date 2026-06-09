import pandas as pd

from painwatchstandard.features import feature_columns, rows_for_pain_training
from painwatchstandard.inference import score_quality, state_preference_normalize, summarize_sensor_blocks


def test_apple_watch_like_feature_set_excludes_metadata_ids_targets_and_auxiliary_columns():
    frame = pd.DataFrame(
        {
            "dataset_id": ["painmonit"],
            "subject_id": ["p01"],
            "session_id": ["p01_1"],
            "target_pain_nrs_0_10": [5.0],
            "target_stress_binary": [1],
            "label_family": ["direct_pain"],
            "collection_protocol": ["painmonit_pmcd_clinical"],
            "bvp__mean": [1.0],
            "hr__mean": [80.0],
            "acc__mag__mean": [0.2],
            "eda__mean": [0.1],
            "baseline_distance_l1": [0.5],
        }
    )

    cols = feature_columns(frame, "apple_watch_like")

    assert "bvp__mean" in cols
    assert "hr__mean" in cols
    assert "acc__mag__mean" in cols
    assert "baseline_distance_l1" in cols
    assert "eda__mean" not in cols
    assert "dataset_id" not in cols
    assert "subject_id" not in cols
    assert "target_pain_nrs_0_10" not in cols
    assert "collection_protocol" not in cols


def test_pain_training_rows_include_only_direct_pain_with_non_null_target():
    frame = pd.DataFrame(
        {
            "dataset_id": ["painmonit", "stress_reference_real", "rheumapain"],
            "label_family": ["direct_pain", "stress_proxy", "direct_pain"],
            "target_pain_nrs_0_10": [6.0, None, None],
        }
    )

    pain = rows_for_pain_training(frame)

    assert pain["dataset_id"].tolist() == ["painmonit"]


def test_summarize_sensor_blocks_reports_used_and_missing_blocks():
    row = {
        "bvp__present": 1,
        "hr__present": 1,
        "acc__present": 0,
        "temperature__present": 0,
    }

    summary = summarize_sensor_blocks(row, ("bvp", "hr", "acc", "temperature"))

    assert summary["sensors_used"] == ["bvp", "hr"]
    assert summary["missing_sensor_blocks"] == ["acc", "temperature"]


def test_score_quality_degrades_with_missing_sensor_blocks():
    full = score_quality(["bvp", "hr", "acc", "temperature"], [])
    weak = score_quality(["bvp"], ["hr", "acc", "temperature"])

    assert full == 1.0
    assert 0.2 <= weak < full


def test_state_preference_normalize_forces_state_competition():
    probs = state_preference_normalize(
        {
            "pain": 0.9,
            "stress": 0.85,
            "activity": 0.8,
            "low_exertion_context": 0.2,
        },
        temperature=1.0,
    )

    assert round(sum(probs.values()), 6) == 1.0
    assert probs["pain"] < 0.4
    assert probs["pain"] > probs["low_exertion_context"]
