#!/usr/bin/env python3
"""Generalized sensor feeder for pain thermometer modeling.

The feeder converts normalized per-sample tables into model-ready window rows.
It keeps native samples for feature extraction, then emits one row per
prediction anchor at a configurable 1-10 Hz cadence.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "_normalized" / "window_features"
MIN_TARGET_HZ = 1.0
MAX_TARGET_HZ = 10.0


@dataclass(frozen=True)
class FeederConfig:
    target_hz: float = 1.0
    window_seconds: float = 30.0
    include_partial_windows: bool = False
    min_window_rows: int = 2
    baseline_conditions: tuple[str, ...] = ("rest", "baseline")

    @property
    def step_seconds(self) -> float:
        return 1.0 / self.target_hz


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    measurement_path: str
    input_columns: tuple[str, ...]
    label_regime: str
    label_scale: str
    label_confidence: float


SENSOR_BLOCKS: dict[str, tuple[str, ...]] = {
    "bvp": ("bvp",),
    "bvp_rb": ("bvp_rb",),
    "eda": ("eda",),
    "eda_rb": ("eda_rb",),
    "temperature": ("temperature",),
    "acc": ("acc_x", "acc_y", "acc_z"),
    "respiration": ("respiration",),
    "emg": ("emg",),
    "grip": ("grip",),
}


DATASET_SPECS: dict[str, DatasetSpec] = {
    "rheumapain": DatasetSpec(
        dataset_id="rheumapain",
        measurement_path="_normalized/rheumapain/frequency_hz=64/measurement_stream.parquet",
        input_columns=(
            "dataset_id",
            "subject_id",
            "session_id",
            "condition",
            "device",
            "sample_rate_hz",
            "sample_index",
            "sample_offset_s",
            "bvp",
            "eda",
            "acc_x",
            "acc_y",
            "acc_z",
            "temperature",
            "pain_score",
            "pain_scale_type",
            "diagnosis",
            "sex",
            "age",
        ),
        label_regime="session_weak",
        label_scale="wong_baker_faces_0_10",
        label_confidence=0.35,
    ),
    "painmonit": DatasetSpec(
        dataset_id="painmonit",
        measurement_path="_normalized/painmonit/clinical/measurement_stream.parquet",
        input_columns=(
            "dataset_id",
            "subject_id",
            "session_id",
            "session_number",
            "condition",
            "record_type",
            "device",
            "sample_rate_hz",
            "sample_index",
            "sample_offset_s",
            "bvp",
            "eda_e4",
            "temperature",
            "respiration",
            "eda_rb",
            "bvp_rb",
            "emg",
            "grip",
            "pain_rate_nrs",
            "pain_label",
            "pain_scale_type",
            "no_pain_threshold",
            "severe_pain_threshold",
        ),
        label_regime="sparse_sample",
        label_scale="nrs_0_10",
        label_confidence=0.75,
    ),
}


LABEL_MATCHES: list[dict[str, Any]] = [
    {
        "dataset_id": "painmonit",
        "source_column": "pain_rate_nrs",
        "canonical_target": "target_pain_nrs_0_10",
        "scale": "nrs_0_10",
        "granularity": "sparse_sample",
        "training_use": "primary dense/sparse direct pain target; train only windows with non-null target count",
    },
    {
        "dataset_id": "painmonit",
        "source_column": "pain_label",
        "canonical_target": "target_pain_class_3",
        "scale": "categorical_0_no_1_moderate_2_severe",
        "granularity": "sparse_sample",
        "training_use": "auxiliary ordinal/classification target when observed in a window",
    },
    {
        "dataset_id": "rheumapain",
        "source_column": "pain_score",
        "canonical_target": "target_pain_nrs_0_10",
        "scale": "wong_baker_faces_0_10",
        "granularity": "session_weak",
        "training_use": "weak session-level direct pain target; use with lower weight or session aggregation",
    },
    {
        "dataset_id": "physiopain",
        "source_column": "pain_scale",
        "canonical_target": "target_pain_nrs_0_10",
        "scale": "source_self_report_scale_to_confirm",
        "granularity": "processed_sample_or_segment_to_confirm",
        "training_use": "first-wave direct target after PhysioPain normalization validates scale semantics",
    },
    {
        "dataset_id": "physiopain",
        "source_column": "pain_type",
        "canonical_target": "target_pain_type",
        "scale": "categorical_pain_type",
        "granularity": "processed_sample_or_segment_to_confirm",
        "training_use": "context/stratification target, not intensity by itself",
    },
    {
        "dataset_id": "catsa_epm_wesad_proxy",
        "source_column": "stress_emotion_activity_labels",
        "canonical_target": "aux_arousal_context",
        "scale": "proxy_not_pain",
        "granularity": "dataset_specific",
        "training_use": "self-supervised/auxiliary context only; never direct pain truth",
    },
]


META_COLUMNS = (
    "dataset_id",
    "subject_id",
    "session_id",
    "session_number",
    "condition",
    "record_type",
    "device",
    "diagnosis",
    "sex",
    "age",
    "pain_scale_type",
    "no_pain_threshold",
    "severe_pain_threshold",
)


def validate_config(config: FeederConfig) -> None:
    if config.target_hz < MIN_TARGET_HZ or config.target_hz > MAX_TARGET_HZ:
        raise ValueError(f"target_hz must be between {MIN_TARGET_HZ:g} and {MAX_TARGET_HZ:g}")
    if config.window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    if config.min_window_rows < 1:
        raise ValueError("min_window_rows must be at least 1")


def _blank_series(length: int, value: Any = np.nan) -> pd.Series:
    return pd.Series([value] * length)


def _copy_numeric(source: pd.DataFrame, column: str, length: int) -> pd.Series:
    if column not in source.columns:
        return _blank_series(length)
    return pd.to_numeric(source[column], errors="coerce")


def _copy_text(source: pd.DataFrame, column: str, length: int) -> pd.Series:
    if column not in source.columns:
        return _blank_series(length, None)
    return source[column].astype("string")


def standardize_measurements(frame: pd.DataFrame, dataset_id: str) -> pd.DataFrame:
    """Map a normalized dataset table into the feeder's canonical columns."""
    if dataset_id not in DATASET_SPECS:
        raise KeyError(f"Unknown dataset_id: {dataset_id}")
    length = len(frame)
    out = pd.DataFrame(
        {
            "dataset_id": _copy_text(frame, "dataset_id", length).fillna(dataset_id),
            "subject_id": _copy_text(frame, "subject_id", length),
            "session_id": _copy_text(frame, "session_id", length),
            "condition": _copy_text(frame, "condition", length),
            "device": _copy_text(frame, "device", length),
            "sample_rate_hz": _copy_numeric(frame, "sample_rate_hz", length),
            "sample_index": _copy_numeric(frame, "sample_index", length),
            "sample_offset_s": _copy_numeric(frame, "sample_offset_s", length),
            "pain_scale_type": _copy_text(frame, "pain_scale_type", length),
        }
    )

    for column in ("session_number", "record_type", "diagnosis", "sex", "age", "no_pain_threshold", "severe_pain_threshold"):
        if column in {"age", "no_pain_threshold", "severe_pain_threshold", "session_number"}:
            out[column] = _copy_numeric(frame, column, length)
        else:
            out[column] = _copy_text(frame, column, length)

    if dataset_id == "rheumapain":
        out["bvp"] = _copy_numeric(frame, "bvp", length)
        out["eda"] = _copy_numeric(frame, "eda", length)
        out["temperature"] = _copy_numeric(frame, "temperature", length)
        out["acc_x"] = _copy_numeric(frame, "acc_x", length)
        out["acc_y"] = _copy_numeric(frame, "acc_y", length)
        out["acc_z"] = _copy_numeric(frame, "acc_z", length)
        out["pain_intensity"] = _copy_numeric(frame, "pain_score", length)
        out["pain_class"] = _blank_series(length)
    elif dataset_id == "painmonit":
        out["bvp"] = _copy_numeric(frame, "bvp", length)
        out["eda"] = _copy_numeric(frame, "eda_e4", length)
        out["temperature"] = _copy_numeric(frame, "temperature", length)
        out["respiration"] = _copy_numeric(frame, "respiration", length)
        out["eda_rb"] = _copy_numeric(frame, "eda_rb", length)
        out["bvp_rb"] = _copy_numeric(frame, "bvp_rb", length)
        out["emg"] = _copy_numeric(frame, "emg", length)
        out["grip"] = _copy_numeric(frame, "grip", length)
        out["pain_intensity"] = _copy_numeric(frame, "pain_rate_nrs", length)
        out["pain_class"] = _copy_numeric(frame, "pain_label", length)

    for column in ("bvp", "bvp_rb", "eda", "eda_rb", "temperature", "acc_x", "acc_y", "acc_z", "respiration", "emg", "grip"):
        if column not in out.columns:
            out[column] = _blank_series(length)

    out["acc_mag"] = np.sqrt(out["acc_x"] ** 2 + out["acc_y"] ** 2 + out["acc_z"] ** 2)
    out = out.sort_values(["subject_id", "session_id", "sample_offset_s"], kind="mergesort").reset_index(drop=True)
    return out


