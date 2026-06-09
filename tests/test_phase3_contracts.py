import numpy as np
import pandas as pd

from painwatchstandard.baseline import build_subject_baseline_profile, attach_baseline_profile_features
from painwatchstandard.normalizers.painmonit import normalize_column, parse_painmonit_session
from painwatchstandard.routing import family_for_row, ordinal_pain_bin
from painwatchstandard.sensors import sensor_block_features
from painwatchstandard.windowing import WindowConfig, build_windows_for_session, make_window_anchors


def test_painmonit_session_parser_extracts_subject_session_and_trial():
    parsed = parse_painmonit_session("PMCD/raw-data/P36_2/P36_2.csv")

    assert parsed == {"subject_id": "p36", "session_id": "p36_2", "session_number": 2}


def test_normalize_column_handles_decimal_comma_source_headers():
    assert normalize_column(" Pain rates ") == "pain_rates"
    assert normalize_column("Eda_E4") == "eda_e4"
    assert normalize_column("Heater [C]") == "heater_c"


def test_window_anchors_are_causal_full_windows_only():
    session = pd.DataFrame({"sample_offset_s": np.arange(0, 35, dtype=float)})
    anchors = make_window_anchors(session, WindowConfig(target_hz=1.0, window_seconds=30.0))

    assert anchors[:3].tolist() == [30.0, 31.0, 32.0]
    assert anchors[-1] == 34.0


def test_build_window_includes_only_samples_up_to_anchor():
    session = pd.DataFrame(
        {
            "dataset_id": "painmonit",
            "subject_id": "p01",
            "session_id": "p01_1",
            "sample_offset_s": np.arange(0, 35, dtype=float),
            "eda": np.arange(0, 35, dtype=float),
            "pain_intensity": [np.nan] * 30 + [4.0, 5.0, np.nan, np.nan, 6.0],
        }
    )

    windows = build_windows_for_session(session, WindowConfig(target_hz=1.0, window_seconds=30.0))
    first = windows.iloc[0]

    assert first["window_start_s"] == 0.0
    assert first["window_end_s"] == 30.0
    assert first["source_rows"] == 30
    assert first["eda__max"] == 30.0
    assert first["target_pain_nrs_0_10"] == 4.0


def test_missing_sensor_block_does_not_fabricate_values():
    features = sensor_block_features(
        pd.DataFrame({"sample_offset_s": [1.0, 2.0, 3.0]}),
        "eda",
        ("eda",),
    )

    assert features["eda__present"] == 0
    assert features["eda__valid_count"] == 0
    assert features["eda__valid_frac"] == 0.0
    assert features["eda__mean"] is None


def test_ibi_window_features_include_rmssd_and_sdnn():
    features = sensor_block_features(
        pd.DataFrame(
            {
                "sample_offset_s": [1.0, 2.0, 3.0, 4.0],
                "ibi": [0.8, 0.82, 0.78, 0.81],
            }
        ),
        "ibi",
        ("ibi",),
    )

    assert features["ibi__present"] == 1
    assert features["ibi__rmssd_ms"] > 0
    assert features["ibi__sdnn_ms"] > 0


def test_label_family_routes_auxiliary_rows_away_from_pain():
    assert family_for_row({"dataset_id": "painmonit", "target_pain_nrs_0_10": 5.0}) == "direct_pain"
    assert family_for_row({"dataset_id": "stress_reference_real", "aux_stress_label": 1}) == "stress_proxy"
    assert family_for_row({"dataset_id": "catsa", "condition": "Baseline"}) == "baseline_context"
    assert family_for_row({"dataset_id": "catsa", "condition": "Stroop"}) == "cognitive_load_proxy"
    assert family_for_row({"dataset_id": "induced_stress_exercise", "condition": "exercise"}) == "exercise_context"


def test_ordinal_pain_bins_match_phase3_contract():
    assert ordinal_pain_bin(0) == 0
    assert ordinal_pain_bin(2.5) == 1
    assert ordinal_pain_bin(4) == 2
    assert ordinal_pain_bin(7) == 3
    assert np.isnan(ordinal_pain_bin(np.nan))


def test_baseline_profile_appends_robust_features_without_replacing_raw():
    frame = pd.DataFrame(
        {
            "dataset_id": ["rheumapain"] * 4,
            "subject_id": ["s001"] * 4,
            "condition": ["rest", "rest", "exercise", "exercise"],
            "eda__mean": [1.0, 1.2, 2.0, 2.4],
            "acc__mag__mean": [0.1, 0.2, 1.5, 1.7],
        }
    )
    profile = build_subject_baseline_profile(frame, "rheumapain", "s001")
    attached = attach_baseline_profile_features(frame, profile)

    assert attached["eda__mean"].tolist() == [1.0, 1.2, 2.0, 2.4]
    assert "eda__mean__robust_z_from_profile" in attached.columns
    assert bool(attached.loc[2, "baseline_profile_available"]) is True
    assert attached.loc[2, "eda__mean__delta_from_profile_median"] > 0
