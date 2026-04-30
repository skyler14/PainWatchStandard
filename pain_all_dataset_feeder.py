#!/usr/bin/env python3
"""Build all-dataset self-supervised window features from local compressed files.

This complements the normalized feeder: it streams directly from supported zip
archives, emits 1 Hz / 30 s model windows, and writes baseline-state atlas
artifacts for review without expanding archives onto disk.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZipFile

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError
from sklearn.cluster import MiniBatchKMeans
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent
DEFAULT_NORMALIZED_WINDOWS = ROOT / "_normalized" / "window_features" / "target_hz=1" / "window_features.parquet"
DEFAULT_OUTPUT = ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "window_features.parquet"

SIGNAL_BLOCKS: dict[str, tuple[str, ...]] = {
    "bvp": ("bvp",),
    "bvp_rb": ("bvp_rb",),
    "hr": ("hr",),
    "ibi": ("ibi",),
    "ecg": ("ecg",),
    "eda": ("eda",),
    "eda_rb": ("eda_rb",),
    "temperature": ("temperature",),
    "acc": ("acc_x", "acc_y", "acc_z"),
    "gyro": ("gyro_x", "gyro_y", "gyro_z"),
    "respiration": ("respiration",),
    "emg": ("emg",),
    "grip": ("grip",),
    "bp_systolic": ("bp_systolic",),
    "bp_diastolic": ("bp_diastolic",),
    "spo2": ("spo2",),
    "steps": ("steps",),
    "eeg_delta": ("eeg_delta",),
    "eeg_theta": ("eeg_theta",),
    "eeg_alpha1": ("eeg_alpha1",),
    "eeg_alpha2": ("eeg_alpha2",),
    "eeg_beta1": ("eeg_beta1",),
    "eeg_beta2": ("eeg_beta2",),
    "eeg_gamma1": ("eeg_gamma1",),
    "eeg_gamma2": ("eeg_gamma2",),
    "eeg_attention": ("eeg_attention",),
    "eeg_meditation": ("eeg_meditation",),
}

CATSA_RATES = {
    "ACC": 32.0,
    "BVP": 64.0,
    "EDA": 4.0,
    "HR": 1.0,
    "TEMP": 4.0,
}

E4_SENSORS = {"ACC", "BVP", "EDA", "HR", "IBI", "TEMP"}
BASELINE_TERMS = ("baseline", "rest", "resting", "neutral", "no_pain", "nopain", "no pain")


@dataclass(frozen=True)
class WindowConfig:
    target_hz: float = 1.0
    window_seconds: float = 30.0
    min_source_rows: int = 2
    max_windows_per_session: int | None = 2500

    @property
    def step_seconds(self) -> float:
        return 1.0 / self.target_hz


@dataclass
class CoverageEvent:
    dataset_id: str
    status: str
    sessions: int = 0
    rows: int = 0
    reason: str | None = None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def read_csv_member(zip_file: ZipFile, member: str, **kwargs: Any) -> pd.DataFrame:
    with zip_file.open(member) as handle:
        try:
            return pd.read_csv(handle, **kwargs)
        except EmptyDataError:
            return pd.DataFrame()
        except UnicodeDecodeError:
            handle.seek(0)
            retry_kwargs = {**kwargs, "encoding": "latin1"}
            return pd.read_csv(handle, **retry_kwargs)


def clean_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [str(column).strip() for column in out.columns]
    return out


def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def sensor_frame(offsets: np.ndarray, values: dict[str, Iterable[Any]]) -> pd.DataFrame:
    frame = pd.DataFrame({"sample_offset_s": offsets.astype(float)})
    for column, value in values.items():
        frame[column] = pd.to_numeric(pd.Series(value), errors="coerce").to_numpy()
    return frame


def concat_sensor_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    valid = [frame for frame in frames if not frame.empty]
    if not valid:
        return pd.DataFrame()
    return pd.concat(valid, ignore_index=True, sort=False)


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
    values = values[np.isfinite(values)]
    if values.size < 3:
        return 0
    spread = float(np.nanstd(values))
    threshold = float(np.nanmean(values)) + 0.25 * spread
    peaks = (values[1:-1] > values[:-2]) & (values[1:-1] >= values[2:]) & (values[1:-1] > threshold)
    return int(peaks.sum())


def series_features(prefix: str, times: np.ndarray, values: np.ndarray) -> dict[str, Any]:
    mask = np.isfinite(values)
    valid = values[mask].astype(float)
    features: dict[str, Any] = {
        f"{prefix}__present": int(valid.size > 0),
        f"{prefix}__valid_count": int(valid.size),
        f"{prefix}__valid_frac": float(valid.size / max(len(values), 1)),
        f"{prefix}__mean": None,
        f"{prefix}__std": None,
        f"{prefix}__min": None,
        f"{prefix}__max": None,
        f"{prefix}__last": None,
        f"{prefix}__slope_per_s": None,
        f"{prefix}__peak_count": 0,
    }
    if valid.size == 0:
        return features
    features[f"{prefix}__mean"] = float(np.nanmean(valid))
    features[f"{prefix}__std"] = float(np.nanstd(valid, ddof=0))
    features[f"{prefix}__min"] = float(np.nanmin(valid))
    features[f"{prefix}__max"] = float(np.nanmax(valid))
    features[f"{prefix}__last"] = float(valid[-1])
    features[f"{prefix}__slope_per_s"] = _slope_per_second(times, values)
    features[f"{prefix}__peak_count"] = _peak_count(values)
    return features


def block_features(window: pd.DataFrame, block: str, columns: tuple[str, ...]) -> dict[str, Any]:
    available = [column for column in columns if column in window.columns]
    if not available:
        return {
            f"{block}__present": 0,
            f"{block}__valid_count": 0,
            f"{block}__valid_frac": 0.0,
        }
    subset = window[["sample_offset_s", *available]].dropna(subset=available, how="all")
    if subset.empty:
        return {
            f"{block}__present": 0,
            f"{block}__valid_count": 0,
            f"{block}__valid_frac": 0.0,
        }
    times = subset["sample_offset_s"].to_numpy(dtype=float)
    if block in {"acc", "gyro"}:
        features: dict[str, Any] = {}
        axis_names = ("x", "y", "z")
        for axis, column in zip(axis_names, columns):
            if column in subset.columns:
                features.update(series_features(column, times, subset[column].to_numpy(dtype=float)))
        axis_frame = subset[[column for column in columns if column in subset.columns]]
        if len(axis_frame.columns) == 3:
            mag = np.sqrt(np.square(axis_frame.to_numpy(dtype=float)).sum(axis=1))
            features.update(series_features(f"{block}__mag", times, mag))
            valid = mag[np.isfinite(mag)]
            features[f"{block}__present"] = int(valid.size > 0)
            features[f"{block}__valid_count"] = int(valid.size)
            features[f"{block}__valid_frac"] = float(valid.size / max(len(mag), 1))
            features[f"{block}__stillness_frac"] = (
                float((np.abs(np.diff(valid)) < 0.02).sum() / max(valid.size - 1, 1)) if valid.size > 1 else None
            )
        return features
    return series_features(block, times, subset[available[0]].to_numpy(dtype=float))


def make_anchors(session: pd.DataFrame, config: WindowConfig) -> tuple[np.ndarray, str]:
    times = pd.to_numeric(session["sample_offset_s"], errors="coerce").dropna()
    if times.empty:
        return np.array([], dtype=float), "empty"
    first_anchor = float(times.min()) + config.window_seconds
    max_time = float(times.max())
    if first_anchor > max_time:
        return np.array([], dtype=float), "too_short"
    count = int(math.floor((max_time - first_anchor) / config.step_seconds)) + 1
    anchors = first_anchor + np.arange(count, dtype=float) * config.step_seconds
    if config.max_windows_per_session and len(anchors) > config.max_windows_per_session:
        indices = np.unique(np.round(np.linspace(0, len(anchors) - 1, config.max_windows_per_session)).astype(int))
        return anchors[indices], f"capped_even_{config.max_windows_per_session}"
    return anchors, "full"


def aggregate_targets(window: pd.DataFrame, label_scale: str, label_confidence: float) -> dict[str, Any]:
    pain = pd.to_numeric(window.get("pain_intensity", pd.Series(dtype=float)), errors="coerce").dropna()
    pain_class = pd.to_numeric(window.get("pain_class", pd.Series(dtype=float)), errors="coerce").dropna()
    result: dict[str, Any] = {
        "target_available": int(not pain.empty),
        "target_pain_nrs_0_10": None,
        "target_pain_min": None,
        "target_pain_max": None,
        "target_pain_count": int(pain.shape[0]),
        "target_pain_coverage": float(pain.shape[0] / max(len(window), 1)),
        "target_pain_class_3": None,
        "target_scale": label_scale if not pain.empty else None,
        "target_granularity": "archive_window_direct" if not pain.empty else "none",
        "target_confidence": label_confidence if not pain.empty else 0.0,
    }
    if not pain.empty:
        result["target_pain_nrs_0_10"] = float(pain.mean())
        result["target_pain_min"] = float(pain.min())
        result["target_pain_max"] = float(pain.max())
    if not pain_class.empty:
        result["target_pain_class_3"] = float(pain_class.mode().iloc[0])
    return result


def build_windows_for_session(
    session: pd.DataFrame,
    meta: dict[str, Any],
    config: WindowConfig,
    label_scale: str | None = None,
    label_confidence: float = 0.0,
) -> pd.DataFrame:
    if session.empty:
        return pd.DataFrame()
    session = session.sort_values("sample_offset_s", kind="mergesort").reset_index(drop=True)
    anchors, sampling = make_anchors(session, config)
    if anchors.size == 0:
        return pd.DataFrame()
    times = session["sample_offset_s"].to_numpy(dtype=float)
    rows: list[dict[str, Any]] = []
    for anchor in anchors:
        start = anchor - config.window_seconds
        left = int(np.searchsorted(times, start, side="right"))
        right = int(np.searchsorted(times, anchor, side="right"))
        window = session.iloc[left:right]
        if len(window) < config.min_source_rows:
            continue
        row: dict[str, Any] = {
            **meta,
            "window_start_s": float(start),
            "window_end_s": float(anchor),
            "window_seconds": float(config.window_seconds),
            "target_hz": float(config.target_hz),
            "source_rows": int(len(window)),
            "window_sampling": sampling,
        }
        for block, columns in SIGNAL_BLOCKS.items():
            row.update(block_features(window, block, columns))
        row.update(aggregate_targets(window, label_scale or "none", label_confidence))
        rows.append(row)
    return pd.DataFrame(rows)


def read_empatica_member(zip_file: ZipFile, member: str, sensor: str) -> pd.DataFrame:
    raw = read_csv_member(zip_file, member, header=None)
    if raw.empty or len(raw) < 2:
        return pd.DataFrame()
    sensor = sensor.upper()
    if sensor == "IBI":
        data = raw.iloc[1:].copy()
        if data.shape[1] < 2:
            return pd.DataFrame()
        offsets = pd.to_numeric(data.iloc[:, 0], errors="coerce").to_numpy(dtype=float)
        values = pd.to_numeric(data.iloc[:, 1], errors="coerce").to_numpy(dtype=float)
        return sensor_frame(offsets, {"ibi": values})
    rate = pd.to_numeric(raw.iloc[1], errors="coerce").dropna()
    sample_rate = float(rate.iloc[0]) if not rate.empty and float(rate.iloc[0]) > 0 else 1.0
    data = raw.iloc[2:].reset_index(drop=True)
    offsets = np.arange(len(data), dtype=float) / sample_rate
    if sensor == "ACC":
        if data.shape[1] < 3:
            return pd.DataFrame()
        return sensor_frame(offsets, {"acc_x": data.iloc[:, 0], "acc_y": data.iloc[:, 1], "acc_z": data.iloc[:, 2]})
    column_map = {"BVP": "bvp", "EDA": "eda", "HR": "hr", "TEMP": "temperature"}
    if sensor not in column_map:
        return pd.DataFrame()
    return sensor_frame(offsets, {column_map[sensor]: data.iloc[:, 0]})


def build_catsa(config: WindowConfig) -> tuple[pd.DataFrame, CoverageEvent]:
    path = ROOT / "CATSA.zip"
    if not path.exists():
        return pd.DataFrame(), CoverageEvent("catsa", "missing", reason=str(path))
    frames: list[pd.DataFrame] = []
    with ZipFile(path) as zip_file:
        members = [
            name for name in zip_file.namelist()
            if re.match(r"CATSA/Sub[^/]+/[^/]+/(ACC|BVP|EDA|HR|TEMP)\.csv$", name)
        ]
        grouped: dict[tuple[str, str], dict[str, str]] = {}
        for member in members:
            _, subject, condition, filename = member.split("/")
            sensor = filename.removesuffix(".csv")
            grouped.setdefault((subject, condition), {})[sensor] = member
        for (subject, condition), sensor_members in sorted(grouped.items()):
            sensor_frames: list[pd.DataFrame] = []
            for sensor, member in sensor_members.items():
                data = clean_columns(read_csv_member(zip_file, member))
                rate = CATSA_RATES[sensor]
                offsets = np.arange(len(data), dtype=float) / rate
                if sensor == "ACC":
                    sensor_frames.append(
                        sensor_frame(offsets, {"acc_x": data["ACC_X"], "acc_y": data["ACC_Y"], "acc_z": data["ACC_Z"]})
                    )
                else:
                    column_map = {"BVP": "bvp", "EDA": "eda", "HR": "hr", "TEMP": "temperature"}
                    sensor_frames.append(sensor_frame(offsets, {column_map[sensor]: data.iloc[:, 0]}))
            meta = {
                "dataset_id": "catsa",
                "subject_id": subject,
                "session_id": f"{subject}_{condition}",
                "condition": condition.lower(),
                "record_type": "cognitive_task",
                "device": "empatica_like",
                "source_archive": "CATSA.zip",
                "source_member": f"CATSA/{subject}/{condition}",
                "source_modality": "wrist",
                "aux_state_label": condition.lower(),
            }
            frames.append(build_windows_for_session(concat_sensor_frames(sensor_frames), meta, config))
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return out, CoverageEvent("catsa", "ok", sessions=len(frames), rows=len(out))


def build_induced_stress(config: WindowConfig) -> tuple[pd.DataFrame, CoverageEvent]:
    archive = "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip"
    path = ROOT / archive
    if not path.exists():
        return pd.DataFrame(), CoverageEvent("induced_stress_exercise", "missing", reason=str(path))
    frames: list[pd.DataFrame] = []
    with ZipFile(path) as zip_file:
        members = [
            name for name in zip_file.namelist()
            if "/Wearable_Dataset/" in name and name.rsplit("/", 1)[-1].removesuffix(".csv").upper() in E4_SENSORS
        ]
        grouped: dict[tuple[str, str], dict[str, str]] = {}
        for member in members:
            parts = member.split("/")
            activity, subject, filename = parts[-3], parts[-2], parts[-1]
            sensor = filename.removesuffix(".csv").upper()
            grouped.setdefault((activity, subject), {})[sensor] = member
        for (activity, subject), sensor_members in sorted(grouped.items()):
            sensor_frames = [
                read_empatica_member(zip_file, member, sensor)
                for sensor, member in sorted(sensor_members.items())
            ]
            meta = {
                "dataset_id": "induced_stress_exercise",
                "subject_id": subject,
                "session_id": f"{activity}_{subject}",
                "condition": activity.lower(),
                "record_type": "exercise_stress_protocol",
                "device": "empatica_e4",
                "source_archive": archive,
                "source_member": f"Wearable_Dataset/{activity}/{subject}",
                "source_modality": "wrist",
                "aux_state_label": activity.lower(),
            }
            frames.append(build_windows_for_session(concat_sensor_frames(sensor_frames), meta, config))
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return out, CoverageEvent("induced_stress_exercise", "ok", sessions=len(frames), rows=len(out))


def build_wesad_e4(config: WindowConfig) -> tuple[pd.DataFrame, CoverageEvent]:
    path = ROOT / "WESAD.zip"
    if not path.exists():
        return pd.DataFrame(), CoverageEvent("wesad", "missing", reason=str(path))
    frames: list[pd.DataFrame] = []
    with ZipFile(path) as outer:
        nested = [name for name in outer.namelist() if name.endswith("_E4_Data.zip")]
        for member in sorted(nested):
            subject = member.split("/")[-2]
            with ZipFile(io.BytesIO(outer.read(member))) as inner:
                sensor_frames = []
                for sensor in sorted(E4_SENSORS):
                    inner_member = f"{sensor}.csv"
                    if inner_member in inner.namelist():
                        sensor_frames.append(read_empatica_member(inner, inner_member, sensor))
            meta = {
                "dataset_id": "wesad",
                "subject_id": subject,
                "session_id": f"{subject}_e4_full_protocol",
                "condition": "full_protocol",
                "record_type": "stress_protocol",
                "device": "empatica_e4",
                "source_archive": "WESAD.zip",
                "source_member": member,
                "source_modality": "wrist",
                "aux_state_label": "stress_protocol_unsegmented",
            }
            frames.append(build_windows_for_session(concat_sensor_frames(sensor_frames), meta, config))
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return out, CoverageEvent("wesad", "ok", sessions=len(frames), rows=len(out))


def build_epm_e4_clean(config: WindowConfig) -> tuple[pd.DataFrame, CoverageEvent]:
    path = ROOT / "EPM-E4.zip"
    if not path.exists():
        return pd.DataFrame(), CoverageEvent("epm_e4", "missing", reason=str(path))
    frames: list[pd.DataFrame] = []
    with ZipFile(path) as zip_file:
        members = [
            name for name in zip_file.namelist()
            if "preprocessed/clean-signals copia/empatica_slices/" in name and name.endswith(".csv")
        ]
        for member in sorted(members):
            parts = member.split("/")
            subject = parts[-2]
            condition = parts[-1].removesuffix(".csv").lower()
            data = clean_columns(read_csv_member(zip_file, member))
            if data.empty or "TimeStamp" not in data.columns:
                continue
            ts = pd.to_datetime(data["TimeStamp"], errors="coerce")
            offsets = (ts - ts.dropna().min()).dt.total_seconds().to_numpy(dtype=float)
            frame = sensor_frame(
                offsets,
                {
                    "acc_x": numeric_series(data, "empatica.acc.x"),
                    "acc_y": numeric_series(data, "empatica.acc.y"),
                    "acc_z": numeric_series(data, "empatica.acc.z"),
                    "hr": numeric_series(data, "empatica.hr"),
                    "bvp": numeric_series(data, "empatica.bvp"),
                    "eda": numeric_series(data, "empatica.eda"),
                    "temperature": numeric_series(data, "empatica.temp"),
                },
            ).dropna(subset=["sample_offset_s"])
            meta = {
                "dataset_id": "epm_e4",
                "subject_id": subject,
                "session_id": f"{subject}_{condition}",
                "condition": condition,
                "record_type": "emotion_slice",
                "device": "empatica_e4",
                "source_archive": "EPM-E4.zip",
                "source_member": member,
                "source_modality": "wrist",
                "aux_state_label": condition,
            }
            frames.append(build_windows_for_session(frame, meta, config))
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return out, CoverageEvent("epm_e4", "ok", sessions=len(frames), rows=len(out))


def build_physio_watch(config: WindowConfig) -> tuple[pd.DataFrame, CoverageEvent]:
    path = ROOT / "PhysioPain Dataset.zip"
    dataset_id = "physiopain_watch"
    if not path.exists():
        return pd.DataFrame(), CoverageEvent(dataset_id, "missing", reason=str(path))
    member = (
        "PhysioPain Dataset/PhysioPain Dataset/WATCH DATA/PROCESSED WATCH DATA/combined/"
        "combined_all_data/all_watch_data_16hz.csv"
    )
    frames: list[pd.DataFrame] = []
    with ZipFile(path) as zip_file:
        data = clean_columns(read_csv_member(zip_file, member))
    for (person_id, pain_type), group in data.groupby(["person_id", "pain_type"], sort=False, dropna=False):
        group = group.reset_index(drop=True)
        offsets = np.arange(len(group), dtype=float) / 16.0
        frame = sensor_frame(
            offsets,
            {
                "bvp": group["bvp"],
                "eda": group["eda"],
                "acc_x": group["x"],
                "acc_y": group["y"],
                "acc_z": group["z"],
                "temperature": group["temperature"],
                "pain_intensity": group["pain_scale"],
            },
        )
        pain_type_text = str(pain_type)
        meta = {
            "dataset_id": dataset_id,
            "subject_id": str(person_id),
            "session_id": f"{person_id}_{pain_type_text}",
            "condition": pain_type_text,
            "record_type": "processed_watch",
            "device": "watch_processed",
            "source_archive": "PhysioPain Dataset.zip",
            "source_member": member,
            "source_modality": "wrist",
            "pain_type": pain_type_text,
            "aux_state_label": pain_type_text,
        }
        frames.append(build_windows_for_session(frame, meta, config, label_scale="physiopain_pain_scale", label_confidence=0.8))
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return out, CoverageEvent(dataset_id, "ok", sessions=len(frames), rows=len(out))


def build_physio_eeg(config: WindowConfig) -> tuple[pd.DataFrame, CoverageEvent]:
    path = ROOT / "PhysioPain Dataset.zip"
    dataset_id = "physiopain_eeg"
    if not path.exists():
        return pd.DataFrame(), CoverageEvent(dataset_id, "missing", reason=str(path))
    frames: list[pd.DataFrame] = []
    with ZipFile(path) as zip_file:
        members = [
            name for name in zip_file.namelist()
            if "EEG DATA/RAW EEG DATA (1Hz)/All/" in name and name.endswith(".csv")
        ]
        for member in sorted(members):
            data = clean_columns(read_csv_member(zip_file, member, na_values=["NA"]))
            if data.empty:
                continue
            subject = str(data["id"].dropna().iloc[0]) if "id" in data.columns and data["id"].notna().any() else Path(member).stem
            pain_type = str(data["pain_type"].dropna().iloc[0]) if "pain_type" in data.columns and data["pain_type"].notna().any() else "unknown"
            offsets = numeric_series(data, "time").fillna(pd.Series(np.arange(len(data), dtype=float)))
            frame = sensor_frame(
                offsets.to_numpy(dtype=float),
                {
                    "eeg_delta": numeric_series(data, "Delta"),
                    "eeg_theta": numeric_series(data, "Theta"),
                    "eeg_alpha1": numeric_series(data, "Alpha1"),
                    "eeg_alpha2": numeric_series(data, "Alpha2"),
                    "eeg_beta1": numeric_series(data, "Beta1"),
                    "eeg_beta2": numeric_series(data, "Beta2"),
                    "eeg_gamma1": numeric_series(data, "Gamma1"),
                    "eeg_gamma2": numeric_series(data, "Gamma2"),
                    "eeg_attention": numeric_series(data, "Attention"),
                    "eeg_meditation": numeric_series(data, "Meditation"),
                },
            )
            meta = {
                "dataset_id": dataset_id,
                "subject_id": subject,
                "session_id": f"{subject}_eeg_{pain_type}",
                "condition": pain_type,
                "record_type": "raw_eeg_1hz",
                "device": "eeg_headset",
                "source_archive": "PhysioPain Dataset.zip",
                "source_member": member,
                "source_modality": "eeg",
                "pain_type": pain_type,
                "aux_state_label": pain_type,
            }
            frames.append(build_windows_for_session(frame, meta, config))
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return out, CoverageEvent(dataset_id, "ok", sessions=len(frames), rows=len(out))


def build_merged_stress(config: WindowConfig) -> tuple[pd.DataFrame, CoverageEvent]:
    path = ROOT / "archive(2).zip"
    dataset_id = "merged_wearable_stress"
    if not path.exists():
        return pd.DataFrame(), CoverageEvent(dataset_id, "missing", reason=str(path))
    with ZipFile(path) as zip_file:
        data = read_csv_member(
            zip_file,
            "merged_data.csv",
            usecols=["X", "Y", "Z", "EDA", "HR", "TEMP", "id", "label"],
            dtype={"X": "float32", "Y": "float32", "Z": "float32", "EDA": "float32", "HR": "float32", "TEMP": "float32", "id": "string", "label": "float32"},
        )
    frames: list[pd.DataFrame] = []
    for (subject, label), group in data.groupby(["id", "label"], sort=False, dropna=False):
        group = group.reset_index(drop=True)
        offsets = np.arange(len(group), dtype=float) / 32.0
        frame = sensor_frame(
            offsets,
            {
                "acc_x": group["X"],
                "acc_y": group["Y"],
                "acc_z": group["Z"],
                "eda": group["EDA"],
                "hr": group["HR"],
                "temperature": group["TEMP"],
            },
        )
        meta = {
            "dataset_id": dataset_id,
            "subject_id": str(subject),
            "session_id": f"{subject}_stress_label_{label}",
            "condition": f"stress_label_{label}",
            "record_type": "aligned_stress_proxy",
            "device": "wearable_merged",
            "source_archive": "archive(2).zip",
            "source_member": "merged_data.csv",
            "source_modality": "wrist",
            "proxy_label": float(label) if pd.notna(label) else None,
            "aux_state_label": f"stress_label_{label}",
        }
        frames.append(build_windows_for_session(frame, meta, config))
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return out, CoverageEvent(dataset_id, "ok", sessions=len(frames), rows=len(out))


def build_sports_sparse() -> tuple[pd.DataFrame, CoverageEvent]:
    path = ROOT / "archive(1).zip"
    dataset_id = "wearable_sports_health"
    if not path.exists():
        return pd.DataFrame(), CoverageEvent(dataset_id, "missing", reason=str(path))
    with ZipFile(path) as zip_file:
        data = clean_columns(read_csv_member(zip_file, "wearable_sports_health_dataset.csv"))
    rows: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        bp = str(row.get("Blood_Pressure", ""))
        match = re.match(r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)", bp)
        systolic = float(match.group(1)) if match else None
        diastolic = float(match.group(2)) if match else None
        out: dict[str, Any] = {
            "dataset_id": dataset_id,
            "subject_id": row.get("Athlete_ID"),
            "session_id": row.get("Athlete_ID"),
            "condition": str(row.get("Activity_Status", "")).lower(),
            "record_type": "sparse_wearable_sports",
            "device": "generic_wearable",
            "source_archive": "archive(1).zip",
            "source_member": "wearable_sports_health_dataset.csv",
            "source_modality": "sparse_wearable",
            "activity_status": row.get("Activity_Status"),
            "aux_state_label": str(row.get("Activity_Status", "")).lower(),
            "window_start_s": 0.0,
            "window_end_s": 0.0,
            "window_seconds": 0.0,
            "target_hz": 0.0,
            "source_rows": 1,
            "window_sampling": "sparse_row",
            "target_available": 0,
            "target_pain_nrs_0_10": None,
            "target_pain_min": None,
            "target_pain_max": None,
            "target_pain_count": 0,
            "target_pain_coverage": 0.0,
            "target_pain_class_3": None,
            "target_scale": None,
            "target_granularity": "none",
            "target_confidence": 0.0,
        }
        sparse_values = {
            "hr": row.get("Heart_Rate"),
            "temperature": row.get("Body_Temperature"),
            "bp_systolic": systolic,
            "bp_diastolic": diastolic,
            "spo2": row.get("Blood_Oxygen"),
            "steps": row.get("Step_Count"),
        }
        for block, value in sparse_values.items():
            out.update(series_features(block, np.array([0.0]), np.array([pd.to_numeric(value, errors="coerce")], dtype=float)))
        rows.append(out)
    out = pd.DataFrame(rows)
    return out, CoverageEvent(dataset_id, "ok", sessions=int(out["session_id"].nunique()), rows=len(out))


def build_sample_27(config: WindowConfig, include_heavy_imu: bool = False) -> tuple[pd.DataFrame, CoverageEvent]:
    path = ROOT / "sample(1).zip"
    dataset_id = "sample_27_9vuw"
    if not path.exists():
        return pd.DataFrame(), CoverageEvent(dataset_id, "missing", reason=str(path))
    selected = {
        "csv/27-9VUW/signals-e4-acc.csv": ("e4", {"x": "acc_x", "y": "acc_y", "z": "acc_z"}),
        "csv/27-9VUW/signals-e4-bvp.csv": ("e4", {"value": "bvp"}),
        "csv/27-9VUW/signals-e4-eda.csv": ("e4", {"value": "eda"}),
        "csv/27-9VUW/signals-e4-hr.csv": ("e4", {"value": "hr"}),
        "csv/27-9VUW/signals-e4-ibi.csv": ("e4", {"value": "ibi"}),
        "csv/27-9VUW/signals-e4-skt.csv": ("e4", {"value": "temperature"}),
        "csv/27-9VUW/signals-bh3-ecg.csv": ("bh3", {"value": "ecg"}),
        "csv/27-9VUW/signals-bh3-hr.csv": ("bh3", {"value": "hr"}),
        "csv/27-9VUW/signals-bh3-rsp.csv": ("bh3", {"value": "respiration"}),
        "csv/27-9VUW/signals-bh3-br.csv": ("bh3", {"value": "respiration"}),
    }
    if include_heavy_imu:
        selected.update(
            {
                "csv/27-9VUW/signals-front-gyro.csv": ("front", {"x": "gyro_x", "y": "gyro_y", "z": "gyro_z"}),
                "csv/27-9VUW/signals-back-gyro.csv": ("back", {"x": "gyro_x", "y": "gyro_y", "z": "gyro_z"}),
                "csv/27-9VUW/signals-back-acc.csv": ("back", {"x": "acc_x", "y": "acc_y", "z": "acc_z"}),
            }
        )
    frames_by_device: dict[str, list[pd.DataFrame]] = {}
    with ZipFile(path) as zip_file:
        for member, (device, mapping) in selected.items():
            if member not in zip_file.namelist():
                continue
            data = clean_columns(read_csv_member(zip_file, member))
            if "timestamp" not in data.columns:
                continue
            offsets = numeric_series(data, "timestamp").to_numpy(dtype=float)
            values = {target: numeric_series(data, source) for source, target in mapping.items() if source in data.columns}
            frames_by_device.setdefault(device, []).append(sensor_frame(offsets, values))
    frames: list[pd.DataFrame] = []
    for device, device_frames in frames_by_device.items():
        meta = {
            "dataset_id": dataset_id,
            "subject_id": "27-9VUW",
            "session_id": f"27-9VUW_{device}",
            "condition": "field_recording",
            "record_type": "sample_schema_prototype",
            "device": device,
            "source_archive": "sample(1).zip",
            "source_member": f"csv/27-9VUW/signals-{device}-*",
            "source_modality": "multi_device",
            "aux_state_label": "field_recording",
        }
        frames.append(build_windows_for_session(concat_sensor_frames(device_frames), meta, config))
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    reason = None if include_heavy_imu else "front/back/water high-volume auxiliary IMU files skipped in first all-dataset pass"
    return out, CoverageEvent(dataset_id, "ok", sessions=len(frames), rows=len(out), reason=reason)


def baseline_mask(frame: pd.DataFrame) -> pd.Series:
    text_columns = [column for column in ["condition", "activity_status", "aux_state_label", "pain_type"] if column in frame.columns]
    if not text_columns:
        return pd.Series(False, index=frame.index)
    joined = pd.Series("", index=frame.index, dtype="string")
    for column in text_columns:
        joined = joined.str.cat(frame[column].astype("string").fillna(""), sep=" ")
    lowered = joined.str.lower()
    mask = pd.Series(False, index=frame.index)
    for term in BASELINE_TERMS:
        mask = mask | lowered.str.contains(term, regex=False, na=False)
    if "target_pain_nrs_0_10" in frame.columns:
        pain = pd.to_numeric(frame["target_pain_nrs_0_10"], errors="coerce")
        mask = mask | (pain == 0)
    return mask.fillna(False)


def feature_mean_columns(frame: pd.DataFrame) -> list[str]:
    excluded_bits = ("baseline_", "delta_from_baseline", "z_from_baseline")
    columns = []
    for column in frame.columns:
        if any(bit in column for bit in excluded_bits):
            continue
        if column.endswith("__mean") or column.endswith("__mag__mean"):
            if pd.api.types.is_numeric_dtype(frame[column]):
                columns.append(column)
    return columns


def build_state_atlas(windows: pd.DataFrame, output_dir: Path, clusters: int = 12) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    if windows.empty:
        return pd.DataFrame()
    work = windows.reset_index(drop=True).copy()
    work.insert(0, "all_window_id", np.arange(len(work), dtype=np.int64))
    mean_cols = feature_mean_columns(work)
    if not mean_cols:
        return pd.DataFrame()

    is_baseline = baseline_mask(work)
    group_cols = ["dataset_id", "subject_id"]
    baseline_stats = work.loc[is_baseline, group_cols + mean_cols].groupby(group_cols, dropna=False).mean(numeric_only=True)
    key_index = pd.MultiIndex.from_frame(work[group_cols])
    centered = pd.DataFrame(index=work.index)
    for column in mean_cols:
        means = key_index.map(baseline_stats[column]).to_numpy(dtype=float) if column in baseline_stats.columns else np.full(len(work), np.nan)
        values = pd.to_numeric(work[column], errors="coerce").to_numpy(dtype=float)
        centered[column] = values - means
    baseline_available = key_index.isin(baseline_stats.index)
    abs_centered = centered.abs()
    assignment = work[
        [
            "all_window_id",
            "dataset_id",
            "subject_id",
            "session_id",
            "condition",
            "record_type",
            "device",
            "window_start_s",
            "window_end_s",
            "target_available",
            "target_pain_nrs_0_10",
        ]
    ].copy()
    assignment["baseline_candidate"] = is_baseline.to_numpy()
    assignment["baseline_anchor_available"] = baseline_available
    assignment["baseline_feature_count"] = abs_centered.notna().sum(axis=1).astype(int)
    assignment["baseline_abs_delta_mean"] = abs_centered.mean(axis=1, skipna=True)
    assignment["baseline_abs_delta_max"] = abs_centered.max(axis=1, skipna=True)
    assignment["baseline_l2_delta"] = np.sqrt(np.square(centered).sum(axis=1, skipna=True))
    quantiles = assignment.loc[assignment["baseline_anchor_available"], "baseline_l2_delta"].dropna().quantile([0.5, 0.8, 0.95])
    q50 = float(quantiles.get(0.5, 0.0)) if not quantiles.empty else 0.0
    q80 = float(quantiles.get(0.8, q50)) if not quantiles.empty else q50
    q95 = float(quantiles.get(0.95, q80)) if not quantiles.empty else q80
    conditions = [
        ~assignment["baseline_anchor_available"],
        assignment["baseline_l2_delta"] <= q50,
        assignment["baseline_l2_delta"] <= q80,
        assignment["baseline_l2_delta"] <= q95,
    ]
    choices = ["no_subject_baseline", "baseline_like", "moderate_departure", "strong_departure"]
    assignment["baseline_state_bin"] = np.select(conditions, choices, default="extreme_departure")

    matrix_source = work[mean_cols].replace([np.inf, -np.inf], np.nan)
    usable_cols = [column for column in mean_cols if matrix_source[column].notna().sum() >= max(20, len(work) * 0.01)]
    if usable_cols:
        pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("cluster", MiniBatchKMeans(n_clusters=min(clusters, len(work)), random_state=42, batch_size=2048, n_init=5)),
            ]
        )
        assignment["state_cluster_id"] = pipeline.fit_predict(matrix_source[usable_cols])
    else:
        assignment["state_cluster_id"] = -1

    assignment.to_parquet(output_dir / "baseline_state_assignments.parquet", compression="zstd", index=False)
    summary = (
        assignment.groupby(["state_cluster_id", "baseline_state_bin"], dropna=False)
        .agg(
            rows=("all_window_id", "size"),
            datasets=("dataset_id", "nunique"),
            subjects=("subject_id", "nunique"),
            target_available=("target_available", "sum"),
            mean_pain=("target_pain_nrs_0_10", "mean"),
            baseline_l2_delta_mean=("baseline_l2_delta", "mean"),
        )
        .reset_index()
        .sort_values(["rows"], ascending=False)
    )
    summary.to_csv(output_dir / "baseline_state_cluster_summary.csv", index=False)
    by_dataset = (
        assignment.groupby(["dataset_id", "baseline_state_bin"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values(["dataset_id", "rows"], ascending=[True, False])
    )
    by_dataset.to_csv(output_dir / "baseline_state_bins_by_dataset.csv", index=False)
    return assignment


def build_all(config: WindowConfig, output: Path, include_sample_heavy_imu: bool = False) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    coverage: list[CoverageEvent] = []
    if DEFAULT_NORMALIZED_WINDOWS.exists():
        normalized = pd.read_parquet(DEFAULT_NORMALIZED_WINDOWS)
        normalized["source_table"] = str(DEFAULT_NORMALIZED_WINDOWS.relative_to(ROOT))
        normalized["source_modality"] = normalized.get("source_modality", "normalized_direct_pain")
        frames.append(normalized)
        coverage.append(CoverageEvent("normalized_rheumapain_painmonit", "ok", sessions=int(normalized["session_id"].nunique()), rows=len(normalized)))
    builders = [
        build_catsa,
        build_induced_stress,
        build_wesad_e4,
        build_epm_e4_clean,
        build_physio_watch,
        build_physio_eeg,
        build_merged_stress,
        lambda cfg: build_sample_27(cfg, include_heavy_imu=include_sample_heavy_imu),
    ]
    sports_frame, sports_event = build_sports_sparse()
    frames.append(sports_frame)
    coverage.append(sports_event)
    for builder in builders:
        frame, event = builder(config)
        frames.append(frame)
        coverage.append(event)
        print(f"{event.dataset_id}: {event.status}, sessions={event.sessions}, rows={event.rows}", flush=True)
    combined = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True, sort=False)
    combined.to_parquet(output, compression="zstd", index=False)
    atlas_dir = output.parent / "state_atlas"
    assignments = build_state_atlas(combined, atlas_dir)
    manifest = {
        "config": asdict(config),
        "output": str(output),
        "rows": int(len(combined)),
        "columns": int(combined.shape[1]),
        "datasets": combined.groupby("dataset_id").size().reset_index(name="rows").to_dict(orient="records") if not combined.empty else [],
        "coverage": [asdict(event) for event in coverage],
        "state_atlas": {
            "assignments": str(atlas_dir / "baseline_state_assignments.parquet"),
            "cluster_summary": str(atlas_dir / "baseline_state_cluster_summary.csv"),
            "bins_by_dataset": str(atlas_dir / "baseline_state_bins_by_dataset.csv"),
            "rows": int(len(assignments)),
        },
    }
    write_json(output.parent / "manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build all-dataset archive-backed window features.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--target-hz", type=float, default=1.0)
    parser.add_argument("--window-seconds", type=float, default=30.0)
    parser.add_argument("--min-source-rows", type=int, default=2)
    parser.add_argument("--max-windows-per-session", type=int, default=2500)
    parser.add_argument("--include-sample-heavy-imu", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cap = args.max_windows_per_session if args.max_windows_per_session > 0 else None
    config = WindowConfig(
        target_hz=args.target_hz,
        window_seconds=args.window_seconds,
        min_source_rows=args.min_source_rows,
        max_windows_per_session=cap,
    )
    manifest = build_all(config, Path(args.output), include_sample_heavy_imu=args.include_sample_heavy_imu)
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