def _first_valid(series: pd.Series) -> Any:
    valid = series.dropna()
    if valid.empty:
        return None
    value = valid.iloc[0]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


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


def _series_features(prefix: str, times: np.ndarray, values: np.ndarray, denominator: int) -> dict[str, Any]:
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
        return features
    features[f"{prefix}__mean"] = float(np.nanmean(valid))
    features[f"{prefix}__std"] = float(np.nanstd(valid, ddof=0))
    features[f"{prefix}__min"] = float(np.nanmin(valid))
    features[f"{prefix}__max"] = float(np.nanmax(valid))
    features[f"{prefix}__last"] = float(valid[-1])
    features[f"{prefix}__slope_per_s"] = _slope_per_second(times, values)
    features[f"{prefix}__peak_count"] = _peak_count(values)
    return features


def _sensor_block_features(window: pd.DataFrame, block: str, columns: Iterable[str]) -> dict[str, Any]:
    times = window["sample_offset_s"].to_numpy(dtype=float)
    denominator = max(len(window), 1)
    features: dict[str, Any] = {}
    available = [column for column in columns if column in window.columns]
    if not available:
        features[f"{block}__present"] = 0
        features[f"{block}__valid_count"] = 0
        features[f"{block}__valid_frac"] = 0.0
        return features

    if block == "acc":
        for axis in ("acc_x", "acc_y", "acc_z"):
            features.update(_series_features(axis, times, window[axis].to_numpy(dtype=float), denominator))
        features.update(_series_features("acc__mag", times, window["acc_mag"].to_numpy(dtype=float), denominator))
        mag = window["acc_mag"].to_numpy(dtype=float)
        valid = mag[np.isfinite(mag)]
        features["acc__present"] = int(valid.size > 0)
        features["acc__valid_count"] = int(valid.size)
        features["acc__valid_frac"] = float(valid.size / denominator)
        if valid.size > 1:
            diffs = np.abs(np.diff(valid))
            features["acc__stillness_frac"] = float((diffs < 0.02).sum() / diffs.size)
        else:
            features["acc__stillness_frac"] = None
        return features

    column = available[0]
    features.update(_series_features(block, times, window[column].to_numpy(dtype=float), denominator))
    return features


