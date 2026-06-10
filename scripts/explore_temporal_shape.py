#!/usr/bin/env python
"""Compare simple summaries with temporal-shape features on raw 30-second windows."""

from __future__ import annotations

import argparse
import json
import math
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pywt
from scipy import stats
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


SENSORS = (
    "bvp",
    "eda",
    "temperature",
    "hr",
    "ibi",
    "ecg",
    "respiration",
    "emg",
    "grip",
    "acc_x",
    "acc_y",
    "acc_z",
)

COUPLING_PAIRS = (
    ("hr", "eda"),
    ("bvp", "eda"),
    ("hr", "respiration"),
    ("eda", "temperature"),
    ("hr", "acc_mag"),
    ("eda", "acc_mag"),
    ("bvp", "acc_mag"),
)

PAIN_DATASETS = (
    "painmonit",
    "painmonit_pmed",
    "physiopain_watch",
    "rheumapain",
    "silver_pain",
)

DATASET_PATHS = {
    "catsa": "catsa/e4_tasks/measurement_stream.parquet",
    "induced_stress_exercise": "induced_stress_exercise/e4_activity/measurement_stream.parquet",
    "painmonit": "painmonit/clinical/measurement_stream.parquet",
    "painmonit_pmed": "painmonit_pmed/experimental_heat/measurement_stream.parquet",
    "physiopain_watch": "physiopain_watch/watch_64hz/measurement_stream.parquet",
    "rheumapain": "rheumapain/frequency_hz=64/measurement_stream.parquet",
    "silver_pain": "silver_pain/merged/measurement_stream.parquet",
    "wesad": "wesad/e4_full/measurement_stream.parquet",
}


@dataclass(frozen=True)
class ExperimentConfig:
    window_seconds: float = 30.0
    resample_hz: float = 4.0
    max_sessions_per_dataset: int = 40
    max_windows_per_session: int = 10
    random_seed: int = 20260609


def _finite(values: np.ndarray) -> np.ndarray:
    return values[np.isfinite(values)]


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if math.isfinite(number) else np.nan


