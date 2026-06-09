"""Feature-set selection with leakage guardrails."""

from __future__ import annotations

import pandas as pd


TARGET_PREFIXES = ("target_",)
ID_COLUMNS = {
    "subject_id",
    "session_id",
    "phase3_eval_group",
    "phase3_window_id",
    "baseline_anchor_id",
    "original_all_window_id",
}
LEAKY_COLUMNS = {
    "window_start_s",
    "window_end_s",
    "source_archive",
    "source_member",
    "source_table",
    "phase3_source_table",
}
METADATA_COLUMNS = {
    "dataset_id",
    "source_family",
    "collection_protocol",
    "label_family",
    "pain_label_regime",
    "condition",
    "record_type",
    "device",
    "diagnosis",
    "sex",
    "age",
    "pain_scale_type",
    "source_modality",
    "source_dataset",
    "aux_state_label",
    "aux_stress_label",
    "proxy_label",
    "pain_type",
    "activity_status",
    "window_sampling",
}
STATE_COLUMNS = {
    "baseline_candidate",
    "baseline_anchor_available",
    "baseline_feature_count",
    "baseline_abs_delta_mean",
    "baseline_abs_delta_max",
    "baseline_l2_delta",
    "baseline_state_bin",
    "state_cluster_id",
    "baseline_missing",
    "baseline_distance_l1",
    "baseline_profile_available",
    "baseline_profile_quality_0_1",
}
SENSOR_PREFIXES: dict[str, tuple[str, ...]] = {
    "bvp": ("bvp__",),
    "bvp_rb": ("bvp_rb__",),
    "hr": ("hr__",),
    "ibi": ("ibi__",),
    "ecg": ("ecg__",),
    "eda": ("eda__",),
    "eda_rb": ("eda_rb__",),
    "temperature": ("temperature__",),
    "acc": ("acc_x__", "acc_y__", "acc_z__", "acc__"),
    "gyro": ("gyro_x__", "gyro_y__", "gyro_z__", "gyro__"),
    "respiration": ("respiration__",),
    "emg": ("emg__",),
    "grip": ("grip__",),
    "bp": ("bp_systolic__", "bp_diastolic__"),
    "spo2": ("spo2__",),
    "steps": ("steps__",),
}
FEATURE_SETS: dict[str, dict[str, object]] = {
    "apple_watch_like": {
        "sensors": ("acc", "gyro", "bvp", "hr", "ibi", "ecg", "temperature", "spo2"),
        "state": True,
        "metadata": False,
    },
    "e4_like": {"sensors": ("acc", "bvp", "eda", "temperature", "hr", "ibi"), "state": True, "metadata": False},
    "autonomic_core": {
        "sensors": ("bvp", "hr", "ibi", "ecg", "eda", "temperature", "respiration"),
        "state": True,
        "metadata": False,
    },
    "motion_only": {"sensors": ("acc", "gyro", "steps"), "state": True, "metadata": False},
    "metadata_probe": {"sensors": (), "state": True, "metadata": True},
}


def _sensor_columns(frame: pd.DataFrame, sensors: tuple[str, ...]) -> list[str]:
    prefixes = tuple(prefix for sensor in sensors for prefix in SENSOR_PREFIXES[sensor])
    return [
        column
        for column in frame.columns
        if column.startswith(prefixes)
        and not column.startswith(TARGET_PREFIXES)
        and column not in ID_COLUMNS
        and column not in LEAKY_COLUMNS
    ]


def feature_columns(frame: pd.DataFrame, feature_set: str) -> list[str]:
    if feature_set not in FEATURE_SETS:
        raise KeyError(f"Unknown feature set: {feature_set}")
    spec = FEATURE_SETS[feature_set]
    selected: list[str] = []
    selected.extend(_sensor_columns(frame, tuple(spec["sensors"])))  # type: ignore[arg-type]
    if spec["state"]:
        selected.extend(column for column in STATE_COLUMNS if column in frame.columns)
        selected.extend(column for column in frame.columns if "__delta_from_profile_median" in column or "__robust_z_from_profile" in column)
    if spec["metadata"]:
        selected.extend(column for column in METADATA_COLUMNS if column in frame.columns)
    excluded = set(ID_COLUMNS) | set(LEAKY_COLUMNS)
    excluded.update(column for column in frame.columns if column.startswith(TARGET_PREFIXES))
    out: list[str] = []
    seen: set[str] = set()
    for column in selected:
        if column in seen or column in excluded or column not in frame.columns:
            continue
        if not frame[column].notna().any():
            continue
        out.append(column)
        seen.add(column)
    return out


def rows_for_pain_training(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[frame["label_family"].eq("direct_pain") & frame["target_pain_nrs_0_10"].notna()].copy()