def aggregate_labels(window: pd.DataFrame, dataset_id: str) -> dict[str, Any]:
    spec = DATASET_SPECS[dataset_id]
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
        "target_scale": spec.label_scale,
        "target_granularity": spec.label_regime if not pain.empty else "none",
        "target_confidence": spec.label_confidence if not pain.empty else 0.0,
    }
    if not pain.empty:
        result["target_pain_nrs_0_10"] = float(pain.mean())
        result["target_pain_min"] = float(pain.min())
        result["target_pain_max"] = float(pain.max())
    if not pain_class.empty:
        modes = pain_class.mode()
        result["target_pain_class_3"] = float(modes.iloc[0] if not modes.empty else pain_class.iloc[-1])
    return result


def make_window_anchors(session: pd.DataFrame, config: FeederConfig) -> np.ndarray:
    validate_config(config)
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


def build_windows_for_session(session: pd.DataFrame, dataset_id: str, config: FeederConfig) -> pd.DataFrame:
    validate_config(config)
    if session.empty:
        return pd.DataFrame()
    session = session.sort_values("sample_offset_s", kind="mergesort").reset_index(drop=True)
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
            "dataset_id": dataset_id,
            "subject_id": _first_valid(window["subject_id"]),
            "session_id": _first_valid(window["session_id"]),
            "window_start_s": float(start),
            "window_end_s": float(anchor),
            "window_seconds": float(anchor - start),
            "target_hz": float(config.target_hz),
            "source_rows": int(len(window)),
        }
        for column in META_COLUMNS:
            if column in {"dataset_id", "subject_id", "session_id"}:
                continue
            if column in window.columns:
                row[column] = _first_valid(window[column])

        for block, columns in SENSOR_BLOCKS.items():
            row.update(_sensor_block_features(window, block, columns))
        row.update(aggregate_labels(window, dataset_id))
        rows.append(row)

    return pd.DataFrame(rows)


