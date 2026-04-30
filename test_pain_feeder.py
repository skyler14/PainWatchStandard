import math

import numpy as np
import pandas as pd
import pytest

from pain_feeder import (
    FeederConfig,
    aggregate_labels,
    attach_baseline_features,
    build_windows_for_session,
    drop_sensor_blocks,
    make_window_anchors,
    resample_to_grid,
    standardize_measurements,
    validate_config,
)


def painmonit_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dataset_id": ["painmonit"] * 8,
            "subject_id": ["p01"] * 8,
            "session_id": ["p01_1"] * 8,
            "session_number": [1] * 8,
            "condition": ["clinical_physiotherapy"] * 8,
            "record_type": ["clinical_main"] * 8,
            "device": ["mixed"] * 8,
            "sample_rate_hz": [4.0] * 8,
            "sample_index": list(range(8)),
            "sample_offset_s": np.arange(8) * 0.25,
            "bvp": np.arange(8, dtype=float),
            "eda_e4": np.arange(8, dtype=float) + 10.0,
            "temperature": [34.0, 34.1, 34.2, 34.3, 34.4, 34.5, 34.6, 34.7],
            "respiration": np.arange(8, dtype=float) + 20.0,
            "eda_rb": np.arange(8, dtype=float) + 30.0,
            "bvp_rb": np.arange(8, dtype=float) + 40.0,
            "emg": np.arange(8, dtype=float) + 50.0,
            "grip": np.arange(8, dtype=float) + 60.0,
            "pain_rate_nrs": [np.nan, np.nan, 5.0, np.nan, np.nan, 7.0, np.nan, np.nan],
            "pain_label": [np.nan, np.nan, 1.0, np.nan, np.nan, 2.0, np.nan, np.nan],
            "pain_scale_type": ["nrs_0_10"] * 8,
            "no_pain_threshold": [3.0] * 8,
            "severe_pain_threshold": [6.0] * 8,
        }
    )


def rheuma_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dataset_id": ["rheumapain"] * 6,
            "subject_id": ["s001"] * 6,
            "session_id": ["s001_rest"] * 6,
            "condition": ["rest"] * 6,
            "device": ["empatica_e4"] * 6,
            "sample_rate_hz": [2.0] * 6,
            "sample_index": list(range(6)),
            "sample_offset_s": np.arange(6) * 0.5,
            "bvp": [1, 2, 3, 4, 5, 6],
            "eda": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            "acc_x": [1.0] * 6,
            "acc_y": [2.0] * 6,
            "acc_z": [2.0] * 6,
            "temperature": [33, 33, 34, 34, 35, 35],
            "pain_score": [2.0] * 6,
            "pain_scale_type": ["wong_baker_faces"] * 6,
            "diagnosis": ["JIA"] * 6,
            "sex": ["f"] * 6,
            "age": [12.0] * 6,
        }
    )


def test_validate_config_accepts_1_to_10_hz() -> None:
    validate_config(FeederConfig(target_hz=1.0))
    validate_config(FeederConfig(target_hz=2.0))
    validate_config(FeederConfig(target_hz=10.0))


def test_validate_config_rejects_outside_supported_cadence() -> None:
    with pytest.raises(ValueError):
        validate_config(FeederConfig(target_hz=0.5))
    with pytest.raises(ValueError):
        validate_config(FeederConfig(target_hz=11.0))


def test_standardize_painmonit_maps_sensor_and_label_columns() -> None:
    out = standardize_measurements(painmonit_fixture(), "painmonit")
    assert out["eda"].iloc[0] == 10.0
    assert out["pain_intensity"].dropna().tolist() == [5.0, 7.0]
    assert out["pain_class"].dropna().tolist() == [1.0, 2.0]
    assert "acc_mag" in out.columns
    assert out["respiration"].iloc[-1] == 27.0


def test_standardize_rheumapain_maps_session_label_and_acc_mag() -> None:
    out = standardize_measurements(rheuma_fixture(), "rheumapain")
    assert out["pain_intensity"].dropna().unique().tolist() == [2.0]
    assert out["diagnosis"].iloc[0] == "JIA"
    assert math.isclose(out["acc_mag"].iloc[0], 3.0)


