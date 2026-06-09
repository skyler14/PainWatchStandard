"""Phase 3 task routing and label standardization."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd


DIRECT_PAIN_DATASETS = {"painmonit", "painmonit_pmed", "rheumapain", "physiopain_watch", "multimodal_pain_watch", "silver_pain"}
STRESS_PROXY_DATASETS = {"stress_reference_real", "stress_reference_synthetic", "merged_wearable_stress", "wesad", "wesad_respiban"}
EMOTION_PROXY_DATASETS = {"epm_e4"}
ACTIVITY_CONTEXT_DATASETS = {"induced_stress_exercise", "wearable_sports_health"}
BASELINE_TERMS = {"baseline", "rest", "resting", "neutral", "no_pain", "nopain", "no pain"}
COGNITIVE_TERMS = {"logic", "stroop", "sudoku"}
EXERCISE_TERMS = {"exercise", "aerobic", "anaerobic", "active"}


def _norm(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower()


def family_for_row(row: Mapping[str, Any] | pd.Series) -> str:
    dataset = _norm(row.get("dataset_id"))
    target = row.get("target_pain_nrs_0_10")
    stress_target = row.get("target_stress_binary")
    condition = _norm(row.get("condition") or row.get("aux_state_label") or row.get("activity_status") or row.get("pain_type"))
    if dataset in DIRECT_PAIN_DATASETS and target is not None and not pd.isna(target):
        return "direct_pain"
    if stress_target is not None and not pd.isna(stress_target):
        return "stress_proxy"
    if dataset in STRESS_PROXY_DATASETS:
        return "stress_proxy"
    if dataset == "catsa" and condition in BASELINE_TERMS:
        return "baseline_context"
    if dataset == "catsa" and condition in COGNITIVE_TERMS:
        return "cognitive_load_proxy"
    if dataset in EMOTION_PROXY_DATASETS:
        return "emotion_proxy"
    if dataset in ACTIVITY_CONTEXT_DATASETS or any(term in condition for term in EXERCISE_TERMS):
        return "exercise_context"
    if dataset in {"physiopain_eeg", "multimodal_pain_eeg"}:
        return "pain_context_unlabeled"
    if condition in BASELINE_TERMS:
        return "baseline_context"
    return "unlabeled"


def ordinal_pain_bin(value: Any) -> float:
    if value is None or pd.isna(value):
        return np.nan
    pain = float(value)
    if pain <= 0:
        return 0
    if pain < 4:
        return 1
    if pain < 7:
        return 2
    return 3