def resample_to_grid(frame: pd.DataFrame, target_hz: float) -> pd.DataFrame:
    """Create aligned sensor means on a regular grid for inspection/debugging."""
    validate_config(FeederConfig(target_hz=target_hz))
    if frame.empty:
        return pd.DataFrame()
    data = frame.copy()
    offset = pd.to_numeric(data["sample_offset_s"], errors="coerce")
    data = data[offset.notna()].copy()
    if data.empty:
        return pd.DataFrame()
    data["grid_index"] = np.floor((data["sample_offset_s"] - data["sample_offset_s"].min()) * target_hz + 1e-9).astype("int64")
    numeric = [
        column
        for column in data.columns
        if column in set().union(*SENSOR_BLOCKS.values(), {"acc_mag", "pain_intensity", "pain_class"})
    ]
    grouped = data.groupby("grid_index", sort=True)
    out = grouped[numeric].mean(numeric_only=True).reset_index()
    meta = grouped[[column for column in META_COLUMNS if column in data.columns]].first().reset_index()
    out = meta.merge(out, on="grid_index", how="left")
    start = float(data["sample_offset_s"].min())
    out["grid_offset_s"] = start + out["grid_index"].astype(float) / target_hz
    out["target_hz"] = float(target_hz)
    return out


def drop_sensor_blocks(frame: pd.DataFrame, blocks: Iterable[str], seed: int | None = None, probability: float = 1.0) -> pd.DataFrame:
    """Blank full sensor blocks for modality-dropout style training augmentation."""
    rng = np.random.default_rng(seed)
    out = frame.copy()
    for block in blocks:
        if block not in SENSOR_BLOCKS:
            raise KeyError(f"Unknown sensor block: {block}")
        if rng.random() <= probability:
            for column in SENSOR_BLOCKS[block]:
                if column in out.columns:
                    out[column] = np.nan
            if block == "acc" and "acc_mag" in out.columns:
                out["acc_mag"] = np.nan
    return out


def attach_baseline_features(windows: pd.DataFrame, config: FeederConfig) -> pd.DataFrame:
    """Append personal-baseline deltas/z-scores without replacing raw features."""
    if windows.empty or "condition" not in windows.columns:
        windows = windows.copy()
        windows["baseline_available"] = False
        return windows

    out = windows.copy()
    condition = out["condition"].astype("string").str.lower()
    baseline_mask = condition.isin([item.lower() for item in config.baseline_conditions])
    mean_features = [
        column
        for column in out.columns
        if column.endswith("__mean") or column.endswith("__mag__mean")
    ]
    out["baseline_available"] = False
    if not mean_features or not baseline_mask.any():
        return out

    group_cols = ["dataset_id", "subject_id"]
    baseline = out.loc[baseline_mask, group_cols + mean_features]
    grouped = baseline.groupby(group_cols, dropna=False)
    baseline_mean = grouped[mean_features].mean(numeric_only=True)
    baseline_std = grouped[mean_features].std(ddof=0, numeric_only=True).replace(0, np.nan)

    key_index = pd.MultiIndex.from_frame(out[group_cols])
    out["baseline_available"] = key_index.isin(baseline_mean.index)
    for feature in mean_features:
        if feature in baseline_mean.columns:
            means = key_index.map(baseline_mean[feature]).to_numpy(dtype=float)
        else:
            means = np.full(len(out), np.nan)
        if feature in baseline_std.columns:
            stds = key_index.map(baseline_std[feature]).to_numpy(dtype=float)
        else:
            stds = np.full(len(out), np.nan)
        values = pd.to_numeric(out[feature], errors="coerce").to_numpy(dtype=float)
        out[f"{feature}__baseline_mean"] = means
        out[f"{feature}__baseline_std"] = stds
        out[f"{feature}__delta_from_baseline"] = values - means
        out[f"{feature}__z_from_baseline"] = (values - means) / stds
    return out


