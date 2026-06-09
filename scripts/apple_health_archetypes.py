#!/usr/bin/env python3
"""Stream Apple Health export.zip into baseline/archetype summaries.

No full XML extraction. Reads zip member with lxml iterparse.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from lxml import etree


RECORD_TYPES = {
    "HKQuantityTypeIdentifierHeartRate",
    "HKQuantityTypeIdentifierRestingHeartRate",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
    "HKQuantityTypeIdentifierRespiratoryRate",
    "HKQuantityTypeIdentifierOxygenSaturation",
    "HKQuantityTypeIdentifierVO2Max",
    "HKQuantityTypeIdentifierPhysicalEffort",
    "HKQuantityTypeIdentifierAppleExerciseTime",
    "HKQuantityTypeIdentifierAppleStandTime",
    "HKQuantityTypeIdentifierActiveEnergyBurned",
    "HKQuantityTypeIdentifierStepCount",
    "HKCategoryTypeIdentifierSleepAnalysis",
    "HKCategoryTypeIdentifierAppleStandHour",
    "HKCategoryTypeIdentifierMindfulSession",
}


@dataclass(frozen=True)
class ParsedHealthExport:
    records: pd.DataFrame
    workouts: pd.DataFrame
    counts: dict[str, int]


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_export(zip_path: Path) -> ParsedHealthExport:
    rows: list[dict[str, Any]] = []
    workouts: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    with zipfile.ZipFile(zip_path) as zf, zf.open("apple_health_export/export.xml") as raw:
        for _, elem in etree.iterparse(raw, events=("end",), tag=("Record", "Workout")):
            if elem.tag == "Record":
                kind = elem.get("type")
                counts[kind or "unknown"] += 1
                if kind in RECORD_TYPES:
                    rows.append(
                        {
                            "type": kind,
                            "source": elem.get("sourceName"),
                            "unit": elem.get("unit"),
                            "start": elem.get("startDate"),
                            "end": elem.get("endDate"),
                            "value": elem.get("value"),
                            "numeric_value": _num(elem.get("value")),
                        }
                    )
            elif elem.tag == "Workout":
                counts["Workout"] += 1
                workouts.append(
                    {
                        "workout_type": elem.get("workoutActivityType"),
                        "start": elem.get("startDate"),
                        "end": elem.get("endDate"),
                        "duration_min": _num(elem.get("duration")),
                        "duration_unit": elem.get("durationUnit"),
                        "total_energy": _num(elem.get("totalEnergyBurned")),
                        "energy_unit": elem.get("totalEnergyBurnedUnit"),
                        "total_distance": _num(elem.get("totalDistance")),
                        "distance_unit": elem.get("totalDistanceUnit"),
                    }
                )
            elem.clear()
    records = pd.DataFrame(rows)
    workout_frame = pd.DataFrame(workouts)
    for frame in (records, workout_frame):
        if not frame.empty:
            frame["start_dt"] = pd.to_datetime(frame["start"], errors="coerce", utc=True)
            frame["end_dt"] = pd.to_datetime(frame["end"], errors="coerce", utc=True)
    return ParsedHealthExport(records, workout_frame, dict(counts))


def _minute_set(intervals: pd.DataFrame) -> set[pd.Timestamp]:
    minutes: set[pd.Timestamp] = set()
    if intervals.empty:
        return minutes
    for row in intervals.itertuples(index=False):
        start = getattr(row, "start_dt")
        end = getattr(row, "end_dt")
        if pd.isna(start) or pd.isna(end) or end < start:
            continue
        rng = pd.date_range(start.floor("min"), end.ceil("min"), freq="min")
        minutes.update(rng)
    return minutes


def _summary(series: pd.Series) -> dict[str, float | int | None]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {"n": 0, "median": None, "mean": None, "p10": None, "p90": None}
    return {
        "n": int(clean.shape[0]),
        "median": float(clean.median()),
        "mean": float(clean.mean()),
        "p10": float(clean.quantile(0.10)),
        "p90": float(clean.quantile(0.90)),
    }


def build_archetypes(parsed: ParsedHealthExport) -> dict[str, Any]:
    records = parsed.records.copy()
    workouts = parsed.workouts.copy()
    sleep = records[
        records["type"].eq("HKCategoryTypeIdentifierSleepAnalysis")
        & records["value"].astype(str).str.contains("Asleep", na=False)
    ]
    exercise = records[records["type"].eq("HKQuantityTypeIdentifierAppleExerciseTime")]
    stand = records[records["type"].eq("HKQuantityTypeIdentifierAppleStandTime")]
    sleep_minutes = _minute_set(sleep)
    workout_minutes = _minute_set(workouts)
    exercise_minutes = _minute_set(exercise)
    stand_minutes = _minute_set(stand)

    hr = records[records["type"].eq("HKQuantityTypeIdentifierHeartRate")].copy()
    if not hr.empty:
        hr["minute"] = hr["start_dt"].dt.floor("min")
        hr["archetype"] = "awake_nonworkout"
        hr.loc[hr["minute"].isin(sleep_minutes), "archetype"] = "sleep"
        hr.loc[hr["minute"].isin(stand_minutes), "archetype"] = "standing"
        hr.loc[hr["minute"].isin(workout_minutes | exercise_minutes), "archetype"] = "workout_or_exercise"
    hr_by_arch = {
        archetype: _summary(group["numeric_value"])
        for archetype, group in hr.groupby("archetype", dropna=False)
    }

    type_summary = {
        kind: _summary(records.loc[records["type"].eq(kind), "numeric_value"])
        for kind in sorted(RECORD_TYPES)
    }
    workout_summary = (
        workouts.groupby("workout_type", dropna=False)
        .agg(
            workouts=("workout_type", "size"),
            duration_min_median=("duration_min", "median"),
            duration_min_mean=("duration_min", "mean"),
            total_energy_median=("total_energy", "median"),
            total_distance_median=("total_distance", "median"),
        )
        .reset_index()
        .to_dict(orient="records")
        if not workouts.empty
        else []
    )
    return {
        "record_counts": parsed.counts,
        "natural_baseline_metrics": {
            "resting_heart_rate": type_summary.get("HKQuantityTypeIdentifierRestingHeartRate"),
            "walking_heart_rate_average": type_summary.get("HKQuantityTypeIdentifierWalkingHeartRateAverage"),
            "heart_rate_variability_sdnn": type_summary.get("HKQuantityTypeIdentifierHeartRateVariabilitySDNN"),
            "respiratory_rate": type_summary.get("HKQuantityTypeIdentifierRespiratoryRate"),
            "oxygen_saturation": type_summary.get("HKQuantityTypeIdentifierOxygenSaturation"),
            "vo2max": type_summary.get("HKQuantityTypeIdentifierVO2Max"),
            "physical_effort": type_summary.get("HKQuantityTypeIdentifierPhysicalEffort"),
        },
        "derived_heart_rate_archetypes": hr_by_arch,
        "workout_summary": workout_summary,
        "sleep_segments": int(len(sleep)),
        "exercise_time_segments": int(len(exercise)),
        "stand_time_segments": int(len(stand)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/apple_health_archetypes"))
    args = parser.parse_args()
    parsed = _read_export(args.zip_path)
    payload = build_archetypes(parsed)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "apple_health_archetypes.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(payload["workout_summary"]).to_csv(args.output / "workout_summary.csv", index=False)
    pd.DataFrame(payload["derived_heart_rate_archetypes"]).T.to_csv(args.output / "heart_rate_archetypes.csv")
    pd.DataFrame(payload["natural_baseline_metrics"]).T.to_csv(args.output / "natural_baseline_metrics.csv")
    print(json.dumps(payload["natural_baseline_metrics"], indent=2, sort_keys=True))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
