#!/usr/bin/env python3
"""Combine multiscale temporal-shape experiment outputs into compact tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    5: ROOT / "outputs/temporal_shape_exploration_5s/model_comparison.csv",
    10: ROOT / "outputs/temporal_shape_exploration_10s/model_comparison.csv",
    30: ROOT / "outputs/temporal_shape_exploration/model_comparison.csv",
}
OUTPUT = ROOT / "outputs/temporal_shape_summary"


def main() -> None:
    frames = []
    for window_s, path in INPUTS.items():
        frame = pd.read_csv(path)
        frame.insert(0, "window_s", window_s)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT / "multiscale_model_comparison.csv", index=False)

    compact_sets = {
        "base_distribution",
        "base_temporal",
        "base_temporal_coupling",
        "base_temporal_shuffle",
        "quality",
    }
    scorecard = combined.loc[
        combined["split"].eq("group_subject_cv")
        & combined["feature_set"].isin(compact_sets)
    ].copy()
    scorecard.to_csv(OUTPUT / "within_dataset_scorecard.csv", index=False)

    pain_transfer = combined.loc[
        combined["task"].eq("pain_high_4_plus")
        & combined["split"].str.startswith("leave_dataset_out")
        & combined["feature_set"].isin({"base_distribution", "base_temporal"})
    ].copy()
    pain_transfer.to_csv(OUTPUT / "pain_leave_dataset_out.csv", index=False)

    dataset_only = combined.loc[combined["feature_set"].eq("dataset_only")].copy()
    dataset_only.to_csv(OUTPUT / "pain_dataset_only_control.csv", index=False)


if __name__ == "__main__":
    main()