def load_dataset(dataset_id: str) -> pd.DataFrame:
    spec = DATASET_SPECS[dataset_id]
    path = ROOT / spec.measurement_path
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_parquet(path, columns=list(spec.input_columns))


def build_feature_table(
    dataset_ids: Iterable[str],
    config: FeederConfig,
    max_sessions: int | None = None,
    baseline_features: bool = True,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    session_count = 0
    for dataset_id in dataset_ids:
        standardized = standardize_measurements(load_dataset(dataset_id), dataset_id)
        for _, session in standardized.groupby(["subject_id", "session_id"], sort=False, dropna=False):
            session_windows = build_windows_for_session(session, dataset_id, config)
            if not session_windows.empty:
                frames.append(session_windows)
            session_count += 1
            if max_sessions is not None and session_count >= max_sessions:
                break
        if max_sessions is not None and session_count >= max_sessions:
            break
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if baseline_features:
        result = attach_baseline_features(result, config)
    return result


def summarize_windows(windows: pd.DataFrame) -> dict[str, Any]:
    if windows.empty:
        return {"rows": 0}
    by_dataset = windows.groupby("dataset_id").agg(
        rows=("dataset_id", "size"),
        subjects=("subject_id", "nunique"),
        sessions=("session_id", "nunique"),
        target_available=("target_available", "sum"),
    )
    label_counts = windows.groupby(["dataset_id", "target_granularity"]).size().reset_index(name="rows")
    return {
        "rows": int(len(windows)),
        "columns": int(windows.shape[1]),
        "by_dataset": by_dataset.reset_index().to_dict(orient="records"),
        "label_granularity": label_counts.to_dict(orient="records"),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def cmd_label_map(_: argparse.Namespace) -> None:
    print(json.dumps(LABEL_MATCHES, indent=2, sort_keys=True))


def cmd_build_windows(args: argparse.Namespace) -> None:
    dataset_ids = list(DATASET_SPECS) if args.dataset == "all" else [args.dataset]
    config = FeederConfig(
        target_hz=args.target_hz,
        window_seconds=args.window_seconds,
        include_partial_windows=args.include_partial_windows,
        min_window_rows=args.min_window_rows,
    )
    windows = build_feature_table(
        dataset_ids,
        config,
        max_sessions=args.max_sessions,
        baseline_features=not args.no_baseline_features,
    )
    output = Path(args.output) if args.output else DEFAULT_OUTPUT / f"target_hz={args.target_hz:g}" / "window_features.parquet"
    output.parent.mkdir(parents=True, exist_ok=True)
    windows.to_parquet(output, compression="zstd", index=False)
    summary = summarize_windows(windows)
    summary["output"] = str(output)
    summary["config"] = asdict(config)
    write_json(output.with_suffix(".manifest.json"), summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


def cmd_summarize(args: argparse.Namespace) -> None:
    path = Path(args.path)
    table = pq.ParquetFile(path)
    print(
        json.dumps(
            {
                "path": str(path),
                "rows": table.metadata.num_rows,
                "columns": table.metadata.num_columns,
                "row_groups": table.metadata.num_row_groups,
                "bytes": path.stat().st_size,
            },
            indent=2,
            sort_keys=True,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build model feeder tables from normalized pain datasets.")
    sub = parser.add_subparsers(dest="command", required=True)

    label_map = sub.add_parser("label-map", help="Print canonical label matches across datasets.")
    label_map.set_defaults(func=cmd_label_map)

    windows = sub.add_parser("build-windows", help="Build sliding native-sample window features.")
    windows.add_argument("--dataset", choices=["all", *DATASET_SPECS.keys()], default="all")
    windows.add_argument("--target-hz", type=float, default=1.0)
    windows.add_argument("--window-seconds", type=float, default=30.0)
    windows.add_argument("--min-window-rows", type=int, default=2)
    windows.add_argument("--include-partial-windows", action="store_true")
    windows.add_argument("--max-sessions", type=int, default=None)
    windows.add_argument("--no-baseline-features", action="store_true")
    windows.add_argument("--output", default=None)
    windows.set_defaults(func=cmd_build_windows)

    summarize = sub.add_parser("summarize", help="Summarize a feeder Parquet output.")
    summarize.add_argument("path")
    summarize.set_defaults(func=cmd_summarize)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