def _longest_run(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    return int(np.max(ends - starts)) if starts.size else 0


def _autocorr(values: np.ndarray, lag: int) -> float:
    if values.size <= lag or lag < 1:
        return np.nan
    left = values[:-lag]
    right = values[lag:]
    if np.std(left) < 1e-12 or np.std(right) < 1e-12:
        return np.nan
    return float(np.corrcoef(left, right)[0, 1])


def _spectral(values: np.ndarray, hz: float) -> dict[str, float]:
    centered = values - np.mean(values)
    power = np.abs(np.fft.rfft(centered)) ** 2
    freq = np.fft.rfftfreq(values.size, d=1.0 / hz)
    if power.size <= 1 or np.sum(power[1:]) <= 0:
        return {
            "dominant_frequency": np.nan,
            "spectral_centroid": np.nan,
            "spectral_entropy": np.nan,
            "low_band_power": np.nan,
            "mid_band_power": np.nan,
            "high_band_power": np.nan,
        }
    power[0] = 0.0
    total = float(np.sum(power))
    probability = power / total
    entropy = -np.sum(probability[probability > 0] * np.log(probability[probability > 0]))
    entropy /= math.log(max(int(np.count_nonzero(probability)), 2))

    def band(low: float, high: float) -> float:
        return float(np.sum(power[(freq >= low) & (freq < high)]) / total)

    return {
        "dominant_frequency": float(freq[int(np.argmax(power))]),
        "spectral_centroid": float(np.sum(freq * power) / total),
        "spectral_entropy": float(entropy),
        "low_band_power": band(0.0, 0.15),
        "mid_band_power": band(0.15, 0.5),
        "high_band_power": band(0.5, hz / 2.0 + 1e-9),
    }


def _wavelet(values: np.ndarray) -> dict[str, float]:
    try:
        max_level = min(3, pywt.dwt_max_level(values.size, pywt.Wavelet("db2").dec_len))
        if max_level < 1:
            return {}
        coeffs = pywt.wavedec(values, "db2", level=max_level)
    except ValueError:
        return {}
    energies = np.asarray([np.sum(np.square(coefficient)) for coefficient in coeffs], dtype=float)
    total = float(np.sum(energies))
    if total <= 0:
        return {}
    return {f"wavelet_energy_{index}": float(value / total) for index, value in enumerate(energies)}


def _resample(
    times: np.ndarray,
    values: np.ndarray,
    start: float,
    end: float,
    hz: float,
) -> np.ndarray | None:
    mask = np.isfinite(times) & np.isfinite(values)
    x = times[mask]
    y = values[mask]
    if x.size < 4:
        return None
    unique_x, unique_indices = np.unique(x, return_index=True)
    y = y[unique_indices]
    if unique_x.size < 4 or unique_x[-1] - unique_x[0] < 1.0:
        return None
    grid = np.arange(start, end + 0.5 / hz, 1.0 / hz)
    if grid.size < 8:
        return None
    return np.interp(grid, unique_x, y, left=y[0], right=y[-1])


def _base_features(values: np.ndarray) -> dict[str, float]:
    valid = _finite(values)
    if valid.size == 0:
        return {}
    return {
        "mean": float(np.mean(valid)),
        "std": float(np.std(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "last": float(valid[-1]),
    }


def _shape_features(values: np.ndarray, hz: float) -> dict[str, float]:
    valid = _finite(values)
    if valid.size < 8:
        return {}
    median = float(np.median(valid))
    mad = float(np.median(np.abs(valid - median)))
    scale = mad * 1.4826
    if scale < 1e-9:
        scale = float(np.std(valid))
    if scale < 1e-9:
        scale = 1.0
    z = (valid - median) / scale
    difference = np.diff(z)
    second_difference = np.diff(z, n=2)
    half = max(z.size // 2, 1)
    above = z > 0
    crossings = np.count_nonzero(np.diff(above.astype(np.int8)) != 0)
    quantiles = np.quantile(valid, [0.10, 0.25, 0.75, 0.90])
    output = {
        "median": median,
        "mad": mad,
        "q10": float(quantiles[0]),
        "q25": float(quantiles[1]),
        "q75": float(quantiles[2]),
        "q90": float(quantiles[3]),
        "iqr": float(quantiles[2] - quantiles[1]),
        "skew": _safe_float(stats.skew(z, bias=False)),
        "kurtosis": _safe_float(stats.kurtosis(z, fisher=True, bias=False)),
        "rms_z": float(np.sqrt(np.mean(np.square(z)))),
        "late_minus_early_z": float(np.mean(z[half:]) - np.mean(z[:half])),
        "last_minus_first_z": float(z[-1] - z[0]),
        "max_time_fraction": float(np.argmax(z) / max(z.size - 1, 1)),
        "min_time_fraction": float(np.argmin(z) / max(z.size - 1, 1)),
        "mean_abs_diff_z": float(np.mean(np.abs(difference))) if difference.size else np.nan,
        "std_diff_z": float(np.std(difference)) if difference.size else np.nan,
        "max_abs_diff_z": float(np.max(np.abs(difference))) if difference.size else np.nan,
        "second_diff_energy": float(np.mean(np.square(second_difference))) if second_difference.size else np.nan,
        "median_crossings": float(crossings),
        "longest_above_median_frac": float(_longest_run(above) / z.size),
        "longest_below_median_frac": float(_longest_run(~above) / z.size),
        "autocorr_025s": _autocorr(z, max(int(round(0.25 * hz)), 1)),
        "autocorr_05s": _autocorr(z, max(int(round(0.5 * hz)), 1)),
        "autocorr_1s": _autocorr(z, max(int(round(1.0 * hz)), 1)),
        "autocorr_2s": _autocorr(z, max(int(round(2.0 * hz)), 1)),
    }
    output.update(_spectral(z, hz))
    output.update(_wavelet(z))
    return output


def _cross_sensor_features(left: np.ndarray, right: np.ndarray, hz: float) -> dict[str, float]:
    mask = np.isfinite(left) & np.isfinite(right)
    x = left[mask]
    y = right[mask]
    if x.size < 12 or np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return {}
    x = (x - np.mean(x)) / np.std(x)
    y = (y - np.mean(y)) / np.std(y)
    contemporaneous = float(np.corrcoef(x, y)[0, 1])
    max_lag = max(int(round(2.0 * hz)), 1)
    candidates: list[tuple[float, int]] = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            a, b = x[-lag:], y[:lag]
        elif lag > 0:
            a, b = x[:-lag], y[lag:]
        else:
            a, b = x, y
        if a.size >= 8 and np.std(a) > 0 and np.std(b) > 0:
            candidates.append((float(np.corrcoef(a, b)[0, 1]), lag))
    if not candidates:
        return {"correlation": contemporaneous}
    best_correlation, best_lag = max(candidates, key=lambda pair: abs(pair[0]))
    return {
        "correlation": contemporaneous,
        "max_abs_lagged_correlation": float(best_correlation),
        "lag_at_max_correlation_s": float(best_lag / hz),
    }


def extract_window_features(
    window: pd.DataFrame,
    start: float,
    end: float,
    config: ExperimentConfig,
    seed: int,
) -> dict[str, float]:
    output: dict[str, float] = {}
    times = pd.to_numeric(window["sample_offset_s"], errors="coerce").to_numpy(dtype=float)
    resampled: dict[str, np.ndarray] = {}
    available_sensors = list(SENSORS)
    if {"acc_x", "acc_y", "acc_z"}.issubset(window.columns):
        available_sensors.append("acc_mag")
    for sensor in available_sensors:
        if sensor == "acc_mag":
            axes = [
                pd.to_numeric(window[axis], errors="coerce").to_numpy(dtype=float)
                for axis in ("acc_x", "acc_y", "acc_z")
            ]
            values = np.sqrt(np.square(axes[0]) + np.square(axes[1]) + np.square(axes[2]))
        elif sensor in window.columns:
            values = pd.to_numeric(window[sensor], errors="coerce").to_numpy(dtype=float)
        else:
            continue
        valid_count = int(np.isfinite(values).sum())
        output[f"{sensor}__quality__valid_count"] = float(valid_count)
        output[f"{sensor}__quality__valid_frac"] = float(valid_count / max(len(window), 1))
        for name, value in _base_features(values).items():
            output[f"{sensor}__base__{name}"] = value
        regular = _resample(times, values, start, end, config.resample_hz)
        if regular is None:
            continue
        resampled[sensor] = regular
        for name, value in _shape_features(regular, config.resample_hz).items():
            output[f"{sensor}__shape__{name}"] = value
        rng = np.random.default_rng(seed + sum(ord(character) for character in sensor))
        shuffled = regular.copy()
        rng.shuffle(shuffled)
        for name, value in _shape_features(shuffled, config.resample_hz).items():
            output[f"{sensor}__shuffle__{name}"] = value
        reversed_values = regular[::-1]
        for name, value in _shape_features(reversed_values, config.resample_hz).items():
            output[f"{sensor}__reverse__{name}"] = value
    for left_name, right_name in COUPLING_PAIRS:
        if left_name not in resampled or right_name not in resampled:
            continue
        for name, value in _cross_sensor_features(
            resampled[left_name],
            resampled[right_name],
            config.resample_hz,
        ).items():
            output[f"{left_name}_x_{right_name}__coupling__{name}"] = value
    return output


def _balanced_session_sample(
    frame: pd.DataFrame,
    max_sessions: int,
    seed: int,
) -> pd.DataFrame:
    sessions = (
        frame[["dataset_id", "subject_id", "session_id", "y"]]
        .drop_duplicates(["dataset_id", "session_id"])
        .copy()
    )
    if len(sessions) <= max_sessions:
        return frame
    selected: list[str] = []
    per_class = max(max_sessions // max(sessions["y"].nunique(), 1), 1)
    for label, group in sessions.groupby("y"):
        take = min(per_class, len(group))
        selected.extend(group.sample(take, random_state=seed + int(label) * 31)["session_id"].astype(str))
    if len(selected) < max_sessions:
        remaining = sessions[~sessions["session_id"].astype(str).isin(selected)]
        take = min(max_sessions - len(selected), len(remaining))
        if take:
            selected.extend(remaining.sample(take, random_state=seed + 999)["session_id"].astype(str))
    return frame[frame["session_id"].astype(str).isin(selected[:max_sessions])].copy()


def _sample_windows(
    frame: pd.DataFrame,
    max_windows_per_session: int,
    seed: int,
) -> pd.DataFrame:
    sampled: list[pd.DataFrame] = []
    for index, (_, session) in enumerate(frame.groupby(["dataset_id", "session_id"], sort=True)):
        session = session.sort_values("window_end_s")
        if len(session) <= max_windows_per_session:
            sampled.append(session)
            continue
        if session["y"].nunique() > 1:
            pieces = []
            per_class = max(max_windows_per_session // session["y"].nunique(), 1)
            for label, class_rows in session.groupby("y"):
                pieces.append(
                    class_rows.sample(
                        min(per_class, len(class_rows)),
                        random_state=seed + index * 17 + int(label),
                    )
                )
            selected = pd.concat(pieces)
            if len(selected) < max_windows_per_session:
                remainder = session.drop(index=selected.index)
                take = min(max_windows_per_session - len(selected), len(remainder))
                if take:
                    selected = pd.concat(
                        [selected, remainder.sample(take, random_state=seed + index * 17 + 99)]
                    )
            sampled.append(selected.sort_values("window_end_s"))
        else:
            indices = np.linspace(0, len(session) - 1, max_windows_per_session).round().astype(int)
            sampled.append(session.iloc[np.unique(indices)])
    return pd.concat(sampled, ignore_index=True) if sampled else frame.iloc[0:0].copy()


def make_anchor_table(master_path: Path, config: ExperimentConfig) -> pd.DataFrame:
    columns = [
        "dataset_id",
        "subject_id",
        "session_id",
        "condition",
        "window_end_s",
        "target_pain_nrs_0_10",
        "target_stress_binary",
    ]
    master = pd.read_parquet(master_path, columns=columns)
    tasks: list[pd.DataFrame] = []

    pain = master[
        master["dataset_id"].isin(PAIN_DATASETS) & master["target_pain_nrs_0_10"].notna()
    ].copy()
    pain["target_value"] = pd.to_numeric(pain["target_pain_nrs_0_10"], errors="coerce")
    pmed = pain["dataset_id"].eq("painmonit_pmed")
    pain.loc[pmed, "target_value"] = pain.loc[pmed, "target_value"] / 10.0
    pain["y"] = (pain["target_value"] >= 4.0).astype(int)
    pain["task"] = "pain_high_4_plus"
    for dataset_id, dataset_rows in pain.groupby("dataset_id"):
        sampled_sessions = _balanced_session_sample(
            dataset_rows,
            config.max_sessions_per_dataset,
            config.random_seed + sum(map(ord, dataset_id)),
        )
        tasks.append(
            _sample_windows(
                sampled_sessions,
                config.max_windows_per_session,
                config.random_seed + 100,
            )
        )

    wesad = master[
        master["dataset_id"].eq("wesad") & master["target_stress_binary"].notna()
    ].copy()
    wesad["target_value"] = pd.to_numeric(wesad["target_stress_binary"], errors="coerce")
    wesad["y"] = wesad["target_value"].astype(int)
    wesad["task"] = "wesad_stress"
    tasks.append(_sample_windows(wesad, config.max_windows_per_session * 3, config.random_seed + 200))

    induced = master[master["dataset_id"].eq("induced_stress_exercise")].copy()
    induced = induced[induced["condition"].isin(["stress", "aerobic", "anaerobic"])]
    induced["target_value"] = induced["condition"].eq("stress").astype(float)
    induced["y"] = induced["target_value"].astype(int)
    induced["task"] = "stress_vs_exercise"
    tasks.append(_sample_windows(induced, config.max_windows_per_session, config.random_seed + 300))

    catsa = master[master["dataset_id"].eq("catsa")].copy()
    catsa["target_value"] = ~catsa["condition"].eq("baseline")
    catsa["y"] = catsa["target_value"].astype(int)
    catsa["task"] = "cognitive_load_vs_baseline"
    catsa = _balanced_session_sample(
        catsa,
        config.max_sessions_per_dataset * 2,
        config.random_seed + 400,
    )
    tasks.append(_sample_windows(catsa, config.max_windows_per_session, config.random_seed + 401))

    anchors = pd.concat(tasks, ignore_index=True)
    anchors = anchors.drop_duplicates(["task", "dataset_id", "session_id", "window_end_s"])
    return anchors[
        [
            "task",
            "dataset_id",
            "subject_id",
            "session_id",
            "condition",
            "window_end_s",
            "target_value",
            "y",
        ]
    ].sort_values(["task", "dataset_id", "session_id", "window_end_s"])


def extract_anchor_features(
    anchors: pd.DataFrame,
    normalized_root: Path,
    config: ExperimentConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = anchors.groupby(["dataset_id", "session_id"], sort=True)
    total = len(grouped)
    for group_index, ((dataset_id, session_id), session_anchors) in enumerate(grouped, start=1):
        relative_path = DATASET_PATHS[str(dataset_id)]
        path = normalized_root / relative_path
        available = set(pq.ParquetFile(path).schema.names)
        columns = [
            column
            for column in (
                "session_id",
                "sample_offset_s",
                "target_pain_nrs_0_10",
                "target_stress_binary",
                *SENSORS,
            )
            if column in available
        ]
        table = pq.read_table(path, columns=columns, filters=[("session_id", "=", str(session_id))])
        session = table.to_pandas()
        if session.empty:
            continue
        session = session.sort_values("sample_offset_s", kind="mergesort").reset_index(drop=True)
        times = pd.to_numeric(session["sample_offset_s"], errors="coerce").to_numpy(dtype=float)
        for anchor_index, anchor in session_anchors.iterrows():
            end = float(anchor["window_end_s"])
            start = end - config.window_seconds
            left = int(np.searchsorted(times, start, side="right"))
            right = int(np.searchsorted(times, end, side="right"))
            window = session.iloc[left:right]
            if len(window) < 2:
                continue
            task = str(anchor["task"])
            target_value = float(anchor["target_value"])
            y = int(anchor["y"])
            recent = window[
                pd.to_numeric(window["sample_offset_s"], errors="coerce") > end - 1.0
            ]
            if task == "pain_high_4_plus" and "target_pain_nrs_0_10" in window:
                target = pd.to_numeric(
                    recent["target_pain_nrs_0_10"],
                    errors="coerce",
                ).dropna()
                if target.empty:
                    target = pd.to_numeric(
                        window["target_pain_nrs_0_10"],
                        errors="coerce",
                    ).dropna()
                if target.empty:
                    continue
                target_value = float(target.median())
                if dataset_id == "painmonit_pmed":
                    target_value /= 10.0
                y = int(target_value >= 4.0)
            elif task == "wesad_stress" and "target_stress_binary" in window:
                target = pd.to_numeric(
                    recent["target_stress_binary"],
                    errors="coerce",
                ).dropna()
                if target.empty:
                    target = pd.to_numeric(
                        window["target_stress_binary"],
                        errors="coerce",
                    ).dropna()
                if target.empty:
                    continue
                target_value = float(target.iloc[-1])
                y = int(target_value >= 0.5)
            feature_row: dict[str, Any] = {
                "task": task,
                "dataset_id": dataset_id,
                "subject_id": anchor["subject_id"],
                "session_id": session_id,
                "condition": anchor["condition"],
                "window_end_s": end,
                "target_value": target_value,
                "y": y,
                "source_rows": len(window),
            }
            feature_row.update(
                extract_window_features(
                    window,
                    start,
                    end,
                    config,
                    seed=config.random_seed + int(anchor_index),
                )
            )
            rows.append(feature_row)
        if group_index % 25 == 0 or group_index == total:
            print(f"extracted_sessions={group_index}/{total} windows={len(rows)}", flush=True)
    return pd.DataFrame(rows)


def _feature_columns(frame: pd.DataFrame, groups: Iterable[str]) -> list[str]:
    markers = tuple(f"__{group}__" for group in groups)
    return [column for column in frame.columns if any(marker in column for marker in markers)]


TEMPORAL_FEATURE_NAMES = (
    "late_minus_early_z",
    "last_minus_first_z",
    "max_time_fraction",
    "min_time_fraction",
    "mean_abs_diff_z",
    "std_diff_z",
    "max_abs_diff_z",
    "second_diff_energy",
    "median_crossings",
    "longest_above_median_frac",
    "longest_below_median_frac",
    "autocorr_025s",
    "autocorr_05s",
    "autocorr_1s",
    "autocorr_2s",
    "dominant_frequency",
    "spectral_centroid",
    "spectral_entropy",
    "low_band_power",
    "mid_band_power",
    "high_band_power",
    "wavelet_energy_0",
    "wavelet_energy_1",
    "wavelet_energy_2",
    "wavelet_energy_3",
)


def _shape_subset(frame: pd.DataFrame, group: str, temporal: bool) -> list[str]:
    marker = f"__{group}__"
    selected = []
    for column in frame.columns:
        if marker not in column:
            continue
        name = column.split(marker, 1)[1]
        is_temporal = name in TEMPORAL_FEATURE_NAMES
        if is_temporal == temporal:
            selected.append(column)
    return selected


def _numeric_pipeline(model: Any) -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
            ("model", model),
        ]
    )


def _metric_row(
    task: str,
    dataset_id: str,
    split: str,
    model_name: str,
    feature_set: str,
    y_true: np.ndarray,
    probability: np.ndarray,
    train_rows: int,
    test_rows: int,
    feature_count: int,
) -> dict[str, Any]:
    return {
        "task": task,
        "dataset_id": dataset_id,
        "split": split,
        "model": model_name,
        "feature_set": feature_set,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "feature_count": feature_count,
        "prevalence": float(np.mean(y_true)),
        "auc": float(roc_auc_score(y_true, probability)) if np.unique(y_true).size == 2 else np.nan,
        "average_precision": (
            float(average_precision_score(y_true, probability))
            if np.unique(y_true).size == 2
            else np.nan
        ),
        "brier": float(brier_score_loss(y_true, probability)),
    }


def evaluate_group_cv(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = _feature_columns(frame, ("base",))
    temporal = _shape_subset(frame, "shape", temporal=True)
    distribution = _shape_subset(frame, "shape", temporal=False)
    temporal_shuffle = _shape_subset(frame, "shuffle", temporal=True)
    temporal_reverse = _shape_subset(frame, "reverse", temporal=True)
    coupling = _feature_columns(frame, ("coupling",))
    feature_sets = {
        "base": base,
        "base_distribution": base + distribution,
        "base_temporal": base + temporal,
        "base_temporal_coupling": base + temporal + coupling,
        "base_temporal_shuffle": base + temporal_shuffle,
        "base_temporal_reverse": base + temporal_reverse,
        "base_shape": _feature_columns(frame, ("base", "shape")),
        "base_shape_coupling": _feature_columns(frame, ("base", "shape", "coupling")),
        "base_shuffle": _feature_columns(frame, ("base", "shuffle")),
        "base_reverse": _feature_columns(frame, ("base", "reverse")),
        "quality_only": _feature_columns(frame, ("quality",)),
    }
    models = {
        "logistic": LogisticRegression(max_iter=2000, class_weight="balanced", C=0.3),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=250,
            min_samples_leaf=4,
            max_features="sqrt",
            class_weight="balanced",
            random_state=20260609,
            n_jobs=-1,
        ),
    }
    metric_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    for (task, dataset_id), subset in frame.groupby(["task", "dataset_id"], sort=True):
        subset = subset.reset_index(drop=True)
        if subset["y"].nunique() < 2 or subset["subject_id"].nunique() < 3:
            continue
        folds = min(5, subset["subject_id"].nunique())
        splitter = GroupKFold(n_splits=folds)
        for feature_set, columns in feature_sets.items():
            columns = [column for column in columns if subset[column].notna().any()]
            if not columns:
                continue
            for model_name, base_model in models.items():
                predictions = np.full(len(subset), np.nan)
                fold_importance = np.zeros(len(columns), dtype=float)
                used_folds = 0
                for train_index, test_index in splitter.split(
                    subset[columns],
                    subset["y"],
                    groups=subset["subject_id"],
                ):
                    y_train = subset.loc[train_index, "y"].to_numpy(dtype=int)
                    y_test = subset.loc[test_index, "y"].to_numpy(dtype=int)
                    if np.unique(y_train).size < 2:
                        continue
                    pipeline = _numeric_pipeline(clone(base_model))
                    pipeline.fit(subset.loc[train_index, columns], y_train)
                    predictions[test_index] = pipeline.predict_proba(
                        subset.loc[test_index, columns]
                    )[:, 1]
                    estimator = pipeline.named_steps["model"]
                    if hasattr(estimator, "feature_importances_"):
                        fold_importance += estimator.feature_importances_
                    elif hasattr(estimator, "coef_"):
                        fold_importance += np.abs(estimator.coef_[0])
                    used_folds += 1
                valid = np.isfinite(predictions)
                if valid.sum() == 0:
                    continue
                metric_rows.append(
                    _metric_row(
                        str(task),
                        str(dataset_id),
                        "group_subject_cv",
                        model_name,
                        feature_set,
                        subset.loc[valid, "y"].to_numpy(dtype=int),
                        predictions[valid],
                        int(len(subset) * (folds - 1) / folds),
                        int(valid.sum()),
                        len(columns),
                    )
                )
                if used_folds:
                    for column, importance in sorted(
                        zip(columns, fold_importance / used_folds),
                        key=lambda pair: pair[1],
                        reverse=True,
                    )[:20]:
                        importance_rows.append(
                            {
                                "task": task,
                                "dataset_id": dataset_id,
                                "model": model_name,
                                "feature_set": feature_set,
                                "feature": column,
                                "importance": float(importance),
                            }
                        )
    return pd.DataFrame(metric_rows), pd.DataFrame(importance_rows)


def evaluate_pain_leave_dataset_out(frame: pd.DataFrame) -> pd.DataFrame:
    pain = frame[frame["task"].eq("pain_high_4_plus")].reset_index(drop=True)
    base = _feature_columns(pain, ("base",))
    temporal = _shape_subset(pain, "shape", temporal=True)
    distribution = _shape_subset(pain, "shape", temporal=False)
    temporal_shuffle = _shape_subset(pain, "shuffle", temporal=True)
    coupling = _feature_columns(pain, ("coupling",))
    feature_sets = {
        "base": base,
        "base_distribution": base + distribution,
        "base_temporal": base + temporal,
        "base_temporal_coupling": base + temporal + coupling,
        "base_temporal_shuffle": base + temporal_shuffle,
        "base_shape": _feature_columns(pain, ("base", "shape")),
        "base_shape_coupling": _feature_columns(pain, ("base", "shape", "coupling")),
        "base_shuffle": _feature_columns(pain, ("base", "shuffle")),
        "quality_only": _feature_columns(pain, ("quality",)),
    }
    rows: list[dict[str, Any]] = []
    for heldout in sorted(pain["dataset_id"].unique()):
        train = pain[~pain["dataset_id"].eq(heldout)]
        test = pain[pain["dataset_id"].eq(heldout)]
        if train["y"].nunique() < 2 or test["y"].nunique() < 2:
            continue
        for feature_set, columns in feature_sets.items():
            # Keep only features observed in every training and held-out dataset.
            common = []
            for column in columns:
                if not test[column].notna().any():
                    continue
                if all(group[column].notna().any() for _, group in train.groupby("dataset_id")):
                    common.append(column)
            if not common:
                continue
            pipeline = _numeric_pipeline(
                LogisticRegression(max_iter=2000, class_weight="balanced", C=0.3)
            )
            pipeline.fit(train[common], train["y"])
            probability = pipeline.predict_proba(test[common])[:, 1]
            rows.append(
                _metric_row(
                    "pain_high_4_plus",
                    str(heldout),
                    "leave_dataset_out",
                    "logistic",
                    feature_set,
                    test["y"].to_numpy(dtype=int),
                    probability,
                    len(train),
                    len(test),
                    len(common),
                )
            )
    return pd.DataFrame(rows)


def evaluate_dataset_only(frame: pd.DataFrame) -> pd.DataFrame:
    pain = frame[frame["task"].eq("pain_high_4_plus")].reset_index(drop=True)
    if pain["dataset_id"].nunique() < 2:
        return pd.DataFrame()
    transformer = ColumnTransformer(
        [("dataset", OneHotEncoder(handle_unknown="ignore"), ["dataset_id"])],
        remainder="drop",
    )
    pipeline = Pipeline(
        [
            ("encode", transformer),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    folds = min(5, pain["subject_id"].nunique())
    splitter = GroupKFold(n_splits=folds)
    predictions = np.full(len(pain), np.nan)
    for train_index, test_index in splitter.split(
        pain[["dataset_id"]],
        pain["y"],
        groups=pain["subject_id"],
    ):
        pipeline.fit(pain.loc[train_index, ["dataset_id"]], pain.loc[train_index, "y"])
        predictions[test_index] = pipeline.predict_proba(
            pain.loc[test_index, ["dataset_id"]]
        )[:, 1]
    valid = np.isfinite(predictions)
    return pd.DataFrame(
        [
            _metric_row(
                "pain_high_4_plus",
                "pooled",
                "group_subject_cv",
                "logistic",
                "dataset_only",
                pain.loc[valid, "y"].to_numpy(dtype=int),
                predictions[valid],
                len(pain),
                int(valid.sum()),
                pain["dataset_id"].nunique(),
            )
        ]
    )


def write_outputs(
    output_dir: Path,
    config: ExperimentConfig,
    anchors: pd.DataFrame,
    features: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    anchors.to_csv(output_dir / "sampled_anchors.csv", index=False)
    features.to_parquet(output_dir / "temporal_shape_features.parquet", index=False)
    cv_metrics, importance = evaluate_group_cv(features)
    leave_dataset = evaluate_pain_leave_dataset_out(features)
    dataset_only = evaluate_dataset_only(features)
    metrics = pd.concat([cv_metrics, leave_dataset, dataset_only], ignore_index=True)
    metrics.to_csv(output_dir / "model_comparison.csv", index=False)
    importance.to_csv(output_dir / "feature_importance.csv", index=False)
    manifest = {
        "config": asdict(config),
        "anchor_rows": len(anchors),
        "feature_rows": len(features),
        "feature_columns": len(features.columns),
        "task_counts": (
            features.groupby(["task", "dataset_id"])
            .size()
            .rename("rows")
            .reset_index()
            .to_dict(orient="records")
        ),
        "class_counts": (
            features.groupby(["task", "dataset_id", "y"])
            .size()
            .rename("rows")
            .reset_index()
            .to_dict(orient="records")
        ),
        "pmed_scale_correction": "target_pain_nrs_0_10 divided by 10 because raw COVAS is 0-100",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(metrics.sort_values(["task", "dataset_id", "model", "feature_set"]).to_string(index=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--normalized-root",
        default="_normalized/full_enriched4",
        type=Path,
    )
    parser.add_argument(
        "--master-path",
        default="_normalized/phase3_enriched/target_hz=1/window_features.parquet",
        type=Path,
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/temporal_shape_exploration",
        type=Path,
    )
    parser.add_argument("--max-sessions-per-dataset", type=int, default=40)
    parser.add_argument("--max-windows-per-session", type=int, default=10)
    parser.add_argument("--window-seconds", type=float, default=30.0)
    parser.add_argument("--resample-hz", type=float, default=4.0)
    return parser


def main() -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    args = build_parser().parse_args()
    config = ExperimentConfig(
        window_seconds=args.window_seconds,
        resample_hz=args.resample_hz,
        max_sessions_per_dataset=args.max_sessions_per_dataset,
        max_windows_per_session=args.max_windows_per_session,
    )
    anchors = make_anchor_table(args.master_path, config)
    print(
        anchors.groupby(["task", "dataset_id", "y"]).size().rename("anchors").to_string(),
        flush=True,
    )
    features = extract_anchor_features(anchors, args.normalized_root, config)
    write_outputs(args.output_dir, config, anchors, features)


if __name__ == "__main__":
    main()