def test_resample_to_grid_aggregates_to_requested_hz() -> None:
    out = standardize_measurements(painmonit_fixture(), "painmonit")
    grid = resample_to_grid(out, target_hz=2.0)
    assert grid["grid_index"].tolist() == [0, 1, 2, 3]
    assert grid["bvp"].tolist() == [0.5, 2.5, 4.5, 6.5]
    assert grid["target_hz"].unique().tolist() == [2.0]


def test_make_window_anchors_uses_prediction_cadence() -> None:
    out = standardize_measurements(rheuma_fixture(), "rheumapain")
    anchors = make_window_anchors(out, FeederConfig(target_hz=2.0, window_seconds=1.0))
    assert anchors.tolist() == [1.0, 1.5, 2.0, 2.5]


def test_build_windows_for_session_emits_sensor_blocks_and_labels() -> None:
    out = standardize_measurements(painmonit_fixture(), "painmonit")
    windows = build_windows_for_session(out, "painmonit", FeederConfig(target_hz=1.0, window_seconds=1.5))
    assert len(windows) == 1
    row = windows.iloc[0]
    assert row["bvp__present"] == 1
    assert row["eda__present"] == 1
    assert row["respiration__present"] == 1
    assert row["target_available"] == 1
    assert row["target_pain_count"] == 2
    assert row["target_pain_nrs_0_10"] == 6.0
    assert row["target_pain_class_3"] == 1.0


def test_aggregate_labels_marks_rheumapain_as_weak_session() -> None:
    out = standardize_measurements(rheuma_fixture(), "rheumapain")
    labels = aggregate_labels(out, "rheumapain")
    assert labels["target_available"] == 1
    assert labels["target_granularity"] == "session_weak"
    assert labels["target_confidence"] == 0.35


def test_drop_sensor_blocks_blanks_all_columns_in_block() -> None:
    out = standardize_measurements(rheuma_fixture(), "rheumapain")
    dropped = drop_sensor_blocks(out, ["acc"], seed=1)
    assert dropped["acc_x"].isna().all()
    assert dropped["acc_y"].isna().all()
    assert dropped["acc_z"].isna().all()
    assert dropped["acc_mag"].isna().all()
    assert dropped["bvp"].notna().all()


def test_attach_baseline_features_adds_delta_and_z_without_replacing_raw() -> None:
    windows = pd.DataFrame(
        {
            "dataset_id": ["rheumapain", "rheumapain", "rheumapain"],
            "subject_id": ["s001", "s001", "s001"],
            "session_id": ["rest", "rest", "exercise"],
            "condition": ["rest", "rest", "exercise"],
            "bvp__mean": [10.0, 14.0, 18.0],
        }
    )
    out = attach_baseline_features(windows, FeederConfig())
    assert out["bvp__mean"].tolist() == [10.0, 14.0, 18.0]
    assert out["baseline_available"].tolist() == [True, True, True]
    assert out["bvp__mean__baseline_mean"].tolist() == [12.0, 12.0, 12.0]
    assert out["bvp__mean__delta_from_baseline"].tolist() == [-2.0, 2.0, 6.0]
    assert out["bvp__mean__z_from_baseline"].round(3).tolist() == [-1.0, 1.0, 3.0]


def test_no_baseline_keeps_baseline_features_unavailable() -> None:
    windows = pd.DataFrame(
        {
            "dataset_id": ["painmonit"],
            "subject_id": ["p01"],
            "condition": ["clinical_physiotherapy"],
            "bvp__mean": [10.0],
        }
    )
    out = attach_baseline_features(windows, FeederConfig())
    assert out["baseline_available"].tolist() == [False]


def test_attach_baseline_features_tolerates_sensor_missing_from_baseline_rows() -> None:
    windows = pd.DataFrame(
        {
            "dataset_id": ["rheumapain", "painmonit"],
            "subject_id": ["s001", "p01"],
            "condition": ["rest", "clinical_physiotherapy"],
            "bvp__mean": [10.0, 20.0],
            "bvp_rb__mean": [np.nan, 30.0],
        }
    )
    out = attach_baseline_features(windows, FeederConfig())
    assert "bvp_rb__mean__baseline_mean" in out.columns
    assert out["bvp_rb__mean__baseline_mean"].isna().all()
