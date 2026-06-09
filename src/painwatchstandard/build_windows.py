"""Build unified Phase 3 window feature tables from normalized streams."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from painwatchstandard.windowing import WindowConfig, build_windows_for_session


TEXT_COLUMNS = {
    "dataset_id",
    "subject_id",
    "session_id",
    "condition",
    "label_family",
    "pain_type",
    "device",
    "cohort",
    "record_type",
    "baseline_pair_session_id",
    "pain_protocol_kind",
    "aux_state_label",
    "survey_gender",
    "survey_pain_type",
    "workbook_sex",
    "workbook_diagnosis",
    "workbook_exercise_duration_text",
    "wesad_protocol_segment",
}

NUMERIC_CONTEXT_COLUMNS = {
    "target_stress_binary",
    "target_stress_score_0_10",
    "target_stress_score_mean_0_10",
    "survey_age",
    "survey_sleep_hours_avg",
    "survey_sleep_hours_before_test",
    "survey_daily_stress_ordinal",
    "survey_chronic_pain_flag",
    "survey_regular_medication_flag",
    "survey_pain_context_score",
    "workbook_age",
    "workbook_pain_rest",
    "workbook_pain_exercise",
    "wesad_protocol_start_s",
    "wesad_protocol_end_s",
}


@dataclass(frozen=True)
class WindowBuildOutput:
    path: str
    rows: int
    bytes: int
    input_streams: int


def _measurement_streams(input_root: Path) -> list[Path]:
    return sorted(input_root.rglob("measurement_stream.parquet"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _stable_window_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in TEXT_COLUMNS:
        if column not in out:
            out[column] = pd.NA
    for column in NUMERIC_CONTEXT_COLUMNS:
        if column not in out:
            out[column] = np.nan
    for column in TEXT_COLUMNS.intersection(out.columns):
        out[column] = out[column].astype("string")
    for column in out.columns:
        if column in TEXT_COLUMNS:
            continue
        if pd.api.types.is_object_dtype(out[column]):
            out[column] = pd.to_numeric(out[column], errors="coerce").astype("float64")
        elif pd.api.types.is_integer_dtype(out[column]) and not (
            column.endswith("__present")
            or column.endswith("__valid_count")
            or column.endswith("__peak_count")
            or column in {"source_rows", "target_available", "target_pain_count"}
        ):
            out[column] = out[column].astype("float64")
    preferred = [
        "dataset_id",
        "subject_id",
        "session_id",
        "condition",
        "label_family",
        "pain_type",
        "device",
        "cohort",
        "record_type",
        "baseline_pair_session_id",
        "pain_protocol_kind",
        "aux_state_label",
    ]
    ordered = [column for column in preferred if column in out.columns]
    ordered.extend(sorted(column for column in out.columns if column not in ordered))
    return out[ordered]


def build_unified_window_table(
    input_root: Path,
    output_path: Path,
    config: WindowConfig,
    max_sessions_per_stream: int | None = None,
) -> WindowBuildOutput:
    streams = _measurement_streams(input_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    total_rows = 0
    stream_summaries: list[dict[str, Any]] = []

    try:
        for stream_path in streams:
            frame = pd.read_parquet(stream_path)
            if frame.empty:
                continue
            if "session_id" not in frame or "sample_offset_s" not in frame:
                continue
            dataset_id = str(frame["dataset_id"].dropna().iloc[0]) if "dataset_id" in frame and not frame["dataset_id"].dropna().empty else stream_path.parent.parent.name
            session_count = 0
            stream_rows = 0
            for _, session in frame.groupby("session_id", sort=True, dropna=False):
                if max_sessions_per_stream is not None and session_count >= max_sessions_per_stream:
                    break
                windows = build_windows_for_session(session, config)
                if windows.empty:
                    continue
                windows = _stable_window_frame(windows)
                table = pa.Table.from_pandas(windows, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(output_path, table.schema, compression="zstd", use_dictionary=True)
                writer.write_table(table)
                total_rows += len(windows)
                stream_rows += len(windows)
                session_count += 1
            stream_summaries.append(
                {
                    "dataset_id": dataset_id,
                    "stream_path": str(stream_path),
                    "source_rows": len(frame),
                    "sessions_windowed": session_count,
                    "window_rows": stream_rows,
                }
            )
    finally:
        if writer is not None:
            writer.close()

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_root": str(input_root),
        "output_path": str(output_path),
        "target_hz": config.target_hz,
        "window_seconds": config.window_seconds,
        "include_partial_windows": config.include_partial_windows,
        "min_window_rows": config.min_window_rows,
        "rows": total_rows,
        "input_streams": len(streams),
        "streams": stream_summaries,
    }
    _write_json(output_path.with_suffix(".manifest.json"), manifest)
    return WindowBuildOutput(str(output_path), total_rows, output_path.stat().st_size if output_path.exists() else 0, len(streams))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build unified Phase 3 window features from normalized streams.")
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--target-hz", type=float, default=1.0)
    parser.add_argument("--window-seconds", type=float, default=30.0)
    parser.add_argument("--include-partial-windows", action="store_true")
    parser.add_argument("--min-window-rows", type=int, default=2)
    parser.add_argument("--max-sessions-per-stream", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    output = build_unified_window_table(
        Path(args.input_root),
        Path(args.output_path),
        WindowConfig(
            target_hz=args.target_hz,
            window_seconds=args.window_seconds,
            include_partial_windows=args.include_partial_windows,
            min_window_rows=args.min_window_rows,
        ),
        max_sessions_per_stream=args.max_sessions_per_stream,
    )
    print(json.dumps(asdict(output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
