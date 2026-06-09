"""Subject baseline profiles and robust baseline-relative features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


BASELINE_CONDITIONS = {"rest", "baseline", "resting", "neutral", "no_pain", "nopain", "no pain"}


@dataclass(frozen=True)
class SubjectBaselineProfile:
    dataset_id: str
    subject_id: str
    baseline_profile_id: str
    baseline_source: str
    baseline_label_state: str
    feature_stats: dict[str, dict[str, float | None]]
    n_windows: int
    quality_0_1: float


def _baseline_feature_columns(frame: pd.DataFrame) -> list[str]:
    return [
        column
        for column in frame.columns
        if (column.endswith("__mean") or column.endswith("__std") or column.endswith("__slope_per_s"))
        and pd.api.types.is_numeric_dtype(frame[column])
    ]


def _stats(values: pd.Series) -> dict[str, float | None]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {"median": None, "mean": None, "std": None, "mad": None, "p05": None, "p95": None}
    median = float(clean.median())
    mad = float((clean - median).abs().median())
    return {
        "median": median,
        "mean": float(clean.mean()),
        "std": float(clean.std(ddof=0)) if len(clean) > 1 else 0.0,
        "mad": mad,
        "p05": float(clean.quantile(0.05)),
        "p95": float(clean.quantile(0.95)),
    }


def build_subject_baseline_profile(
    frame: pd.DataFrame,
    dataset_id: str,
    subject_id: str,
    baseline_conditions: set[str] | None = None,
) -> SubjectBaselineProfile:
    conditions = baseline_conditions or BASELINE_CONDITIONS
    subject = frame.loc[frame["dataset_id"].eq(dataset_id) & frame["subject_id"].eq(subject_id)].copy()
    condition = subject.get("condition", pd.Series("", index=subject.index)).astype("string").str.lower()
    baseline = subject.loc[condition.isin(conditions)]
    feature_cols = _baseline_feature_columns(subject)
    stats = {column: _stats(baseline[column]) for column in feature_cols}
    quality = 0.0 if baseline.empty or not feature_cols else min(1.0, len(baseline) / 10.0)
    return SubjectBaselineProfile(
        dataset_id=dataset_id,
        subject_id=subject_id,
        baseline_profile_id=f"{dataset_id}::{subject_id}::explicit_rest::v1",
        baseline_source="explicit_rest" if not baseline.empty else "none",
        baseline_label_state="relaxed_rest" if not baseline.empty else "unknown_untrusted",
        feature_stats=stats,
        n_windows=int(len(baseline)),
        quality_0_1=float(quality),
    )


def attach_baseline_profile_features(frame: pd.DataFrame, profile: SubjectBaselineProfile) -> pd.DataFrame:
    out = frame.copy()
    available = profile.quality_0_1 > 0 and bool(profile.feature_stats)
    out["baseline_profile_id"] = profile.baseline_profile_id if available else None
    out["baseline_profile_available"] = bool(available)
    out["baseline_profile_quality_0_1"] = profile.quality_0_1
    out["baseline_state_label"] = profile.baseline_label_state
    distances: list[float] = []
    for feature, stats in profile.feature_stats.items():
        if feature not in out.columns:
            continue
        median = stats.get("median")
        mad = stats.get("mad")
        values = pd.to_numeric(out[feature], errors="coerce")
        if median is None:
            delta = pd.Series(np.nan, index=out.index)
            robust_z = pd.Series(np.nan, index=out.index)
        else:
            delta = values - float(median)
            denom = 1.4826 * float(mad) if mad and mad > 0 else np.nan
            robust_z = delta / denom
            distances.append(delta.abs())
        out[f"{feature}__delta_from_profile_median"] = delta
        out[f"{feature}__robust_z_from_profile"] = robust_z
    out["baseline_distance_l1"] = pd.concat(distances, axis=1).mean(axis=1) if distances else np.nan
    return out
