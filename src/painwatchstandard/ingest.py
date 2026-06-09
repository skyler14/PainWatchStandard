"""Compressed-source dataset ingest for PainWatchStandard.

The ingest layer writes wide, per-sample Parquet streams. It does not create
pain truth from context datasets. Pain labels only come from explicit pain
columns or dataset labels.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from painwatchstandard.normalizers.painmonit import clean_numeric, normalize_column, parse_painmonit_session
from painwatchstandard.routing import family_for_row, ordinal_pain_bin


DEFAULT_SOURCE_ROOT = Path("/Users/skyler/Downloads/PainDatasets")
DEFAULT_OUTPUT_ROOT = Path("_normalized")

OPTIONAL_STREAM_COLUMNS = {
    "ibi",
    "ecg",
    "heater_c",
    "source_sample_rate_hz",
    "record_type",
    "baseline_pair_session_id",
    "pain_protocol_kind",
    "aux_state_label",
    "target_stress_binary",
    "target_stress_score_0_10",
    "target_stress_score_mean_0_10",
    "survey_age",
    "survey_gender",
    "survey_sleep_hours_avg",
    "survey_sleep_hours_before_test",
    "survey_daily_stress_ordinal",
    "survey_chronic_pain_flag",
    "survey_regular_medication_flag",
    "survey_pain_context_score",
    "survey_pain_type",
    "workbook_age",
    "workbook_sex",
    "workbook_diagnosis",
    "workbook_pain_rest",
    "workbook_pain_exercise",
    "workbook_exercise_duration_text",
    "wesad_protocol_segment",
    "wesad_protocol_start_s",
    "wesad_protocol_end_s",
}

NUMERIC_OPTIONAL_STREAM_COLUMNS = {
    "ibi",
    "ecg",
    "heater_c",
    "source_sample_rate_hz",
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
class IngestOutput:
    dataset_id: str
    output_kind: str
    path: str
    rows: int
    bytes: int


class ParquetSink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.writer: pq.ParquetWriter | None = None
        self.rows = 0
        self.columns: list[str] | None = None

    def write(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        frame = frame.copy()
        for column in OPTIONAL_STREAM_COLUMNS:
            if column not in frame:
                frame[column] = np.nan if column in NUMERIC_OPTIONAL_STREAM_COLUMNS else pd.NA
        if self.columns is None:
            self.columns = list(frame.columns)
        else:
            for column in self.columns:
                if column not in frame:
                    frame[column] = pd.NA
            extra = [column for column in frame.columns if column not in self.columns]
            if extra:
                if self.writer is not None:
                    raise ValueError(f"New columns after writer initialization for {self.path}: {extra}")
                self.columns.extend(extra)
            frame = frame[self.columns]
        for column in frame.columns:
            if column == "sample_index":
                continue
            if column in NUMERIC_OPTIONAL_STREAM_COLUMNS:
                frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
            elif pd.api.types.is_numeric_dtype(frame[column]):
                frame[column] = frame[column].astype("float64")
            elif pd.api.types.is_object_dtype(frame[column]) or pd.api.types.is_string_dtype(frame[column]):
                frame[column] = frame[column].astype("string")
        table = pa.Table.from_pandas(frame, preserve_index=False)
        if self.writer is None:
            self.writer = pq.ParquetWriter(self.path, table.schema, compression="zstd", use_dictionary=True)
        self.writer.write_table(table)
        self.rows += len(frame)

    def close(self) -> None:
        if self.writer is not None:
            self.writer.close()


def clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def clean_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        text = str(value).strip().replace(",", ".")
        if not text or text.lower() in {"nan", "<na>"}:
            return None
        return float(text)
    except ValueError:
        return None


def numeric_first(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    for match in re.findall(r"\d+(?:\.\d+)?", str(value).replace(",", ".")):
        return float(match)
    return None


def yes_no_flag(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"yes", "y", "evet", "true", "1"} or "yes" in text or "evet" in text:
        return 1.0
    if text in {"no", "n", "hayır", "hayir", "false", "0"} or "no" in text or "hayır" in text or "hayir" in text:
        return 0.0
    return None


def ordinal_text_score(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    direct = numeric_first(value)
    if direct is not None:
        return direct
    text = str(value).strip().lower()
    mapping = {
        "not severe": 0.0,
        "hiç": 0.0,
        "low": 1.0,
        "mild": 1.0,
        "hafif": 1.0,
        "moderate": 3.0,
        "orta": 3.0,
        "high": 4.0,
        "severe": 5.0,
        "şiddetli": 5.0,
        "stressed": 4.0,
        "stressli": 4.0,
    }
    for key, score in mapping.items():
        if key in text:
            return score
    return None


def load_rheumapain_workbook(source_root: Path) -> dict[str, dict[str, Any]]:
    archive = archive_path(source_root, "RheumaPain Dataset.zip")
    with zipfile.ZipFile(archive) as zf:
        member = next(name for name in zf.namelist() if name.endswith("RheumaPain/Demographic Data/patients.xlsx"))
        with zf.open(member) as raw:
            frame = pd.read_excel(raw)
    frame.columns = [normalize_column(c) for c in frame.columns]
    rows: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        subject = clean_text(row.get("uid"))
        if not subject:
            continue
        rows[subject.lower()] = {
            "workbook_age": clean_float(row.get("age")),
            "workbook_sex": clean_text(row.get("gender")),
            "workbook_diagnosis": clean_text(row.get("diagnosis")),
            "workbook_pain_rest": clean_float(row.get("pain_scale_rest")),
            "workbook_pain_exercise": clean_float(row.get("pain_scale_exercise")),
            "workbook_exercise_duration_text": clean_text(row.get("exercise_durations_seconds")),
        }
    return rows


def load_physio_survey_metrics(source_root: Path, archive_name: str) -> dict[str, dict[str, Any]]:
    archive = archive_path(source_root, archive_name)
    with zipfile.ZipFile(archive) as zf:
        members = [name for name in zf.namelist() if name.endswith("SURVEY DATA/survey_answers_en.xlsx")]
        if not members:
            return {}
        with zf.open(members[0]) as raw:
            frame = pd.read_excel(raw)
    rows: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        subject = clean_text(row.get("id"))
        if not subject:
            continue
        pain_severity_cols = [col for col in frame.columns if "Rate the severity of your pain" in str(col)]
        pain_scores = [ordinal_text_score(row.get(col)) for col in pain_severity_cols]
        pain_scores = [score for score in pain_scores if score is not None]
        rows[subject] = {
            "survey_age": clean_float(row.get("Age")),
            "survey_gender": clean_text(row.get("Gender (Biological)")),
            "survey_sleep_hours_avg": numeric_first(row.get("How many hours do you sleep per day on average?")),
            "survey_sleep_hours_before_test": numeric_first(row.get("How many hours did you sleep before this test?")),
            "survey_daily_stress_ordinal": ordinal_text_score(row.get("What do you think about your stress level in your daily life?")),
            "survey_chronic_pain_flag": yes_no_flag(row.get("Do you have any chronic pain conditions?")),
            "survey_regular_medication_flag": yes_no_flag(row.get("Are there any medications or supplements you currently use regularly?")),
            "survey_pain_context_score": float(np.nanmean(pain_scores)) if pain_scores else None,
            "survey_pain_type": clean_text(row.get("What is your pain type?")),
        }
    return rows


def add_subject_metrics(frame: pd.DataFrame, metrics: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if not metrics or "subject_id" not in frame:
        return frame
    out = frame.copy()
    for key in sorted({k for row in metrics.values() for k in row}):
        out[key] = [metrics.get(str(subject), {}).get(key) for subject in out["subject_id"]]
    return out
    try:
        text = str(value).strip().replace(",", ".")
        if not text or text.lower() in {"nan", "<na>"}:
            return None
        return float(text)
    except ValueError:
        return None


def useful_zip_infos(zip_path: Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(zip_path) as zf:
        infos = []
        for info in zf.infolist():
            name = Path(info.filename).name
            if info.is_dir() or name.startswith("._") or name == ".DS_Store" or info.filename.startswith("__MACOSX/"):
                continue
            infos.append(info)
        return infos


def archive_path(source_root: Path, name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() else source_root / name


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def add_common_labels(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "pain_intensity" not in out and "target_pain_nrs_0_10" in out:
        out["pain_intensity"] = out["target_pain_nrs_0_10"]
    out["label_family"] = [family_for_row(row) for _, row in out.iterrows()]
    out["target_pain_bin"] = out.get("target_pain_nrs_0_10", pd.Series(np.nan, index=out.index)).map(ordinal_pain_bin)
    return out


def source_member_row(archive: Path, info: zipfile.ZipInfo, nested_archive: str | None = None) -> dict[str, Any]:
    row = {
        "source_archive": archive.name,
        "source_member": info.filename,
        "compressed_bytes": info.compress_size,
        "uncompressed_bytes": info.file_size,
        "crc32": f"{info.CRC:08x}",
    }
    if nested_archive:
        row["nested_archive"] = nested_archive
    return row


def finalize_outputs(
    dataset_id: str,
    out_dir: Path,
    stream: ParquetSink,
    labels: list[dict[str, Any]],
    subjects: dict[str, dict[str, Any]],
    source_rows: list[dict[str, Any]],
    note: str,
) -> list[IngestOutput]:
    stream.close()
    labels_path = out_dir / "labels.parquet"
    subjects_path = out_dir / "subjects.parquet"
    manifest_path = out_dir / "manifest.json"
    labels_frame = pd.DataFrame(labels)
    subjects_frame = pd.DataFrame(sorted(subjects.values(), key=lambda row: str(row.get("subject_id"))))
    labels_frame.to_parquet(labels_path, compression="zstd", index=False)
    subjects_frame.to_parquet(subjects_path, compression="zstd", index=False)
    manifest = {
        "dataset_id": dataset_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows": stream.rows,
        "source_members": source_rows,
        "outputs": {
            "measurement_stream": str(stream.path),
            "labels": str(labels_path),
            "subjects": str(subjects_path),
        },
        "schema_note": note,
    }
    write_json(manifest_path, manifest)
    outputs = [
        IngestOutput(dataset_id, "measurement_stream", str(stream.path), stream.rows, stream.path.stat().st_size if stream.path.exists() else 0),
        IngestOutput(dataset_id, "labels", str(labels_path), len(labels_frame), labels_path.stat().st_size),
        IngestOutput(dataset_id, "subjects", str(subjects_path), len(subjects_frame), subjects_path.stat().st_size),
    ]
    return outputs


def read_csv_chunks(raw: Any, chunksize: int, **kwargs: Any) -> Iterable[pd.DataFrame]:
    yield from pd.read_csv(raw, chunksize=chunksize, **kwargs)


def normalize_painmonit(source_root: Path, output_root: Path, chunksize: int, max_sessions: int | None = None, **_: Any) -> list[IngestOutput]:
    archive = archive_path(source_root, "PainMonit Database.zip")
    out_dir = output_root / "painmonit" / "clinical"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []

    with zipfile.ZipFile(archive) as outer:
        nested_name = "PMCD.zip"
        nested_info = outer.getinfo(nested_name)
        with zipfile.ZipFile(outer.open(nested_info)) as inner:
            main_members = [
                info
                for info in inner.infolist()
                if not info.is_dir()
                and info.filename.lower().endswith(".csv")
                and not info.filename.lower().endswith("_runup.csv")
                and "/raw-data/" in info.filename.lower()
            ]
            runup_by_session = {
                info.filename.replace("_runUp.csv", ".csv").replace("_runup.csv", ".csv"): info
                for info in inner.infolist()
                if not info.is_dir() and info.filename.lower().endswith("_runup.csv")
            }
            for idx, info in enumerate(sorted(main_members, key=lambda item: item.filename)):
                if max_sessions is not None and idx >= max_sessions:
                    break
                parsed = parse_painmonit_session(info.filename)
                paired_infos = [("clinical_main", info), ("clinical_runup_baseline", runup_by_session.get(info.filename))]
                pain_min: float | None = None
                pain_max: float | None = None
                pain_count = 0
                for record_type, paired_info in paired_infos:
                    if paired_info is None:
                        continue
                    source_rows.append(source_member_row(archive, paired_info, nested_name))
                    cumulative = 0
                    with inner.open(paired_info) as raw:
                        reader = read_csv_chunks(raw, chunksize, sep=";", decimal=",", na_values=["NaN", "nan", ""])
                        for chunk in reader:
                            chunk.columns = [normalize_column(c) for c in chunk.columns]
                            rows = len(chunk)
                            sample_index = pd.Series(range(cumulative, cumulative + rows), index=chunk.index, dtype="int64")
                            cumulative += rows
                            if record_type == "clinical_main":
                                pain = clean_numeric(chunk.get("pain_rates", pd.Series(np.nan, index=chunk.index))).astype("float64")
                                valid_pain = pain.dropna()
                                if not valid_pain.empty:
                                    pain_min = float(valid_pain.min()) if pain_min is None else min(pain_min, float(valid_pain.min()))
                                    pain_max = float(valid_pain.max()) if pain_max is None else max(pain_max, float(valid_pain.max()))
                                    pain_count += int(valid_pain.shape[0])
                            else:
                                pain = pd.Series(np.nan, index=chunk.index, dtype="float64")
                            out = pd.DataFrame(
                                {
                                    "dataset_id": "painmonit",
                                    "source_archive": archive.name,
                                    "source_member": paired_info.filename,
                                    "subject_id": parsed["subject_id"],
                                    "session_id": parsed["session_id"] if record_type == "clinical_main" else f"{parsed['session_id']}_runup",
                                    "baseline_pair_session_id": parsed["session_id"],
                                    "condition": "clinical_physiotherapy" if record_type == "clinical_main" else "clinical_runup_baseline",
                                    "record_type": record_type,
                                    "pain_protocol_kind": "clinical",
                                    "device": "empatica_e4_respiratory_belt_emg_grip",
                                    "sample_rate_hz": 250.0,
                                    "sample_index": sample_index,
                                    "sample_offset_s": clean_numeric(chunk.get("seconds", sample_index / 250.0)).astype("float64"),
                                    "bvp": clean_numeric(chunk.get("bvp", pd.Series(np.nan, index=chunk.index))),
                                    "eda": clean_numeric(chunk.get("eda_e4", pd.Series(np.nan, index=chunk.index))),
                                    "temperature": clean_numeric(chunk.get("tmp", pd.Series(np.nan, index=chunk.index))),
                                    "respiration": clean_numeric(chunk.get("resp", pd.Series(np.nan, index=chunk.index))),
                                    "emg": clean_numeric(chunk.get("emg", pd.Series(np.nan, index=chunk.index))),
                                    "grip": clean_numeric(chunk.get("grip", pd.Series(np.nan, index=chunk.index))),
                                    "target_pain_nrs_0_10": pain,
                                    "pain_label": chunk.get("pain_labels", pd.Series(pd.NA, index=chunk.index)).astype("string"),
                                    "pain_scale_type": "nrs_0_10",
                                }
                            )
                            stream.write(add_common_labels(out))
                subjects[parsed["subject_id"]] = {"dataset_id": "painmonit", "subject_id": parsed["subject_id"]}
                labels.append(
                    {
                        "dataset_id": "painmonit",
                        "subject_id": parsed["subject_id"],
                        "session_id": parsed["session_id"],
                        "label_type": "pain_nrs_timeseries",
                        "pain_min": pain_min,
                        "pain_max": pain_max,
                        "pain_labeled_rows": pain_count,
                        "source_archive": archive.name,
                        "source_member": info.filename,
                    }
                )
    return finalize_outputs("painmonit", out_dir, stream, labels, subjects, source_rows, "PainMonit PMCD clinical direct-pain stream.")


def normalize_rheumapain(
    source_root: Path,
    output_root: Path,
    chunksize: int,
    frequency_hz: int = 64,
    max_sessions: int | None = None,
    **_: Any,
) -> list[IngestOutput]:
    archive = archive_path(source_root, "RheumaPain Dataset.zip")
    out_dir = output_root / "rheumapain" / f"frequency_hz={frequency_hz}"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    workbook = load_rheumapain_workbook(source_root)
    pattern = f"/Processed Data/{frequency_hz}Hz/"
    with zipfile.ZipFile(archive) as zf:
        members = [info for info in zf.infolist() if pattern in info.filename and info.filename.lower().endswith(".csv")]
        for idx, info in enumerate(sorted(members, key=lambda item: item.filename)):
            if max_sessions is not None and idx >= max_sessions:
                break
            source_rows.append(source_member_row(archive, info))
            cumulative = 0
            observed: set[float] = set()
            subject_id = Path(info.filename).stem.lower()
            condition_seen: str | None = None
            with zf.open(info) as raw:
                for chunk in read_csv_chunks(raw, chunksize):
                    chunk.columns = [normalize_column(c) for c in chunk.columns]
                    rows = len(chunk)
                    sample_index = pd.Series(range(cumulative, cumulative + rows), index=chunk.index, dtype="int64")
                    cumulative += rows
                    person = chunk.get("person_id", pd.Series(subject_id, index=chunk.index)).astype("string").str.lower()
                    condition = chunk.get("exercise_rest", pd.Series("unknown", index=chunk.index)).astype("string").str.lower()
                    condition_seen = clean_text(condition.iloc[0]) or condition_seen
                    pain = clean_numeric(chunk.get("pain_scale", pd.Series(np.nan, index=chunk.index))).astype("float64")
                    metrics = workbook.get(subject_id, {})
                    if condition_seen == "rest" and metrics.get("workbook_pain_rest") is not None:
                        pain = pd.Series(metrics["workbook_pain_rest"], index=chunk.index, dtype="float64")
                    elif condition_seen == "exercise" and metrics.get("workbook_pain_exercise") is not None:
                        pain = pd.Series(metrics["workbook_pain_exercise"], index=chunk.index, dtype="float64")
                    for value in pain.dropna().unique().tolist():
                        observed.add(float(value))
                    out = pd.DataFrame(
                        {
                            "dataset_id": "rheumapain",
                            "source_archive": archive.name,
                            "source_member": info.filename,
                            "subject_id": person,
                            "session_id": person + "_" + condition,
                            "condition": condition,
                            "device": "empatica_e4",
                            "sample_rate_hz": float(frequency_hz),
                            "sample_index": sample_index,
                            "sample_offset_s": sample_index.astype("float64") / float(frequency_hz),
                            "bvp": clean_numeric(chunk.get("bvp", pd.Series(np.nan, index=chunk.index))),
                            "eda": clean_numeric(chunk.get("eda", pd.Series(np.nan, index=chunk.index))),
                            "acc_x": clean_numeric(chunk.get("x", pd.Series(np.nan, index=chunk.index))),
                            "acc_y": clean_numeric(chunk.get("y", pd.Series(np.nan, index=chunk.index))),
                            "acc_z": clean_numeric(chunk.get("z", pd.Series(np.nan, index=chunk.index))),
                            "temperature": clean_numeric(chunk.get("temperature", pd.Series(np.nan, index=chunk.index))),
                            "target_pain_nrs_0_10": pain,
                            "pain_scale_type": "wong_baker_source",
                        }
                    )
                    for key, value in metrics.items():
                        out[key] = value
                    stream.write(add_common_labels(out))
            subjects[subject_id] = {"dataset_id": "rheumapain", "subject_id": subject_id, **workbook.get(subject_id, {})}
            labels.append(
                {
                    "dataset_id": "rheumapain",
                    "subject_id": subject_id,
                    "session_id": f"{subject_id}_{condition_seen or 'unknown'}",
                    "condition": condition_seen,
                    "label_type": "weak_session_pain",
                    "pain_values_observed": sorted(observed),
                    **workbook.get(subject_id, {}),
                    "source_archive": archive.name,
                    "source_member": info.filename,
                }
            )
    return finalize_outputs("rheumapain", out_dir, stream, labels, subjects, source_rows, "RheumaPain processed weak/session pain stream.")


def normalize_painmonit_pmed(source_root: Path, output_root: Path, chunksize: int, max_sessions: int | None = None, **_: Any) -> list[IngestOutput]:
    archive = archive_path(source_root, "PainMonit Database.zip")
    dataset_id = "painmonit_pmed"
    out_dir = output_root / dataset_id / "experimental_heat"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive) as outer:
        nested_name = "PMED.zip"
        with zipfile.ZipFile(outer.open(nested_name)) as inner:
            members = [info for info in inner.infolist() if not info.is_dir() and info.filename.endswith("-synchronised-data.csv")]
            for idx, info in enumerate(sorted(members, key=lambda item: item.filename)):
                if max_sessions is not None and idx >= max_sessions:
                    break
                match = re.search(r"S_(\d+)-synchronised-data\.csv$", info.filename)
                subject_id = f"s{match.group(1)}" if match else Path(info.filename).stem
                source_rows.append(source_member_row(archive, info, nested_name))
                pain_min = pain_max = None
                pain_count = 0
                cumulative = 0
                with inner.open(info) as raw:
                    for chunk in read_csv_chunks(raw, chunksize, sep=";", decimal=",", na_values=["NaN", "nan", ""]):
                        chunk.columns = [normalize_column(c) for c in chunk.columns]
                        rows = len(chunk)
                        sample_index = pd.Series(range(cumulative, cumulative + rows), index=chunk.index, dtype="int64")
                        cumulative += rows
                        pain = clean_numeric(chunk.get("covas", pd.Series(np.nan, index=chunk.index))).astype("float64")
                        valid = pain.dropna()
                        if not valid.empty:
                            pain_min = float(valid.min()) if pain_min is None else min(pain_min, float(valid.min()))
                            pain_max = float(valid.max()) if pain_max is None else max(pain_max, float(valid.max()))
                            pain_count += int(valid.shape[0])
                        out = pd.DataFrame(
                            {
                                "dataset_id": dataset_id,
                                "source_archive": archive.name,
                                "source_member": info.filename,
                                "subject_id": subject_id,
                                "session_id": f"{subject_id}_heat",
                                "condition": "experimental_heat_pain",
                                "record_type": "heat_main",
                                "pain_protocol_kind": "experimental_heat",
                                "device": "empatica_e4_respiratory_belt_ecg_emg_heater",
                                "sample_rate_hz": 250.0,
                                "sample_index": sample_index,
                                "sample_offset_s": clean_numeric(chunk.get("seconds", sample_index / 250.0)).astype("float64"),
                                "bvp": clean_numeric(chunk.get("bvp", pd.Series(np.nan, index=chunk.index))),
                                "eda": clean_numeric(chunk.get("eda_e4", pd.Series(np.nan, index=chunk.index))),
                                "temperature": clean_numeric(chunk.get("tmp", pd.Series(np.nan, index=chunk.index))),
                                "ibi": clean_numeric(chunk.get("ibi", pd.Series(np.nan, index=chunk.index))),
                                "hr": clean_numeric(chunk.get("hr", pd.Series(np.nan, index=chunk.index))),
                                "respiration": clean_numeric(chunk.get("resp", pd.Series(np.nan, index=chunk.index))),
                                "ecg": clean_numeric(chunk.get("ecg", pd.Series(np.nan, index=chunk.index))),
                                "emg": clean_numeric(chunk.get("emg", pd.Series(np.nan, index=chunk.index))),
                                "heater_c": clean_numeric(chunk.get("heater_c", pd.Series(np.nan, index=chunk.index))),
                                "target_pain_nrs_0_10": pain,
                                "pain_scale_type": "covas_0_10",
                            }
                        )
                        stream.write(add_common_labels(out))
                subjects[subject_id] = {"dataset_id": dataset_id, "subject_id": subject_id}
                labels.append(
                    {
                        "dataset_id": dataset_id,
                        "subject_id": subject_id,
                        "session_id": f"{subject_id}_heat",
                        "label_type": "experimental_heat_covas_timeseries",
                        "pain_min": pain_min,
                        "pain_max": pain_max,
                        "pain_labeled_rows": pain_count,
                        "source_archive": archive.name,
                        "source_member": info.filename,
                    }
                )
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, "PainMonit PMED induced heat direct-pain stream.")


def normalize_watch_pain_archive(
    source_root: Path,
    output_root: Path,
    archive_name: str,
    dataset_id: str,
    chunksize: int,
    max_chunks: int | None = None,
) -> list[IngestOutput]:
    archive = archive_path(source_root, archive_name)
    out_dir = output_root / dataset_id / "watch_64hz"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    label_rows: dict[tuple[str, str, float], int] = {}
    survey_metrics = load_physio_survey_metrics(source_root, archive_name)
    with zipfile.ZipFile(archive) as zf:
        member = next(
            info
            for info in zf.infolist()
            if info.filename.endswith("PROCESSED WATCH DATA/combined/combined_all_data/all_watch_data_64hz.csv")
        )
        source_rows.append(source_member_row(archive, member))
        with zf.open(member) as raw:
            for chunk_idx, chunk in enumerate(read_csv_chunks(raw, chunksize)):
                if max_chunks is not None and chunk_idx >= max_chunks:
                    break
                chunk.columns = [normalize_column(c) for c in chunk.columns]
                subject = chunk.get("person_id", pd.Series("unknown", index=chunk.index)).astype("string")
                pain_type = chunk.get("pain_type", pd.Series("unknown", index=chunk.index)).astype("string")
                pain = clean_numeric(chunk.get("pain_scale", pd.Series(np.nan, index=chunk.index))).astype("float64")
                session = subject + "_" + pain_type + "_scale_" + pain.astype("string").fillna("unknown")
                sample_index = []
                for sid in session.tolist():
                    start = counters.get(sid, 0)
                    sample_index.append(start)
                    counters[sid] = start + 1
                sample_index_s = pd.Series(sample_index, index=chunk.index, dtype="int64")
                out = pd.DataFrame(
                    {
                        "dataset_id": dataset_id,
                        "source_archive": archive.name,
                        "source_member": member.filename,
                        "subject_id": subject,
                        "session_id": session,
                        "condition": pain_type,
                        "device": "processed_watch",
                        "sample_rate_hz": 64.0,
                        "sample_index": sample_index_s,
                        "sample_offset_s": sample_index_s.astype("float64") / 64.0,
                        "bvp": clean_numeric(chunk.get("bvp", pd.Series(np.nan, index=chunk.index))),
                        "eda": clean_numeric(chunk.get("eda", pd.Series(np.nan, index=chunk.index))),
                        "acc_x": clean_numeric(chunk.get("x", pd.Series(np.nan, index=chunk.index))),
                        "acc_y": clean_numeric(chunk.get("y", pd.Series(np.nan, index=chunk.index))),
                        "acc_z": clean_numeric(chunk.get("z", pd.Series(np.nan, index=chunk.index))),
                        "temperature": clean_numeric(chunk.get("temperature", pd.Series(np.nan, index=chunk.index))),
                        "target_pain_nrs_0_10": pain,
                        "pain_type": pain_type,
                        "pain_scale_type": "source_1_5",
                    }
                )
                out = add_subject_metrics(out, survey_metrics)
                for sid in subject.dropna().unique().tolist():
                    subjects[str(sid)] = {"dataset_id": dataset_id, "subject_id": str(sid), **survey_metrics.get(str(sid), {})}
                for key, count in out.groupby(["subject_id", "pain_type", "target_pain_nrs_0_10"], dropna=False).size().items():
                    label_rows[(str(key[0]), str(key[1]), float(key[2]) if not pd.isna(key[2]) else np.nan)] = label_rows.get((str(key[0]), str(key[1]), float(key[2]) if not pd.isna(key[2]) else np.nan), 0) + int(count)
                stream.write(add_common_labels(out))
    for (subject_id, pain_type, pain_scale), rows in sorted(label_rows.items(), key=lambda item: str(item[0])):
        labels.append(
            {
                "dataset_id": dataset_id,
                "subject_id": subject_id,
                "pain_type": pain_type,
                "pain_scale": pain_scale,
                "rows": rows,
                "label_type": "watch_processed_pain_type_scale",
                "source_archive": archive.name,
            }
        )
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, f"{archive.name} processed watch direct-pain stream.")


def normalize_silver(
    source_root: Path,
    output_root: Path,
    chunksize: int,
    max_chunks_per_cohort: int | None = None,
    max_chunks: int | None = None,
    **_: Any,
) -> list[IngestOutput]:
    if max_chunks_per_cohort is None:
        max_chunks_per_cohort = max_chunks
    archive = archive_path(source_root, "SILVER-Pain Dataset.zip")
    dataset_id = "silver_pain"
    out_dir = output_root / dataset_id / "merged"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    label_rows: dict[tuple[str, str, float], int] = {}
    start_ns_by_session: dict[str, float] = {}
    with zipfile.ZipFile(archive) as zf:
        for cohort, suffix in [("older_adults", "older_adults.csv"), ("young_adults", "young_adults.csv")]:
            member = next(info for info in zf.infolist() if info.filename.endswith(f"/{suffix}"))
            source_rows.append(source_member_row(archive, member))
            with zf.open(member) as raw:
                for chunk_idx, chunk in enumerate(read_csv_chunks(raw, chunksize)):
                    if max_chunks_per_cohort is not None and chunk_idx >= max_chunks_per_cohort:
                        break
                    chunk.columns = [normalize_column(c) for c in chunk.columns]
                    subject = chunk.get("subject", pd.Series("unknown", index=chunk.index)).astype("string")
                    if cohort == "older_adults":
                        subject = subject.str.replace(r"\.0$", "", regex=True).str.zfill(3)
                    trial = chunk.get("trial", pd.Series(pd.NA, index=chunk.index)).astype("string").fillna("unknown")
                    segment = chunk.get("segment", pd.Series(pd.NA, index=chunk.index)).astype("string").fillna("unknown")
                    session = cohort + "_" + subject + "_trial_" + trial
                    timestamp_ns = clean_numeric(chunk.get("timestamp_ns", pd.Series(np.nan, index=chunk.index))).astype("float64")
                    offsets = []
                    for sid, ts in zip(session.tolist(), timestamp_ns.tolist(), strict=False):
                        if pd.isna(ts):
                            offsets.append(np.nan)
                            continue
                        start = start_ns_by_session.setdefault(str(sid), float(ts))
                        offsets.append((float(ts) - start) / 1_000_000_000.0)
                    pain = clean_numeric(chunk.get("painlevel", pd.Series(np.nan, index=chunk.index))).astype("float64")
                    out = pd.DataFrame(
                        {
                            "dataset_id": dataset_id,
                            "source_archive": archive.name,
                            "source_member": member.filename,
                            "subject_id": cohort + "_" + subject,
                            "session_id": session,
                            "condition": segment,
                            "cohort": cohort,
                            "device": "empatica_like_merged",
                            "sample_rate_hz": np.nan,
                            "sample_index": pd.Series(range(len(chunk)), index=chunk.index, dtype="int64"),
                            "sample_offset_s": pd.Series(offsets, index=chunk.index, dtype="float64"),
                            "bvp": clean_numeric(chunk.get("bvp", pd.Series(np.nan, index=chunk.index))),
                            "eda": clean_numeric(chunk.get("eda", pd.Series(np.nan, index=chunk.index))),
                            "temperature": clean_numeric(chunk.get("temperature", pd.Series(np.nan, index=chunk.index))),
                            "hr": clean_numeric(chunk.get("hr", pd.Series(np.nan, index=chunk.index))),
                            "target_pain_nrs_0_10": pain,
                            "pain_scale_type": "silver_source",
                        }
                    )
                    for sid in out["subject_id"].dropna().unique().tolist():
                        subjects[str(sid)] = {"dataset_id": dataset_id, "subject_id": str(sid), "cohort": cohort}
                    for key, count in out.groupby(["subject_id", "condition", "target_pain_nrs_0_10"], dropna=False).size().items():
                        label_rows[(str(key[0]), str(key[1]), float(key[2]) if not pd.isna(key[2]) else np.nan)] = label_rows.get((str(key[0]), str(key[1]), float(key[2]) if not pd.isna(key[2]) else np.nan), 0) + int(count)
                    stream.write(add_common_labels(out))
    for (subject_id, condition, pain), rows in sorted(label_rows.items(), key=lambda item: str(item[0])):
        labels.append({"dataset_id": dataset_id, "subject_id": subject_id, "condition": condition, "pain_scale": pain, "rows": rows, "label_type": "silver_painlevel"})
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, "SILVER-Pain merged direct-pain stream.")


def read_e4_csv(zf: zipfile.ZipFile, member: str, sensor: str) -> pd.DataFrame:
    data = zf.read(member).decode("utf-8-sig", errors="replace").strip().splitlines()
    if sensor == "ibi":
        if len(data) < 2:
            return pd.DataFrame()
        body = "\n".join(data[1:])
        frame = pd.read_csv(io.StringIO(body), header=None, names=["sample_offset_s", "ibi"])
        frame["sample_offset_s"] = pd.to_numeric(frame["sample_offset_s"], errors="coerce")
        frame["ibi"] = pd.to_numeric(frame["ibi"], errors="coerce")
        frame = frame.dropna(subset=["sample_offset_s", "ibi"]).reset_index(drop=True)
        frame["sample_index"] = np.arange(len(frame), dtype=np.int64)
        frame["sample_rate_hz"] = np.nan
        return frame
    if len(data) < 3:
        return pd.DataFrame()
    rate = clean_float(str(data[1]).split(",")[0]) or 1.0
    body = "\n".join(data[2:])
    if sensor == "acc":
        frame = pd.read_csv(io.StringIO(body), header=None, names=["acc_x", "acc_y", "acc_z"])
    else:
        name = {"temp": "temperature"}.get(sensor, sensor)
        frame = pd.read_csv(io.StringIO(body), header=None, names=[name])
    frame["sample_index"] = np.arange(len(frame), dtype=np.int64)
    frame["sample_offset_s"] = frame["sample_index"].astype("float64") / float(rate)
    frame["sample_rate_hz"] = float(rate)
    return frame


def combine_e4_session(zf: zipfile.ZipFile, members: dict[str, str]) -> pd.DataFrame:
    frames = {sensor: read_e4_csv(zf, member, sensor) for sensor, member in members.items()}
    frames = {sensor: frame for sensor, frame in frames.items() if not frame.empty}
    if not frames:
        return pd.DataFrame()
    base_sensor = max(frames, key=lambda sensor: len(frames[sensor]))
    out = frames[base_sensor].drop(columns=["sample_rate_hz"]).sort_values("sample_offset_s")
    for sensor, frame in frames.items():
        if sensor == base_sensor:
            continue
        value_cols = [col for col in frame.columns if col not in {"sample_index", "sample_offset_s", "sample_rate_hz"}]
        if sensor == "ibi":
            tolerance = 0.015
        else:
            tolerance = max(0.02, 0.5 / float(frame["sample_rate_hz"].dropna().iloc[0]))
        out = pd.merge_asof(
            out.sort_values("sample_offset_s"),
            frame[["sample_offset_s", *value_cols]].sort_values("sample_offset_s"),
            on="sample_offset_s",
            direction="nearest",
            tolerance=tolerance,
        )
    out["sample_index"] = np.arange(len(out), dtype=np.int64)
    return out


def load_induced_stress_scores(source_root: Path) -> dict[str, dict[str, float]]:
    archive = archive_path(source_root, "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip")
    scores: dict[str, dict[str, float]] = {}
    with zipfile.ZipFile(archive) as zf:
        for member in [
            "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1/Stress_Level_v1.csv",
            "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1/Stress_Level_v2.csv",
        ]:
            if member not in zf.namelist():
                continue
            with zf.open(member) as raw:
                frame = pd.read_csv(raw, index_col=0)
            for subject, row in frame.iterrows():
                vals = pd.to_numeric(row, errors="coerce").dropna()
                if vals.empty:
                    continue
                bucket = scores.setdefault(str(subject).lower(), {})
                bucket["target_stress_score_mean_0_10"] = float(vals.mean())
                bucket["target_stress_score_0_10"] = float(vals.max())
    return scores


def parse_wesad_protocol(quest_text: str) -> list[dict[str, Any]]:
    lines = [line.rstrip(";") for line in quest_text.splitlines()]
    order = start = end = None
    for line in lines:
        parts = [part.strip() for part in line.split(";")]
        if parts and parts[0] == "# ORDER":
            order = parts[1:]
        elif parts and parts[0] == "# START":
            start = [clean_float(part) for part in parts[1:]]
        elif parts and parts[0] == "# END":
            end = [clean_float(part) for part in parts[1:]]
    segments: list[dict[str, Any]] = []
    if not order or not start or not end:
        return segments
    valid_starts = [value for value in start if value is not None]
    origin_min = min(valid_starts) if valid_starts else 0.0
    for name, start_min, end_min in zip(order, start, end, strict=False):
        if not name or start_min is None or end_min is None:
            continue
        normalized = name.lower().replace(" ", "_")
        is_stress = normalized == "tsst"
        segments.append(
            {
                "wesad_protocol_segment": normalized,
                "wesad_protocol_start_s": (start_min - origin_min) * 60.0,
                "wesad_protocol_end_s": (end_min - origin_min) * 60.0,
                "target_stress_binary": 1.0 if is_stress else 0.0,
                "target_stress_score_0_10": 8.0 if is_stress else 2.0,
                "aux_state_label": "tsst_stress" if is_stress else normalized,
            }
        )
    return segments


def apply_wesad_protocol(frame: pd.DataFrame, segments: list[dict[str, Any]]) -> pd.DataFrame:
    out = frame.copy()
    out["wesad_protocol_segment"] = "unknown"
    out["wesad_protocol_start_s"] = np.nan
    out["wesad_protocol_end_s"] = np.nan
    out["target_stress_binary"] = np.nan
    out["target_stress_score_0_10"] = np.nan
    out["aux_state_label"] = pd.NA
    times = pd.to_numeric(out["sample_offset_s"], errors="coerce")
    for segment in segments:
        mask = times.ge(segment["wesad_protocol_start_s"]) & times.le(segment["wesad_protocol_end_s"])
        for key, value in segment.items():
            out.loc[mask, key] = value
    return out


def normalize_catsa(source_root: Path, output_root: Path, max_sessions: int | None = None) -> list[IngestOutput]:
    archive = archive_path(source_root, "CATSA.zip")
    dataset_id = "catsa"
    out_dir = output_root / dataset_id / "e4_tasks"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    session_re = re.compile(r"CATSA/(?P<subject>Sub\d+)/(?P<condition>[^/]+)/(?P<sensor>ACC|BVP|EDA|HR|TEMP)\.csv$")
    with zipfile.ZipFile(archive) as zf:
        groups: dict[tuple[str, str], dict[str, str]] = {}
        infos = {info.filename: info for info in zf.infolist()}
        for name in infos:
            match = session_re.match(name)
            if match:
                sensor = match.group("sensor").lower()
                sensor = "temp" if sensor == "temp" else sensor
                groups.setdefault((match.group("subject").lower(), match.group("condition")), {})[sensor] = name
        for idx, ((subject_id, condition), members) in enumerate(sorted(groups.items())):
            if max_sessions is not None and idx >= max_sessions:
                break
            for member in members.values():
                source_rows.append(source_member_row(archive, infos[member]))
            session = combine_e4_session(zf, members)
            if session.empty:
                continue
            session["dataset_id"] = dataset_id
            session["source_archive"] = archive.name
            session["source_member"] = ";".join(sorted(members.values()))
            session["subject_id"] = subject_id
            session["session_id"] = f"{subject_id}_{condition.lower()}"
            session["condition"] = condition.lower()
            session["device"] = "empatica_e4"
            session["target_pain_nrs_0_10"] = np.nan
            stream.write(add_common_labels(session))
            subjects[subject_id] = {"dataset_id": dataset_id, "subject_id": subject_id}
            labels.append({"dataset_id": dataset_id, "subject_id": subject_id, "session_id": f"{subject_id}_{condition.lower()}", "condition": condition.lower(), "label_type": "context_only"})
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, "CATSA E4 task context stream; no pain truth.")


def normalize_wearable_sports(source_root: Path, output_root: Path, chunksize: int, **_: Any) -> list[IngestOutput]:
    archive = archive_path(source_root, "Wearable Sports Health Monitoring Dataset.zip")
    dataset_id = "wearable_sports_health"
    out_dir = output_root / dataset_id / "csv"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive) as zf:
        member = next(info for info in zf.infolist() if info.filename.endswith(".csv"))
        source_rows.append(source_member_row(archive, member))
        with zf.open(member) as raw:
            for chunk in read_csv_chunks(raw, chunksize):
                chunk.columns = [normalize_column(c) for c in chunk.columns]
                athlete = chunk.get("athlete_id", pd.Series("unknown", index=chunk.index)).astype("string")
                status = chunk.get("activity_status", pd.Series("unknown", index=chunk.index)).astype("string").str.lower()
                bp = chunk.get("blood_pressure", pd.Series("", index=chunk.index)).astype("string").str.split("/", expand=True)
                systolic = clean_numeric(bp[0]) if 0 in bp else pd.Series(np.nan, index=chunk.index)
                diastolic = clean_numeric(bp[1]) if 1 in bp else pd.Series(np.nan, index=chunk.index)
                out = pd.DataFrame(
                    {
                        "dataset_id": dataset_id,
                        "source_archive": archive.name,
                        "source_member": member.filename,
                        "subject_id": athlete,
                        "session_id": athlete + "_sports_synthetic_like",
                        "condition": status,
                        "device": "sports_health_csv",
                        "sample_rate_hz": np.nan,
                        "sample_index": clean_numeric(chunk.get("record_id", pd.Series(range(len(chunk)), index=chunk.index))),
                        "sample_offset_s": pd.Series(range(len(chunk)), index=chunk.index, dtype="float64") * 300.0,
                        "hr": clean_numeric(chunk.get("heart_rate", pd.Series(np.nan, index=chunk.index))),
                        "temperature": clean_numeric(chunk.get("body_temperature", pd.Series(np.nan, index=chunk.index))),
                        "spo2": clean_numeric(chunk.get("blood_oxygen", pd.Series(np.nan, index=chunk.index))),
                        "steps": clean_numeric(chunk.get("step_count", pd.Series(np.nan, index=chunk.index))),
                        "systolic_bp": systolic,
                        "diastolic_bp": diastolic,
                        "target_pain_nrs_0_10": np.nan,
                    }
                )
                for sid in athlete.dropna().unique().tolist():
                    subjects[str(sid)] = {"dataset_id": dataset_id, "subject_id": str(sid)}
                stream.write(add_common_labels(out))
    labels.append({"dataset_id": dataset_id, "label_type": "activity_context_only", "pain_truth": False})
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, "Sports activity context stream; no pain truth.")


def normalize_induced_stress_exercise(source_root: Path, output_root: Path, max_sessions: int | None = None) -> list[IngestOutput]:
    archive = archive_path(source_root, "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip")
    dataset_id = "induced_stress_exercise"
    out_dir = output_root / dataset_id / "e4_activity"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    stress_scores = load_induced_stress_scores(source_root)
    session_re = re.compile(r".*/Wearable_Dataset/(?P<activity>[^/]+)/(?P<subject>S\d+)/(?P<sensor>ACC|BVP|EDA|HR|IBI|TEMP)\.csv$")
    with zipfile.ZipFile(archive) as zf:
        groups: dict[tuple[str, str], dict[str, str]] = {}
        infos = {info.filename: info for info in zf.infolist()}
        for name in infos:
            match = session_re.match(name)
            if match:
                sensor = match.group("sensor").lower()
                sensor = "temp" if sensor == "temp" else sensor
                groups.setdefault((match.group("subject").lower(), match.group("activity").lower()), {})[sensor] = name
        for idx, ((subject_id, activity), members) in enumerate(sorted(groups.items())):
            if max_sessions is not None and idx >= max_sessions:
                break
            for member in members.values():
                source_rows.append(source_member_row(archive, infos[member]))
            session = combine_e4_session(zf, members)
            if session.empty:
                continue
            session["dataset_id"] = dataset_id
            session["source_archive"] = archive.name
            session["source_member"] = ";".join(sorted(members.values()))
            session["subject_id"] = subject_id
            session["session_id"] = f"{subject_id}_{activity}"
            session["condition"] = activity
            session["aux_state_label"] = activity
            if activity == "stress":
                session["target_stress_binary"] = 1.0
                for key, value in stress_scores.get(subject_id, {}).items():
                    session[key] = value
            session["device"] = "empatica_e4"
            session["target_pain_nrs_0_10"] = np.nan
            stream.write(add_common_labels(session))
            subjects[subject_id] = {"dataset_id": dataset_id, "subject_id": subject_id}
            labels.append({"dataset_id": dataset_id, "subject_id": subject_id, "session_id": f"{subject_id}_{activity}", "condition": activity, "label_type": "exercise_or_stress_context"})
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, "Induced stress/exercise E4 context stream; no pain truth.")


def normalize_wesad(source_root: Path, output_root: Path, max_sessions: int | None = None, **_: Any) -> list[IngestOutput]:
    archive = archive_path(source_root, "WESAD.zip")
    dataset_id = "wesad"
    out_dir = output_root / dataset_id / "e4_full"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive) as outer:
        nested_members = [
            info
            for info in outer.infolist()
            if re.match(r"WESAD/S\d+/S\d+_E4_Data\.zip$", info.filename)
        ]
        for idx, info in enumerate(sorted(nested_members, key=lambda item: item.filename)):
            if max_sessions is not None and idx >= max_sessions:
                break
            subject_id = Path(info.filename).parent.name.lower()
            source_rows.append(source_member_row(archive, info))
            with zipfile.ZipFile(outer.open(info)) as inner:
                names = set(inner.namelist())
                members = {
                    sensor: member
                    for sensor, member in {
                        "acc": "ACC.csv",
                        "bvp": "BVP.csv",
                        "eda": "EDA.csv",
                        "hr": "HR.csv",
                        "ibi": "IBI.csv",
                        "temp": "TEMP.csv",
                    }.items()
                    if member in names
                }
                session = combine_e4_session(inner, members)
            if session.empty:
                continue
            session["dataset_id"] = dataset_id
            session["source_archive"] = archive.name
            session["source_member"] = info.filename
            session["subject_id"] = subject_id
            session["session_id"] = f"{subject_id}_e4_full"
            session["condition"] = "wesad_full_protocol"
            session["device"] = "empatica_e4"
            session["target_pain_nrs_0_10"] = np.nan
            quest_member = f"WESAD/{subject_id.upper()}/{subject_id.upper()}_quest.csv"
            if quest_member in outer.namelist():
                segments = parse_wesad_protocol(outer.read(quest_member).decode("utf-8-sig", errors="replace"))
                session = apply_wesad_protocol(session, segments)
            stream.write(add_common_labels(session))
            subjects[subject_id] = {"dataset_id": dataset_id, "subject_id": subject_id}
            labels.append({"dataset_id": dataset_id, "subject_id": subject_id, "session_id": f"{subject_id}_e4_full", "condition": "wesad_full_protocol", "label_type": "stress_protocol_context"})
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, "WESAD E4 full-protocol stress context stream; no pain truth.")


def normalize_wesad_respiban(source_root: Path, output_root: Path, chunksize: int, max_sessions: int | None = None, **_: Any) -> list[IngestOutput]:
    archive = archive_path(source_root, "WESAD.zip")
    dataset_id = "wesad_respiban"
    out_dir = output_root / dataset_id / "chest_respiban"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive) as outer:
        members = [info for info in outer.infolist() if re.match(r"WESAD/S\d+/S\d+_respiban\.txt$", info.filename)]
        for idx, info in enumerate(sorted(members, key=lambda item: item.filename)):
            if max_sessions is not None and idx >= max_sessions:
                break
            subject_id = Path(info.filename).parent.name.lower()
            source_rows.append(source_member_row(archive, info))
            quest_member = f"WESAD/{subject_id.upper()}/{subject_id.upper()}_quest.csv"
            segments = parse_wesad_protocol(outer.read(quest_member).decode("utf-8-sig", errors="replace")) if quest_member in outer.namelist() else []
            with outer.open(info) as raw:
                reader = pd.read_csv(
                    raw,
                    sep="\t",
                    skiprows=3,
                    header=None,
                    names=["nseq", "digital", "ecg", "eda", "emg", "temperature", "acc_x", "acc_y", "acc_z", "respiration", "empty"],
                    chunksize=chunksize,
                )
                cumulative = 0
                for chunk in reader:
                    chunk = chunk.iloc[::11].copy()
                    rows = len(chunk)
                    raw_index = clean_numeric(chunk["nseq"]).fillna(pd.Series(range(cumulative, cumulative + rows), index=chunk.index))
                    sample_index = raw_index.astype("int64")
                    cumulative += rows * 11
                    out = pd.DataFrame(
                        {
                            "dataset_id": dataset_id,
                            "source_archive": archive.name,
                            "source_member": info.filename,
                            "subject_id": subject_id,
                            "session_id": f"{subject_id}_respiban_full",
                            "condition": "wesad_full_protocol",
                            "device": "respiban_chest",
                            "source_sample_rate_hz": 700.0,
                            "sample_rate_hz": 700.0 / 11.0,
                            "sample_index": sample_index,
                            "sample_offset_s": sample_index.astype("float64") / 700.0,
                            "ecg": clean_numeric(chunk["ecg"]),
                            "eda": clean_numeric(chunk["eda"]),
                            "emg": clean_numeric(chunk["emg"]),
                            "temperature": clean_numeric(chunk["temperature"]),
                            "acc_x": clean_numeric(chunk["acc_x"]),
                            "acc_y": clean_numeric(chunk["acc_y"]),
                            "acc_z": clean_numeric(chunk["acc_z"]),
                            "respiration": clean_numeric(chunk["respiration"]),
                            "target_pain_nrs_0_10": np.nan,
                        }
                    )
                    out = apply_wesad_protocol(out, segments)
                    stream.write(add_common_labels(out))
            subjects[subject_id] = {"dataset_id": dataset_id, "subject_id": subject_id}
            labels.append({"dataset_id": dataset_id, "subject_id": subject_id, "session_id": f"{subject_id}_respiban_full", "condition": "wesad_full_protocol", "label_type": "stress_protocol_chest_context"})
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, "WESAD Respiban chest stress context stream; no pain truth.")


def normalize_physiopain_eeg(
    source_root: Path,
    output_root: Path,
    chunksize: int,
    archive_name: str = "PhysioPain Dataset.zip",
    dataset_id: str = "physiopain_eeg",
    max_sessions: int | None = None,
    **_: Any,
) -> list[IngestOutput]:
    archive = archive_path(source_root, archive_name)
    out_dir = output_root / dataset_id / "processed_1hz"
    stream = ParquetSink(out_dir / "measurement_stream.parquet")
    labels: list[dict[str, Any]] = []
    subjects: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    survey_metrics = load_physio_survey_metrics(source_root, archive_name)
    member_re = re.compile(r".*/PROCESSED EEG DATA/1Hz/(?P<pain_type>[^/]+)_1hz/(?P<subject>S\d+)\.csv$")
    with zipfile.ZipFile(archive) as zf:
        members = [info for info in zf.infolist() if member_re.match(info.filename)]
        for idx, info in enumerate(sorted(members, key=lambda item: item.filename)):
            if max_sessions is not None and idx >= max_sessions:
                break
            match = member_re.match(info.filename)
            if not match:
                continue
            pain_type = match.group("pain_type")
            subject_id = match.group("subject")
            source_rows.append(source_member_row(archive, info))
            cumulative = 0
            with zf.open(info) as raw:
                for chunk in read_csv_chunks(raw, chunksize):
                    chunk.columns = [normalize_column(c) for c in chunk.columns]
                    rows = len(chunk)
                    sample_index = pd.Series(range(cumulative, cumulative + rows), index=chunk.index, dtype="int64")
                    cumulative += rows
                    pain = clean_numeric(chunk.get("pain_intensity", pd.Series(np.nan, index=chunk.index))).astype("float64")
                    out = pd.DataFrame(
                        {
                            "dataset_id": dataset_id,
                            "source_archive": archive.name,
                            "source_member": info.filename,
                            "subject_id": chunk.get("person_id", pd.Series(subject_id, index=chunk.index)).astype("string"),
                            "session_id": f"{subject_id}_{pain_type}_eeg",
                            "condition": pain_type,
                            "device": "mindwave_eeg_processed",
                            "sample_rate_hz": 1.0,
                            "sample_index": sample_index,
                            "sample_offset_s": sample_index.astype("float64"),
                            "eeg_delta": clean_numeric(chunk.get("delta", pd.Series(np.nan, index=chunk.index))),
                            "eeg_theta": clean_numeric(chunk.get("theta", pd.Series(np.nan, index=chunk.index))),
                            "eeg_alpha1": clean_numeric(chunk.get("alpha1", pd.Series(np.nan, index=chunk.index))),
                            "eeg_alpha2": clean_numeric(chunk.get("alpha2", pd.Series(np.nan, index=chunk.index))),
                            "eeg_beta1": clean_numeric(chunk.get("beta1", pd.Series(np.nan, index=chunk.index))),
                            "eeg_beta2": clean_numeric(chunk.get("beta2", pd.Series(np.nan, index=chunk.index))),
                            "eeg_gamma1": clean_numeric(chunk.get("gamma1", pd.Series(np.nan, index=chunk.index))),
                            "eeg_gamma2": clean_numeric(chunk.get("gamma2", pd.Series(np.nan, index=chunk.index))),
                            "eeg_attention": clean_numeric(chunk.get("attention", pd.Series(np.nan, index=chunk.index))),
                            "eeg_meditation": clean_numeric(chunk.get("meditation", pd.Series(np.nan, index=chunk.index))),
                            "target_pain_nrs_0_10": pain,
                            "pain_type": chunk.get("pain_version", pd.Series(pain_type, index=chunk.index)).astype("string"),
                            "pain_scale_type": "source_1_5",
                        }
                    )
                    out = add_subject_metrics(out, survey_metrics)
                    stream.write(add_common_labels(out))
            subjects[subject_id] = {"dataset_id": dataset_id, "subject_id": subject_id, **survey_metrics.get(subject_id, {})}
            labels.append({"dataset_id": dataset_id, "subject_id": subject_id, "session_id": f"{subject_id}_{pain_type}_eeg", "condition": pain_type, "label_type": "eeg_pain_context"})
    return finalize_outputs(dataset_id, out_dir, stream, labels, subjects, source_rows, "PhysioPain processed EEG context branch; keep separate from watch pain head.")


NORMALIZERS: dict[str, Callable[..., list[IngestOutput]]] = {
    "painmonit": normalize_painmonit,
    "painmonit_pmed": normalize_painmonit_pmed,
    "rheumapain": normalize_rheumapain,
    "physiopain_watch": lambda source_root, output_root, chunksize, **kw: normalize_watch_pain_archive(source_root, output_root, "PhysioPain Dataset.zip", "physiopain_watch", chunksize, kw.get("max_chunks")),
    "multimodal_pain_watch": lambda source_root, output_root, chunksize, **kw: normalize_watch_pain_archive(source_root, output_root, "Multimodal Pain Dataset.zip", "multimodal_pain_watch", chunksize, kw.get("max_chunks")),
    "silver_pain": normalize_silver,
    "catsa": lambda source_root, output_root, chunksize, **kw: normalize_catsa(source_root, output_root, kw.get("max_sessions")),
    "wearable_sports_health": normalize_wearable_sports,
    "induced_stress_exercise": lambda source_root, output_root, chunksize, **kw: normalize_induced_stress_exercise(source_root, output_root, kw.get("max_sessions")),
    "wesad": lambda source_root, output_root, chunksize, **kw: normalize_wesad(source_root, output_root, kw.get("max_sessions")),
    "wesad_respiban": normalize_wesad_respiban,
    "physiopain_eeg": normalize_physiopain_eeg,
    "multimodal_pain_eeg": lambda source_root, output_root, chunksize, **kw: normalize_physiopain_eeg(
        source_root,
        output_root,
        chunksize,
        archive_name="Multimodal Pain Dataset.zip",
        dataset_id="multimodal_pain_eeg",
        max_sessions=kw.get("max_sessions"),
    ),
}


def inventory_sources(source_root: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for archive in sorted(source_root.glob("*.zip")):
        infos = useful_zip_infos(archive)
        payload[archive.name] = {
            "compressed_bytes": archive.stat().st_size,
            "members": len(infos),
            "uncompressed_bytes": sum(info.file_size for info in infos),
            "extensions": {},
        }
        for info in infos:
            suffix = Path(info.filename).suffix.lower() or "<none>"
            payload[archive.name]["extensions"][suffix] = payload[archive.name]["extensions"].get(suffix, 0) + 1
    return payload


def ingest_datasets(
    dataset_ids: list[str],
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    chunksize: int = 100_000,
    max_sessions: int | None = None,
    max_chunks: int | None = None,
) -> list[IngestOutput]:
    outputs: list[IngestOutput] = []
    for dataset_id in dataset_ids:
        normalizer = NORMALIZERS[dataset_id]
        outputs.extend(normalizer(source_root, output_root, chunksize, max_sessions=max_sessions, max_chunks=max_chunks))
    index = pd.DataFrame([asdict(item) for item in outputs])
    index_path = output_root / "ingest_outputs.parquet"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index.to_parquet(index_path, compression="zstd", index=False)
    write_json(output_root / "ingest_outputs.json", [asdict(item) for item in outputs])
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize compressed wearable pain/context datasets.")
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--chunksize", type=int, default=100_000)
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("inventory")
    inventory.add_argument("--output", default=None)

    normalize = sub.add_parser("normalize")
    normalize.add_argument("datasets", nargs="+", choices=sorted(NORMALIZERS))
    normalize.add_argument("--max-sessions", type=int, default=None)
    normalize.add_argument("--max-chunks", type=int, default=None)

    normalize_all = sub.add_parser("normalize-all")
    normalize_all.add_argument("--max-sessions", type=int, default=None)
    normalize_all.add_argument("--max-chunks", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    source_root = Path(args.source_root)
    output_root = Path(args.output_root)
    if args.command == "inventory":
        payload = inventory_sources(source_root)
        if args.output:
            write_json(Path(args.output), payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if args.command == "normalize-all":
        dataset_ids = sorted(NORMALIZERS)
    else:
        dataset_ids = args.datasets
    outputs = ingest_datasets(
        dataset_ids,
        source_root=source_root,
        output_root=output_root,
        chunksize=args.chunksize,
        max_sessions=args.max_sessions,
        max_chunks=args.max_chunks,
    )
    print(json.dumps([asdict(item) for item in outputs], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
