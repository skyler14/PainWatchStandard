#!/usr/bin/env python3
"""Build the Phase 3 multi-task feeder table.

Phase 3 keeps direct pain targets separate from auxiliary stress/activity/state
data. The output is still one row per modeling window, but every row carries
label-family and source-family fields so training can route gradients to the
right task head.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
DEFAULT_ALL_WINDOWS = WORKSPACE_ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "window_features.parquet"
DEFAULT_STATE_ATLAS = (
    WORKSPACE_ROOT
    / "_normalized"
    / "window_features_all"
    / "target_hz=1"
    / "state_atlas"
    / "baseline_state_assignments.parquet"
)
DEFAULT_STRESS_ROWS = REPO_ROOT / "phase_2" / "analysis" / "outputs" / "stress_reference_feeder_rows.parquet"
DEFAULT_OUTPUT = WORKSPACE_ROOT / "_normalized" / "phase3" / "target_hz=1" / "window_features.parquet"

DIRECT_PAIN_DATASETS = {"painmonit", "rheumapain", "physiopain_watch"}
STRESS_PROXY_DATASETS = {"stress_reference_real", "stress_reference_synthetic", "merged_wearable_stress", "wesad"}
EMOTION_PROXY_DATASETS = {"epm_e4"}
ACTIVITY_CONTEXT_DATASETS = {"induced_stress_exercise", "wearable_sports_health"}
BASELINE_TERMS = {"baseline", "rest", "resting", "neutral", "no_pain", "nopain", "no pain"}
COGNITIVE_TERMS = {"logic", "stroop", "sudoku"}
EXERCISE_TERMS = {"exercise", "aerobic", "anaerobic", "active"}


@dataclass(frozen=True)
class PrepareConfig:
    all_windows: str
    state_atlas: str
    stress_rows: str
    output: str


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def first_text(row: pd.Series, columns: tuple[str, ...]) -> str:
    for column in columns:
        if column in row.index:
            text = normalize_text(row[column])
            if text:
                return text
    return ""


def family_for_row(row: pd.Series) -> str:
    dataset = normalize_text(row.get("dataset_id"))
    target = row.get("target_pain_nrs_0_10")
    condition = first_text(row, ("condition", "aux_state_label", "aux_stress_label", "activity_status", "pain_type"))
    if dataset in DIRECT_PAIN_DATASETS and pd.notna(target):
        return "direct_pain"
    if dataset in STRESS_PROXY_DATASETS:
        return "stress_proxy"
    if dataset == "catsa":
        if condition in BASELINE_TERMS:
            return "baseline_context"
        if condition in COGNITIVE_TERMS:
            return "cognitive_load_proxy"
    if dataset in EMOTION_PROXY_DATASETS:
        return "emotion_proxy"
    if dataset in ACTIVITY_CONTEXT_DATASETS:
        return "exercise_context"
    if dataset == "physiopain_eeg":
        return "pain_context_unlabeled"
    if condition in BASELINE_TERMS:
        return "baseline_context"
    return "unlabeled"


def source_family_for_row(row: pd.Series) -> str:
    dataset = normalize_text(row.get("dataset_id"))
    modality = normalize_text(row.get("source_modality"))
    if dataset == "painmonit":
        return "clinical_direct_pain"
    if dataset == "rheumapain":
        return "weak_session_direct_pain"
    if dataset == "physiopain_watch":
        return "watch_direct_pain"
    if dataset.startswith("stress_reference"):
        return "derived_hr_eda_stress"
    if dataset in {"merged_wearable_stress", "wesad"}:
        return "wearable_stress_proxy"
    if dataset == "catsa":
        return "cognitive_baseline_proxy"
    if dataset == "epm_e4":
        return "emotion_wearable_proxy"
    if dataset in ACTIVITY_CONTEXT_DATASETS:
        return "activity_context"
    return modality or "unknown"


def collection_protocol_for_row(row: pd.Series) -> str:
    dataset = normalize_text(row.get("dataset_id"))
    source_dataset = normalize_text(row.get("source_dataset"))
    condition = first_text(row, ("condition", "record_type", "aux_state_label", "activity_status"))
    if dataset.startswith("stress_reference"):
        return f"xalentis_stress_{source_dataset or 'synthetic'}"
    if dataset == "painmonit":
        return "painmonit_pmcd_clinical"
    if dataset == "rheumapain":
        return "rheumapain_rest_exercise_session"
    if dataset == "physiopain_watch":
        return "physiopain_watch_pain_type"
    return f"{dataset}_{condition or 'unknown'}"


def pain_label_regime_for_row(row: pd.Series) -> str:
    dataset = normalize_text(row.get("dataset_id"))
    if family_for_row(row) != "direct_pain":
        return "none"
    if dataset == "painmonit":
        return "painmonit_sparse_nrs"
    if dataset == "rheumapain":
        return "rheumapain_weak_session_wong_baker"
    if dataset == "physiopain_watch":
        return "physiopain_watch_source_scale"
    return "direct_pain_unknown"


def stress_binary_for_row(row: pd.Series) -> float:
    dataset = normalize_text(row.get("dataset_id"))
    condition = first_text(row, ("condition", "aux_state_label", "aux_stress_label"))
    if dataset.startswith("stress_reference") and pd.notna(row.get("aux_stress_label")):
        return float(row.get("aux_stress_label"))
    if dataset == "merged_wearable_stress" and pd.notna(row.get("proxy_label")):
        return float(row.get("proxy_label") > 0)
    if dataset == "induced_stress_exercise":
        if condition == "stress":
            return 1.0
        if condition == "baseline":
            return 0.0
    if dataset == "catsa":
        if condition in BASELINE_TERMS:
            return 0.0
        if condition in COGNITIVE_TERMS:
            return 1.0
    return np.nan


def activity_binary_for_row(row: pd.Series) -> float:
    dataset = normalize_text(row.get("dataset_id"))
    condition = first_text(row, ("condition", "activity_status", "aux_state_label"))
    if dataset in ACTIVITY_CONTEXT_DATASETS or condition in EXERCISE_TERMS:
        if condition in BASELINE_TERMS or condition in {"sedentary", "rest"}:
            return 0.0
        if any(term in condition for term in EXERCISE_TERMS):
            return 1.0
    return np.nan


def baseline_binary_for_row(row: pd.Series) -> float:
    condition = first_text(row, ("condition", "aux_state_label", "activity_status", "record_type"))
    state_bin = normalize_text(row.get("baseline_state_bin"))
    if condition in BASELINE_TERMS or state_bin == "baseline_like":
        return 1.0
    if state_bin in {"moderate_departure", "strong_departure", "extreme_departure"}:
        return 0.0
    return np.nan


def ordinal_bin(value: Any) -> float:
    if pd.isna(value):
        return np.nan
    pain = float(value)
    if pain <= 0:
        return 0.0
    if pain < 4:
        return 1.0
    if pain < 7:
        return 2.0
    return 3.0


def load_all_windows(path: Path, state_atlas: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path).reset_index(drop=True)
    frame.insert(0, "phase3_source_table", "all_dataset_windows")
    frame.insert(1, "original_all_window_id", np.arange(len(frame), dtype=np.int64))
    if state_atlas.exists():
        atlas = pd.read_parquet(state_atlas)
        atlas = atlas.rename(columns={"all_window_id": "original_all_window_id"})
        frame = frame.merge(atlas, on="original_all_window_id", how="left", suffixes=("", "_atlas"))
    return frame


def load_stress_rows(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path).reset_index(drop=True)
    frame.insert(0, "phase3_source_table", "stress_reference_feeder_rows")
    frame.insert(1, "original_all_window_id", pd.NA)
    if "aux_state_label" not in frame.columns and "aux_stress_label" in frame.columns:
        frame["aux_state_label"] = frame["aux_stress_label"].map(lambda value: f"stress_{int(value)}" if pd.notna(value) else None)
    frame["baseline_state_bin"] = "no_subject_baseline"
    frame["baseline_anchor_available"] = 0
    return frame


def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["phase3_window_id"] = np.arange(len(frame), dtype=np.int64)
    frame["label_family"] = frame.apply(family_for_row, axis=1)
    frame["source_family"] = frame.apply(source_family_for_row, axis=1)
    frame["collection_protocol"] = frame.apply(collection_protocol_for_row, axis=1)
    frame["pain_label_regime"] = frame.apply(pain_label_regime_for_row, axis=1)
    frame["target_stress_binary"] = frame.apply(stress_binary_for_row, axis=1)
    frame["target_activity_binary"] = frame.apply(activity_binary_for_row, axis=1)
    frame["target_baseline_binary"] = frame.apply(baseline_binary_for_row, axis=1)
    frame["target_pain_ordinal_4"] = frame["target_pain_nrs_0_10"].map(ordinal_bin)
    frame["baseline_missing"] = frame.get("baseline_anchor_available", pd.Series(0, index=frame.index)).fillna(0).astype(float).eq(0).astype(int)
    frame["baseline_anchor_id"] = np.where(
        frame["baseline_missing"].eq(0),
        frame["dataset_id"].astype(str) + "::" + frame["subject_id"].astype(str),
        None,
    )
    frame["phase3_eval_group"] = frame["dataset_id"].astype(str) + "::" + frame["subject_id"].astype(str)
    return frame


def audit(frame: pd.DataFrame) -> dict[str, Any]:
    by_family = (
        frame.groupby(["label_family", "dataset_id"], dropna=False)
        .agg(
            rows=("phase3_window_id", "size"),
            subjects=("subject_id", "nunique"),
            sessions=("session_id", "nunique"),
            pain_targets=("target_pain_nrs_0_10", lambda value: int(pd.to_numeric(value, errors="coerce").notna().sum())),
            stress_targets=("target_stress_binary", lambda value: int(pd.to_numeric(value, errors="coerce").notna().sum())),
            activity_targets=("target_activity_binary", lambda value: int(pd.to_numeric(value, errors="coerce").notna().sum())),
            baseline_targets=("target_baseline_binary", lambda value: int(pd.to_numeric(value, errors="coerce").notna().sum())),
        )
        .reset_index()
        .sort_values(["label_family", "rows"], ascending=[True, False])
    )
    return {
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "by_label_family_dataset": by_family.to_dict(orient="records"),
    }


def build_phase3(config: PrepareConfig) -> dict[str, Any]:
    all_windows = load_all_windows(Path(config.all_windows), Path(config.state_atlas))
    stress_rows = load_stress_rows(Path(config.stress_rows))
    frame = pd.concat([all_windows, stress_rows], ignore_index=True, sort=False)
    frame = enrich(frame)
    output = Path(config.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, compression="zstd", index=False)
    audit_payload = audit(frame)
    audit_frame = pd.DataFrame(audit_payload["by_label_family_dataset"])
    audit_frame.to_csv(output.with_name("label_family_audit.csv"), index=False)
    manifest = {
        "config": asdict(config),
        "output": str(output),
        "audit": audit_payload,
        "sidecars": {
            "label_family_audit": str(output.with_name("label_family_audit.csv")),
        },
    }
    write_json(output.with_suffix(".manifest.json"), manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Phase 3 multi-task feeder table.")
    parser.add_argument("--all-windows", default=str(DEFAULT_ALL_WINDOWS))
    parser.add_argument("--state-atlas", default=str(DEFAULT_STATE_ATLAS))
    parser.add_argument("--stress-rows", default=str(DEFAULT_STRESS_ROWS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = PrepareConfig(
        all_windows=args.all_windows,
        state_atlas=args.state_atlas,
        stress_rows=args.stress_rows,
        output=args.output,
    )
    print(json.dumps(build_phase3(config), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
