#!/usr/bin/env python3
"""Fast labeled-dataset inventory and per-label sensor summaries.

Keeps source archives compressed. Uses bounded sampling for huge CSVs.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_ROOT = Path("/Users/skyler/Downloads/PainDatasets")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "outputs" / "labeled_dataset_analysis"


def _norm_cols(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [re.sub(r"_+", "_", re.sub(r"[^0-9A-Za-z]+", "_", str(c).strip())).strip("_").lower() for c in frame.columns]
    return frame


def _read_csv_from_zip(zf: zipfile.ZipFile, member: str, nrows: int | None = None, **kwargs: Any) -> pd.DataFrame:
    with zf.open(member) as raw:
        return _norm_cols(pd.read_csv(raw, nrows=nrows, **kwargs))


def _summary_numeric(frame: pd.DataFrame, group_cols: list[str], sensor_cols: list[str]) -> pd.DataFrame:
    present = [c for c in sensor_cols if c in frame.columns]
    for c in present:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    aggs = {c: ["count", "median", "mean", "std"] for c in present}
    return frame.groupby(group_cols, dropna=False, observed=True).agg(aggs).reset_index()


def _flat_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = ["__".join(str(x) for x in col if str(x)) if isinstance(col, tuple) else str(col) for col in out.columns]
    return out


def analyze_silver(root: Path, max_rows: int) -> dict[str, pd.DataFrame]:
    path = root / "SILVER-Pain Dataset.zip"
    frames = []
    with zipfile.ZipFile(path) as zf:
        for cohort, member in {
            "older_adults": "SILVER-Pain Dataset/data/older_adults/older_adults.csv",
            "young_adults": "SILVER-Pain Dataset/data/young_adults/young_adults.csv",
        }.items():
            frame = _read_csv_from_zip(zf, member, nrows=max_rows)
            frame["cohort"] = cohort
            frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data["painlevel"] = pd.to_numeric(data.get("painlevel"), errors="coerce")
    data["pain_bin"] = pd.cut(data["painlevel"], [-np.inf, 0, 3, 6, np.inf], labels=["zero", "mild", "moderate", "high"])
    label = data.groupby(["cohort", "painlevel", "pain_bin"], dropna=False, observed=True).agg(
        rows=("subject", "size"),
        subjects=("subject", "nunique"),
        trials=("trial", "nunique"),
        sections=("section", "nunique"),
        segments=("segment", "nunique"),
    ).reset_index()
    sensors = _flat_columns(_summary_numeric(data, ["cohort", "pain_bin"], ["bvp", "eda", "temperature", "hr"]))
    return {"silver_label_distribution": label, "silver_sensor_by_pain_bin": sensors}


def analyze_rheumapain(root: Path, max_files: int | None) -> dict[str, pd.DataFrame]:
    path = root / "RheumaPain Dataset.zip"
    frames = []
    with zipfile.ZipFile(path) as zf:
        members = [
            m for m in zf.namelist()
            if "/Processed Data/64Hz/" in m and m.endswith(".csv")
        ]
        if max_files:
            members = members[:max_files]
        for member in members:
            frame = _read_csv_from_zip(zf, member)
            frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data["pain_scale"] = pd.to_numeric(data.get("pain_scale"), errors="coerce")
    data["pain_bin"] = pd.cut(data["pain_scale"], [-np.inf, 0, 3, 6, np.inf], labels=["zero", "mild", "moderate", "high"])
    label = data.groupby(["exercise_rest", "pain_scale", "pain_bin"], dropna=False, observed=True).agg(
        rows=("person_id", "size"),
        subjects=("person_id", "nunique"),
    ).reset_index()
    sensors = _flat_columns(_summary_numeric(data, ["exercise_rest", "pain_bin"], ["bvp", "eda", "temperature", "x", "y", "z"]))
    return {"rheumapain_label_distribution": label, "rheumapain_sensor_by_pain_bin": sensors}


def analyze_physiopain_like(root: Path, archive_name: str, dataset_key: str, max_rows: int) -> dict[str, pd.DataFrame]:
    path = root / archive_name
    with zipfile.ZipFile(path) as zf:
        members = zf.namelist()
        preferred = [m for m in members if m.endswith("combined_all_data/all_watch_data_64hz.csv")]
        if not preferred:
            preferred = [m for m in members if "PROCESSED WATCH DATA" in m and m.endswith(".csv")]
        full_labels = []
        with zf.open(preferred[0]) as raw:
            for chunk in pd.read_csv(raw, usecols=["pain_scale", "pain_type", "person_id"], chunksize=500_000):
                full_labels.append(
                    chunk.groupby(["pain_type", "pain_scale"], dropna=False)
                    .agg(rows=("person_id", "size"), subjects=("person_id", "nunique"))
                    .reset_index()
                )
        full_label = (
            pd.concat(full_labels, ignore_index=True)
            .groupby(["pain_type", "pain_scale"], dropna=False)
            .agg(rows=("rows", "sum"), subjects=("subjects", "max"))
            .reset_index()
        )
        data = _read_csv_from_zip(zf, preferred[0], nrows=max_rows)
    data["pain_scale"] = pd.to_numeric(data.get("pain_scale"), errors="coerce")
    data["pain_bin"] = pd.cut(data["pain_scale"], [-np.inf, 0, 2, 4, np.inf], labels=["zero", "low", "moderate", "high"])
    label = data.groupby(["pain_type", "pain_scale", "pain_bin"], dropna=False, observed=True).agg(
        rows=("person_id", "size"),
        subjects=("person_id", "nunique"),
    ).reset_index()
    sensors = _flat_columns(_summary_numeric(data, ["pain_type", "pain_bin"], ["bvp", "eda", "temperature", "x", "y", "z"]))
    return {
        f"{dataset_key}_label_distribution_full": full_label,
        f"{dataset_key}_label_distribution_sample": label,
        f"{dataset_key}_sensor_by_pain_bin_sample": sensors,
    }


def analyze_painmonit(root: Path, max_sessions: int) -> dict[str, pd.DataFrame]:
    path = root / "PainMonit Database.zip"
    rows = []
    sensor_rows = []
    with zipfile.ZipFile(path) as outer:
        nested = outer.read("PMCD.zip")
    with zipfile.ZipFile(io.BytesIO(nested)) as zf:
        members = [
            m for m in zf.namelist()
            if m.lower().endswith(".csv") and not m.lower().endswith("_runup.csv") and "/raw-data/" in m.lower()
        ][:max_sessions]
        for member in members:
            frame = _read_csv_from_zip(zf, member, sep=";", decimal=",")
            frame["pain_rates"] = pd.to_numeric(frame.get("pain_rates"), errors="coerce")
            frame["pain_bin"] = pd.cut(frame["pain_rates"], [-np.inf, 0, 3, 6, np.inf], labels=["zero", "mild", "moderate", "high"])
            match = re.search(r"/(P(?P<subject>\d+)_(?P<trial>\d+))/", member)
            subject = f"p{match.group('subject')}" if match else member
            trial = int(match.group("trial")) if match else None
            rows.append({
                "subject": subject,
                "trial": trial,
                "rows": len(frame),
                "pain_nonnull": int(frame["pain_rates"].notna().sum()),
                "pain_min": float(frame["pain_rates"].min(skipna=True)) if frame["pain_rates"].notna().any() else None,
                "pain_median": float(frame["pain_rates"].median(skipna=True)) if frame["pain_rates"].notna().any() else None,
                "pain_max": float(frame["pain_rates"].max(skipna=True)) if frame["pain_rates"].notna().any() else None,
                "labels": ",".join(sorted(frame.get("pain_labels", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())),
            })
            by_bin = _flat_columns(_summary_numeric(frame, ["pain_bin"], ["bvp", "eda_e4", "tmp", "resp", "eda_rb", "bvp_rb", "emg", "grip"]))
            by_bin.insert(0, "subject", subject)
            by_bin.insert(1, "trial", trial)
            sensor_rows.append(by_bin)
    return {
        "painmonit_session_distribution": pd.DataFrame(rows),
        "painmonit_sensor_by_pain_bin": pd.concat(sensor_rows, ignore_index=True) if sensor_rows else pd.DataFrame(),
    }


def write_outputs(outputs: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, frame in outputs.items():
        path = out_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        manifest[name] = {"rows": int(len(frame)), "columns": list(map(str, frame.columns))}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-rows", type=int, default=250_000)
    parser.add_argument("--max-painmonit-sessions", type=int, default=18)
    parser.add_argument("--max-rheumapain-files", type=int, default=None)
    args = parser.parse_args()
    outputs: dict[str, pd.DataFrame] = {}
    outputs.update(analyze_silver(args.root, args.max_rows))
    outputs.update(analyze_rheumapain(args.root, args.max_rheumapain_files))
    outputs.update(analyze_physiopain_like(args.root, "PhysioPain Dataset.zip", "physiopain", args.max_rows))
    outputs.update(analyze_physiopain_like(args.root, "Multimodal Pain Dataset.zip", "multimodal_pain", args.max_rows))
    outputs.update(analyze_painmonit(args.root, args.max_painmonit_sessions))
    write_outputs(outputs, args.output)
    print(json.dumps({k: len(v) for k, v in outputs.items()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
