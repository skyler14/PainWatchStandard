#!/usr/bin/env python3
"""Read-only local web gateway for the compressed pain dataset folder.

The service intentionally keeps the original archives compressed. It builds a
small in-memory manifest from zip central directories and streams requested rows
from source members on demand.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parent
MAX_LIMIT = 10_000


@dataclass(frozen=True)
class ArchiveInfo:
    dataset_id: str
    source_path: str
    source_type: str
    compressed_bytes: int
    useful_members: int | None
    useful_uncompressed_bytes: int | None


@dataclass(frozen=True)
class MemberInfo:
    dataset_id: str
    source_archive: str
    source_member: str
    extension: str
    compressed_bytes: int
    uncompressed_bytes: int
    crc32: str | None
    parser: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    dataset_id: str
    source: str
    description: str
    adapter: str


TABLES: dict[str, TableInfo] = {
    "subject_info_catsa": TableInfo(
        "subject_info_catsa",
        "subject_info_catsa",
        "Subject_info_CATSA.csv",
        "CATSA demographics from the top-level CSV.",
        "plain_csv",
    ),
    "questionnaire": TableInfo(
        "questionnaire",
        "questionnaire",
        "questionnaire.csv",
        "Top-level questionnaire CSV.",
        "plain_csv",
    ),
    "catsa": TableInfo(
        "catsa",
        "catsa",
        "CATSA.zip",
        "CATSA signal rows over subject, task, and sensor CSV members.",
        "catsa",
    ),
    "epm_e4": TableInfo(
        "epm_e4",
        "epm_e4",
        "EPM-E4.zip",
        "EPM-E4 raw, preprocessed, key-moment, and questionnaire rows.",
        "epm_e4",
    ),
    "wesad": TableInfo(
        "wesad",
        "wesad",
        "WESAD.zip",
        "WESAD nested E4 rows plus questionnaire/readme/PKL metadata.",
        "wesad",
    ),
    "wearable_sports_health": TableInfo(
        "wearable_sports_health",
        "wearable_sports_health",
        "archive(1).zip",
        "Single CSV wearable sports health dataset.",
        "zip_single_csv",
    ),
    "merged_wearable_stress": TableInfo(
        "merged_wearable_stress",
        "merged_wearable_stress",
        "archive(2).zip",
        "Large merged wearable stress CSV.",
        "zip_single_csv",
    ),
    "sample_27_9vuw": TableInfo(
        "sample_27_9vuw",
        "sample_27_9vuw",
        "sample(1).zip",
        "Normalized CSV rows for the 27-9VUW sample package.",
        "sample_27",
    ),
    "induced_stress_exercise": TableInfo(
        "induced_stress_exercise",
        "induced_stress_exercise",
        "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip",
        "Induced stress/exercise Empatica E4 dataset.",
        "induced",
    ),
    "rheumapain_64hz": TableInfo(
        "rheumapain_64hz",
        "rheumapain",
        "_normalized/rheumapain/frequency_hz=64/measurement_stream.parquet",
        "Normalized RheumaPain 64 Hz wide per-sample physiology stream.",
        "normalized_parquet",
    ),
    "rheumapain_labels": TableInfo(
        "rheumapain_labels",
        "rheumapain",
        "_normalized/rheumapain/frequency_hz=64/labels.parquet",
        "Normalized RheumaPain session-level pain labels.",
        "normalized_parquet",
    ),
    "rheumapain_subjects": TableInfo(
        "rheumapain_subjects",
        "rheumapain",
        "_normalized/rheumapain/frequency_hz=64/subjects.parquet",
        "Normalized RheumaPain subject metadata.",
        "normalized_parquet",
    ),
    "painmonit_clinical": TableInfo(
        "painmonit_clinical",
        "painmonit",
        "_normalized/painmonit/clinical/measurement_stream.parquet",
        "Normalized PainMonit PMCD clinical per-sample physiology and pain-rate stream.",
        "normalized_parquet",
    ),
    "painmonit_labels": TableInfo(
        "painmonit_labels",
        "painmonit",
        "_normalized/painmonit/clinical/labels.parquet",
        "Normalized PainMonit PMCD session-level label summaries and thresholds.",
        "normalized_parquet",
    ),
    "painmonit_subjects": TableInfo(
        "painmonit_subjects",
        "painmonit",
        "_normalized/painmonit/clinical/subjects.parquet",
        "Normalized PainMonit PMCD subject-level summaries.",
        "normalized_parquet",
    ),
    "pain_windows_1hz_30s": TableInfo(
        "pain_windows_1hz_30s",
        "pain_windows",
        "_normalized/window_features/target_hz=1/window_features.parquet",
        "Model feeder windows at 1 Hz cadence with 30-second trailing native-sample features.",
        "normalized_parquet",
    ),
}


ARCHIVE_TO_DATASET = {
    "CATSA.zip": "catsa",
    "EPM-E4.zip": "epm_e4",
    "WESAD.zip": "wesad",
    "archive(1).zip": "wearable_sports_health",
    "archive(2).zip": "merged_wearable_stress",
    "sample(1).zip": "sample_27_9vuw",
    "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip": "induced_stress_exercise",
    "PainMonit.zip": "painmonit",
    "PhysioPain Dataset.zip": "physiopain",
    "RheumaPain Dataset.zip": "rheumapain",
}


PLAIN_CSV_TO_TABLE = {
    "Subject_info_CATSA.csv": "subject_info_catsa",
    "questionnaire.csv": "questionnaire",
}


CATSA_RATES = {
    "ACC": 32.0,
    "BVP": 64.0,
    "EDA": 4.0,
    "TEMP": 4.0,
    "HR": 1.0,
}


def is_macos_sidecar(member: str) -> bool:
    parts = member.split("/")
    name = parts[-1]
    return parts[0] == "__MACOSX" or name.startswith("._") or name == ".DS_Store"


def normalize_key(key: str) -> str:
    key = key.strip().replace("\ufeff", "")
    key = re.sub(r"[^0-9A-Za-z]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_").lower()
    return key or "field"


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if text == "":
            return None
        return float(text)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def parse_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
        if number > 1_000_000_000:
            return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return text


def add_seconds(timestamp: Any, seconds: float | None) -> str | None:
    if seconds is None:
        return parse_timestamp(timestamp)
    text = str(timestamp).strip() if timestamp is not None else ""
    if not text:
        return None
    try:
        base = datetime.fromtimestamp(float(text), tz=timezone.utc)
    except ValueError:
        parsed = parse_timestamp(text)
        if parsed is None:
            return None
        try:
            base = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
        except ValueError:
            return parsed
    return (base + timedelta(seconds=seconds)).isoformat()


def row_matches(row: dict[str, Any], filters: dict[str, str]) -> bool:
    for key, expected in filters.items():
        actual = row.get(key)
        if actual is None:
            return False
        if str(actual).lower() != expected.lower():
            return False
    return True


def filter_value(filters: dict[str, str], key: str) -> str | None:
    return filters.get(normalize_key(key))


def filter_matches_value(filters: dict[str, str], key: str, value: Any) -> bool:
    expected = filter_value(filters, key)
    if expected is None:
        return True
    if value is None:
        return False
    return str(value).lower() == expected.lower()


def limited(rows: Iterable[dict[str, Any]], limit: int, filters: dict[str, str]) -> Iterator[dict[str, Any]]:
    count = 0
    for row in rows:
        if filters and not row_matches(row, filters):
            continue
        yield row
        count += 1
        if count >= limit:
            return


def text_stream_from_zip(zf: zipfile.ZipFile, info_or_name: zipfile.ZipInfo | str) -> io.TextIOWrapper:
    return io.TextIOWrapper(zf.open(info_or_name), encoding="utf-8-sig", errors="replace", newline="")


def csv_dict_rows(text_io: io.TextIOBase, delimiter: str = ",") -> Iterator[dict[str, Any]]:
    reader = csv.DictReader(text_io, delimiter=delimiter)
    for row in reader:
        yield {normalize_key(k or "field"): v for k, v in row.items()}


def zip_members(archive_name: str) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(ROOT / archive_name) as zf:
        return [i for i in zf.infolist() if not i.is_dir() and not is_macos_sidecar(i.filename)]


class Gateway:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.archives: list[ArchiveInfo] = []
        self.members: list[MemberInfo] = []
        self._build_manifest()

    def _build_manifest(self) -> None:
        archives: list[ArchiveInfo] = []
        members: list[MemberInfo] = []

        for path in sorted(self.root.iterdir()):
            if path.name == ".DS_Store" or path.name.startswith("_gateway_cache"):
                continue
            if path.suffix.lower() == ".csv":
                table = PLAIN_CSV_TO_TABLE.get(path.name, normalize_key(path.stem))
                size = path.stat().st_size
                archives.append(
                    ArchiveInfo(table, path.name, "plain_csv", size, None, size)
                )
                members.append(
                    MemberInfo(table, path.name, path.name, ".csv", size, size, None, "headered_csv")
                )
                continue
            if path.suffix.lower() != ".zip":
                continue
            dataset_id = ARCHIVE_TO_DATASET.get(path.name, normalize_key(path.stem))
            useful_count = 0
            useful_bytes = 0
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if info.is_dir() or is_macos_sidecar(info.filename):
                        continue
                    useful_count += 1
                    useful_bytes += info.file_size
                    ext = Path(info.filename).suffix.lower() or "<none>"
                    members.append(
                        MemberInfo(
                            dataset_id,
                            path.name,
                            info.filename,
                            ext,
                            info.compress_size,
                            info.file_size,
                            f"{info.CRC:08x}",
                            self._guess_parser(path.name, info.filename),
                        )
                    )
            archives.append(
                ArchiveInfo(
                    dataset_id,
                    path.name,
                    "zip",
                    path.stat().st_size,
                    useful_count,
                    useful_bytes,
                )
            )

        self.archives = archives
        self.members = members

    def _guess_parser(self, archive_name: str, member: str) -> str:
        lower = member.lower()
        if archive_name == "WESAD.zip" and lower.endswith(".pkl"):
            return "pkl_metadata_only"
        if lower.endswith(".zip"):
            return "nested_zip"
        if lower.endswith(".txt"):
            return "text_metadata"
        if not lower.endswith(".csv"):
            return "binary_or_other"
        if "/empatica/" in lower and lower.rsplit("/", 1)[-1] in {
            "acc.csv",
            "bvp.csv",
            "eda.csv",
            "hr.csv",
            "ibi.csv",
            "temp.csv",
            "tags.csv",
        }:
            return "empatica_e4"
        if "/wearable_dataset/" in lower:
            return "empatica_e4"
        return "headered_csv"

    def table_rows(self, table: str, filters: dict[str, str] | None = None) -> Iterable[dict[str, Any]]:
        filters = filters or {}
        if table == "subject_info_catsa":
            return iter_plain_csv("Subject_info_CATSA.csv", dataset_id=table)
        if table == "questionnaire":
            return iter_plain_csv("questionnaire.csv", dataset_id=table)
        if table == "wearable_sports_health":
            return iter_single_zip_csv("archive(1).zip", dataset_id=table)
        if table == "merged_wearable_stress":
            return iter_single_zip_csv("archive(2).zip", dataset_id=table)
        if table == "catsa":
            return iter_catsa(filters)
        if table == "epm_e4":
            return iter_epm_e4(filters)
        if table == "wesad":
            return iter_wesad(filters)
        if table == "sample_27_9vuw":
            return iter_sample_27(filters)
        if table == "induced_stress_exercise":
            return iter_induced(filters)
        if table == "rheumapain_64hz":
            return iter_parquet_table("_normalized/rheumapain/frequency_hz=64/measurement_stream.parquet", filters)
        if table == "rheumapain_labels":
            return iter_parquet_table("_normalized/rheumapain/frequency_hz=64/labels.parquet", filters)
        if table == "rheumapain_subjects":
            return iter_parquet_table("_normalized/rheumapain/frequency_hz=64/subjects.parquet", filters)
        if table == "painmonit_clinical":
            return iter_parquet_table("_normalized/painmonit/clinical/measurement_stream.parquet", filters)
        if table == "painmonit_labels":
            return iter_parquet_table("_normalized/painmonit/clinical/labels.parquet", filters)
        if table == "painmonit_subjects":
            return iter_parquet_table("_normalized/painmonit/clinical/subjects.parquet", filters)
        if table == "pain_windows_1hz_30s":
            return iter_parquet_table("_normalized/window_features/target_hz=1/window_features.parquet", filters)
        raise KeyError(table)


gateway = Gateway(ROOT)

app = FastAPI(title="Pain Dataset Gateway", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def iter_plain_csv(filename: str, dataset_id: str) -> Iterator[dict[str, Any]]:
    path = ROOT / filename
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        for idx, row in enumerate(csv_dict_rows(fh), start=1):
            normalized = dict(row)
            subject = normalized.get("subjectid") or normalized.get("id")
            yield {
                "dataset_id": dataset_id,
                "source_archive": filename,
                "source_member": filename,
                "source_row_number": idx,
                "subject_id": subject,
                "payload_json": normalized,
                **normalized,
            }


def iter_parquet_table(filename: str, filters: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
    filters = filters or {}
    path = ROOT / filename
    if not path.exists():
        return
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=10_000):
        data = batch.to_pylist()
        for row in data:
            normalized = {normalize_key(str(k)): v for k, v in row.items()}
            if filters and not row_matches(normalized, filters):
                continue
            yield normalized


def iter_single_zip_csv(archive_name: str, dataset_id: str) -> Iterator[dict[str, Any]]:
    with zipfile.ZipFile(ROOT / archive_name) as zf:
        info = next(i for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith(".csv"))
        with text_stream_from_zip(zf, info) as fh:
            for idx, row in enumerate(csv_dict_rows(fh), start=1):
                normalized = dict(row)
                timestamp = normalized.get("timestamp") or normalized.get("datetime")
                subject = normalized.get("athlete_id") or normalized.get("id")
                out = {
                    "dataset_id": dataset_id,
                    "source_archive": archive_name,
                    "source_member": info.filename,
                    "source_crc32": f"{info.CRC:08x}",
                    "source_compressed_bytes": info.compress_size,
                    "source_uncompressed_bytes": info.file_size,
                    "source_row_number": idx,
                    "subject_id": str(subject) if subject is not None else None,
                    "sample_time_utc": parse_timestamp(timestamp),
                    "payload_json": normalized,
                }
                out.update(normalized)
                yield out


def iter_catsa(filters: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
    filters = filters or {}
    with zipfile.ZipFile(ROOT / "CATSA.zip") as zf:
        infos = [
            i
            for i in zf.infolist()
            if not i.is_dir()
            and not is_macos_sidecar(i.filename)
            and i.filename.lower().endswith(".csv")
        ]
        for info in infos:
            parts = info.filename.split("/")
            if len(parts) != 4:
                continue
            _, subject_id, condition, filename = parts
            sensor = Path(filename).stem
            if not filter_matches_value(filters, "subject_id", subject_id):
                continue
            if not filter_matches_value(filters, "condition", condition):
                continue
            if not filter_matches_value(filters, "sensor", sensor):
                continue
            if not filter_matches_value(filters, "record_type", "signal"):
                continue
            sample_rate = CATSA_RATES.get(sensor)
            with text_stream_from_zip(zf, info) as fh:
                for idx, row in enumerate(csv_dict_rows(fh), start=1):
                    x = to_float(row.get("acc_x"))
                    y = to_float(row.get("acc_y"))
                    z = to_float(row.get("acc_z"))
                    value = None if sensor == "ACC" else to_float(row.get(normalize_key(sensor)))
                    sample_index = idx - 1
                    offset = sample_index / sample_rate if sample_rate else None
                    yield {
                        "dataset_id": "catsa",
                        "source_archive": "CATSA.zip",
                        "source_member": info.filename,
                        "source_crc32": f"{info.CRC:08x}",
                        "source_compressed_bytes": info.compress_size,
                        "source_uncompressed_bytes": info.file_size,
                        "source_row_number": idx,
                        "record_type": "signal",
                        "subject_id": subject_id,
                        "condition": condition,
                        "device": "empatica",
                        "sensor": sensor,
                        "sample_index": sample_index,
                        "sample_rate_hz": sample_rate,
                        "sample_offset_s": offset,
                        "x": x,
                        "y": y,
                        "z": z,
                        "value": value,
                        "payload_json": row,
                    }


def iter_e4_lines(
    lines: Iterable[list[str]],
    dataset_id: str,
    source_archive: str,
    source_member: str,
    subject_id: str | None,
    condition: str | None,
    device: str,
    sensor: str,
    source_meta: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    source_meta = source_meta or {}
    rows = list()
    iterator = iter(lines)
    try:
        first = next(iterator)
    except StopIteration:
        return

    sensor_upper = sensor.upper()
    if sensor_upper == "TAGS":
        for idx, row in enumerate([first, *iterator], start=1):
            if not row or not row[0].strip():
                continue
            yield {
                **source_meta,
                "dataset_id": dataset_id,
                "source_archive": source_archive,
                "source_member": source_member,
                "source_row_number": idx,
                "record_type": "tag",
                "subject_id": subject_id,
                "condition": condition,
                "device": device,
                "sensor": "tags",
                "sample_time_utc": parse_timestamp(row[0]),
                "value": None,
                "payload_json": {"raw": row},
            }
        return

    start = first[0].strip() if first else None
    try:
        second = next(iterator)
    except StopIteration:
        return

    if sensor_upper == "IBI":
        data_iter = [second, *iterator]
        for idx, row in enumerate(data_iter, start=1):
            if not row or not row[0].strip() or row[0].strip().upper() == "IBI":
                continue
            offset = to_float(row[0])
            value = to_float(row[1] if len(row) > 1 else None)
            yield {
                **source_meta,
                "dataset_id": dataset_id,
                "source_archive": source_archive,
                "source_member": source_member,
                "source_row_number": idx,
                "record_type": "signal",
                "subject_id": subject_id,
                "condition": condition,
                "device": device,
                "sensor": sensor_upper,
                "sample_index": idx - 1,
                "sample_offset_s": offset,
                "sample_time_utc": add_seconds(start, offset),
                "value": value,
                "payload_json": {"offset_s": row[0], "ibi_s": row[1] if len(row) > 1 else None},
            }
        return

    sample_rate = to_float(second[0] if second else None)
    for idx, row in enumerate(iterator, start=1):
        if not row:
            continue
        sample_index = idx - 1
        offset = sample_index / sample_rate if sample_rate else None
        x = y = z = value = None
        if sensor_upper == "ACC":
            x = to_float(row[0] if len(row) > 0 else None)
            y = to_float(row[1] if len(row) > 1 else None)
            z = to_float(row[2] if len(row) > 2 else None)
        else:
            value = to_float(row[0])
        yield {
            **source_meta,
            "dataset_id": dataset_id,
            "source_archive": source_archive,
            "source_member": source_member,
            "source_row_number": idx,
            "record_type": "signal",
            "subject_id": subject_id,
            "condition": condition,
            "device": device,
            "sensor": sensor_upper,
            "sample_index": sample_index,
            "sample_rate_hz": sample_rate,
            "sample_offset_s": offset,
            "sample_time_utc": add_seconds(start, offset),
            "x": x,
            "y": y,
            "z": z,
            "value": value,
            "payload_json": {"raw": row},
        }


def csv_rows_from_text_io(fh: io.TextIOBase, delimiter: str = ",") -> Iterator[list[str]]:
    reader = csv.reader(fh, delimiter=delimiter)
    for row in reader:
        yield row


def iter_epm_e4(filters: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
    filters = filters or {}
    archive = "EPM-E4.zip"
    with zipfile.ZipFile(ROOT / archive) as zf:
        for info in zf.infolist():
            if info.is_dir() or is_macos_sidecar(info.filename):
                continue
            member = info.filename
            lower = member.lower()
            meta = {
                "source_crc32": f"{info.CRC:08x}",
                "source_compressed_bytes": info.compress_size,
                "source_uncompressed_bytes": info.file_size,
            }
            if lower.endswith(".csv") and "/key_moments/" in lower:
                condition = Path(member).stem.upper()
                if not filter_matches_value(filters, "record_type", "key_moment"):
                    continue
                if not filter_matches_value(filters, "condition", condition):
                    continue
                with text_stream_from_zip(zf, info) as fh:
                    for idx, row in enumerate(csv_dict_rows(fh), start=1):
                        yield {
                            **meta,
                            "dataset_id": "epm_e4",
                            "source_archive": archive,
                            "source_member": member,
                            "source_row_number": idx,
                            "record_type": "key_moment",
                            "condition": condition,
                            "sample_time_utc": parse_timestamp(row.get("timestamp")),
                            "payload_json": row,
                        }
                continue
            if lower.endswith(".csv") and "/questionnaires/" in lower:
                if not filter_matches_value(filters, "record_type", "questionnaire"):
                    continue
                with text_stream_from_zip(zf, info) as fh:
                    for idx, row in enumerate(csv_dict_rows(fh), start=1):
                        yield {
                            **meta,
                            "dataset_id": "epm_e4",
                            "source_archive": archive,
                            "source_member": member,
                            "source_row_number": idx,
                            "record_type": "questionnaire",
                            "subject_id": row.get("id"),
                            "condition": row.get("emotion"),
                            "payload_json": row,
                        }
                continue
            if lower.endswith(".csv") and "/preprocessed/" in lower:
                parts = member.split("/")
                subject_id = parts[-2] if len(parts) > 2 else None
                condition = Path(parts[-1]).stem.upper()
                quality = "clean" if "clean-signals" in lower else "unclean"
                if not filter_matches_value(filters, "record_type", "preprocessed_empatica"):
                    continue
                if not filter_matches_value(filters, "subject_id", subject_id):
                    continue
                if not filter_matches_value(filters, "condition", condition):
                    continue
                if not filter_matches_value(filters, "device", "empatica"):
                    continue
                with text_stream_from_zip(zf, info) as fh:
                    for idx, row in enumerate(csv_dict_rows(fh), start=1):
                        yield {
                            **meta,
                            "dataset_id": "epm_e4",
                            "source_archive": archive,
                            "source_member": member,
                            "source_row_number": idx,
                            "record_type": "preprocessed_empatica",
                            "quality_stage": quality,
                            "subject_id": subject_id,
                            "condition": condition,
                            "device": "empatica",
                            "sample_rate_hz": 128.0,
                            "sample_time_utc": parse_timestamp(row.get("timestamp")),
                            "x": to_float(row.get("empatica_acc_x")),
                            "y": to_float(row.get("empatica_acc_y")),
                            "z": to_float(row.get("empatica_acc_z")),
                            "hr": to_float(row.get("empatica_hr")),
                            "bvp": to_float(row.get("empatica_bvp")),
                            "eda": to_float(row.get("empatica_eda")),
                            "temp": to_float(row.get("empatica_temp")),
                            "payload_json": row,
                        }
                continue
            if "/raw/" in lower and "/empatica/" in lower and lower.endswith(".csv"):
                parts = member.split("/")
                raw_idx = parts.index("raw")
                subject_id = parts[raw_idx + 1]
                sensor = Path(parts[-1]).stem
                if filter_value(filters, "record_type") not in (None, "signal", "tag"):
                    continue
                if not filter_matches_value(filters, "subject_id", subject_id):
                    continue
                if not filter_matches_value(filters, "device", "empatica"):
                    continue
                if not filter_matches_value(filters, "sensor", sensor):
                    continue
                with text_stream_from_zip(zf, info) as fh:
                    yield from iter_e4_lines(
                        csv_rows_from_text_io(fh),
                        "epm_e4",
                        archive,
                        member,
                        subject_id,
                        None,
                        "empatica",
                        sensor,
                        meta,
                    )
                continue
            if "/raw/" in lower and "/muse/" in lower and lower.endswith(".csv"):
                parts = member.split("/")
                raw_idx = parts.index("raw")
                subject_id = parts[raw_idx + 1]
                filename = parts[-1]
                condition = filename.split("_", 1)[0].upper()
                if not filter_matches_value(filters, "record_type", "raw_muse"):
                    continue
                if not filter_matches_value(filters, "subject_id", subject_id):
                    continue
                if not filter_matches_value(filters, "condition", condition):
                    continue
                if not filter_matches_value(filters, "device", "muse"):
                    continue
                with text_stream_from_zip(zf, info) as fh:
                    for idx, row in enumerate(csv_dict_rows(fh), start=1):
                        yield {
                            **meta,
                            "dataset_id": "epm_e4",
                            "source_archive": archive,
                            "source_member": member,
                            "source_row_number": idx,
                            "record_type": "raw_muse",
                            "subject_id": subject_id,
                            "condition": condition,
                            "device": "muse",
                            "sample_time_utc": parse_timestamp(row.get("timestamp")),
                            "payload_json": row,
                        }


def iter_wesad(filters: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
    filters = filters or {}
    archive = "WESAD.zip"
    with zipfile.ZipFile(ROOT / archive) as outer:
        for info in outer.infolist():
            if info.is_dir() or is_macos_sidecar(info.filename):
                continue
            member = info.filename
            parts = member.split("/")
            subject_id = parts[1] if len(parts) > 1 else None
            if not filter_matches_value(filters, "subject_id", subject_id):
                continue
            meta = {
                "source_crc32": f"{info.CRC:08x}",
                "source_compressed_bytes": info.compress_size,
                "source_uncompressed_bytes": info.file_size,
            }
            lower = member.lower()
            if lower.endswith("_e4_data.zip"):
                if filter_value(filters, "record_type") not in (None, "signal", "tag"):
                    continue
                nested_bytes = outer.read(info)
                with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
                    for ni in nested.infolist():
                        if ni.is_dir() or not ni.filename.lower().endswith(".csv"):
                            continue
                        sensor = Path(ni.filename).stem
                        if not filter_matches_value(filters, "sensor", sensor):
                            continue
                        if not filter_matches_value(filters, "device", "empatica"):
                            continue
                        nested_member = f"{member}!/{ni.filename}"
                        nested_meta = {
                            **meta,
                            "source_member": nested_member,
                            "nested_source_crc32": f"{ni.CRC:08x}",
                            "source_compressed_bytes": ni.compress_size,
                            "source_uncompressed_bytes": ni.file_size,
                        }
                        with text_stream_from_zip(nested, ni) as fh:
                            yield from iter_e4_lines(
                                csv_rows_from_text_io(fh),
                                "wesad",
                                archive,
                                nested_member,
                                subject_id,
                                None,
                                "empatica",
                                sensor,
                                nested_meta,
                            )
                continue
            if lower.endswith("_quest.csv"):
                if not filter_matches_value(filters, "record_type", "questionnaire"):
                    continue
                with text_stream_from_zip(outer, info) as fh:
                    reader = csv.reader(fh, delimiter=";")
                    for idx, row in enumerate(reader, start=1):
                        if not any(cell.strip() for cell in row):
                            continue
                        yield {
                            **meta,
                            "dataset_id": "wesad",
                            "source_archive": archive,
                            "source_member": member,
                            "source_row_number": idx,
                            "record_type": "questionnaire",
                            "subject_id": subject_id,
                            "payload_json": {"cells": row},
                        }
                continue
            if lower.endswith("_readme.txt") or lower.endswith("_respiban.txt"):
                if not filter_matches_value(filters, "record_type", "text_metadata"):
                    continue
                text = outer.read(info).decode("utf-8-sig", errors="replace")
                yield {
                    **meta,
                    "dataset_id": "wesad",
                    "source_archive": archive,
                    "source_member": member,
                    "source_row_number": 1,
                    "record_type": "text_metadata",
                    "subject_id": subject_id,
                    "payload_json": {"text": text[:20_000]},
                }
                continue
            if lower.endswith(".pkl"):
                if not filter_matches_value(filters, "record_type", "pkl_metadata_only"):
                    continue
                yield {
                    **meta,
                    "dataset_id": "wesad",
                    "source_archive": archive,
                    "source_member": member,
                    "source_row_number": 1,
                    "record_type": "pkl_metadata_only",
                    "subject_id": subject_id,
                    "payload_json": {"note": "PKL internals are not parsed by default."},
                }


def sample_record_type(filename: str) -> tuple[str, str | None, str | None]:
    stem = Path(filename).stem
    if stem.startswith("signals-"):
        _, device, sensor = stem.split("-", 2)
        return "signal", device, sensor
    if stem.startswith("markers-"):
        return stem.replace("-", "_"), None, None
    return stem.replace("-", "_"), None, None


def iter_sample_27(filters: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
    filters = filters or {}
    archive = "sample(1).zip"
    with zipfile.ZipFile(ROOT / archive) as zf:
        infos = [
            i
            for i in zf.infolist()
            if not i.is_dir()
            and not is_macos_sidecar(i.filename)
            and i.filename.startswith("csv/27-9VUW/")
            and i.filename.lower().endswith(".csv")
        ]
        for info in infos:
            record_type, device, sensor = sample_record_type(info.filename.split("/")[-1])
            if not filter_matches_value(filters, "record_type", record_type):
                continue
            if not filter_matches_value(filters, "subject_id", "27-9VUW"):
                continue
            if not filter_matches_value(filters, "device", device):
                continue
            if not filter_matches_value(filters, "sensor", sensor):
                continue
            meta = {
                "source_crc32": f"{info.CRC:08x}",
                "source_compressed_bytes": info.compress_size,
                "source_uncompressed_bytes": info.file_size,
            }
            with text_stream_from_zip(zf, info) as fh:
                for idx, row in enumerate(csv_dict_rows(fh), start=1):
                    timestamp = row.get("timestamp")
                    yield {
                        **meta,
                        "dataset_id": "sample_27_9vuw",
                        "source_archive": archive,
                        "source_member": info.filename,
                        "source_row_number": idx,
                        "record_type": record_type,
                        "subject_id": "27-9VUW",
                        "device": device,
                        "sensor": sensor,
                        "sample_offset_s": to_float(timestamp),
                        "x": to_float(row.get("x")),
                        "y": to_float(row.get("y")),
                        "z": to_float(row.get("z")),
                        "value": to_float(row.get("value")),
                        "payload_json": row,
                    }


def iter_induced(filters: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
    filters = filters or {}
    archive = "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip"
    root_prefix = "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1/"
    with zipfile.ZipFile(ROOT / archive) as zf:
        for info in zf.infolist():
            if info.is_dir() or is_macos_sidecar(info.filename) or not info.filename.lower().endswith(".csv"):
                continue
            member = info.filename
            rel = member.removeprefix(root_prefix)
            parts = rel.split("/")
            meta = {
                "source_crc32": f"{info.CRC:08x}",
                "source_compressed_bytes": info.compress_size,
                "source_uncompressed_bytes": info.file_size,
            }
            if len(parts) == 4 and parts[0] == "Wearable_Dataset":
                _, activity, subject_id, filename = parts
                sensor = Path(filename).stem
                if not filter_matches_value(filters, "record_type", "signal"):
                    continue
                if not filter_matches_value(filters, "condition", activity):
                    continue
                if not filter_matches_value(filters, "subject_id", subject_id):
                    continue
                if not filter_matches_value(filters, "sensor", sensor):
                    continue
                if not filter_matches_value(filters, "device", "empatica"):
                    continue
                with text_stream_from_zip(zf, info) as fh:
                    yield from iter_e4_lines(
                        csv_rows_from_text_io(fh),
                        "induced_stress_exercise",
                        archive,
                        member,
                        subject_id,
                        activity,
                        "empatica",
                        sensor,
                        meta,
                    )
                continue
            with text_stream_from_zip(zf, info) as fh:
                record_type = Path(parts[-1]).stem.lower()
                if not filter_matches_value(filters, "record_type", record_type):
                    continue
                for idx, row in enumerate(csv_dict_rows(fh), start=1):
                    yield {
                        **meta,
                        "dataset_id": "induced_stress_exercise",
                        "source_archive": archive,
                        "source_member": member,
                        "source_row_number": idx,
                        "record_type": record_type,
                        "subject_id": row.get("info") or row.get("field"),
                        "payload_json": row,
                    }


def parse_simple_sql(sql: str) -> tuple[str, dict[str, str], int]:
    stripped = " ".join(sql.strip().rstrip(";").split())
    match = re.match(
        r"(?is)^select\s+.+?\s+from\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+where\s+(.+?))?(?:\s+limit\s+(\d+))?$",
        stripped,
    )
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Only simple SELECT ... FROM table WHERE col = 'value' AND ... LIMIT n is supported.",
        )
    table = match.group(1)
    where = match.group(2)
    limit = min(int(match.group(3) or 100), MAX_LIMIT)
    filters: dict[str, str] = {}
    if where:
        conditions = re.split(r"(?i)\s+and\s+", where)
        for cond in conditions:
            cm = re.match(r"(?is)^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*'?([^']*?)'?$", cond.strip())
            if not cm:
                raise HTTPException(status_code=400, detail=f"Unsupported WHERE condition: {cond}")
            filters[normalize_key(cm.group(1))] = cm.group(2)
    return table, filters, limit


def request_filters(request: Request) -> dict[str, str]:
    filters: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key in {"limit", "offset"}:
            continue
        if value != "":
            filters[normalize_key(key)] = value
    return filters


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pain Dataset Gateway</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #111317; color: #eceff3; }
    header { padding: 18px 22px; border-bottom: 1px solid #2b3038; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    h1 { font-size: 18px; margin: 0; font-weight: 650; letter-spacing: 0; }
    main { display: grid; grid-template-columns: 300px 1fr; min-height: calc(100vh - 61px); }
    aside { border-right: 1px solid #2b3038; padding: 16px; overflow: auto; }
    section { padding: 16px; overflow: auto; }
    button, select, input, textarea { background: #191d23; color: #eceff3; border: 1px solid #39404b; border-radius: 6px; font: inherit; }
    button { padding: 8px 10px; cursor: pointer; }
    button:hover { border-color: #657083; }
    textarea { width: 100%; min-height: 96px; resize: vertical; box-sizing: border-box; padding: 10px; }
    .toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
    .table-btn { width: 100%; margin-bottom: 6px; text-align: left; display: block; }
    .muted { color: #9aa3af; font-size: 12px; }
    .pill { border: 1px solid #39404b; border-radius: 999px; padding: 4px 8px; color: #bac2cf; font-size: 12px; }
    table { border-collapse: collapse; width: 100%; font-size: 12px; }
    th, td { border-bottom: 1px solid #2b3038; padding: 7px 8px; vertical-align: top; max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    th { color: #cbd2dc; text-align: left; background: #161a20; position: sticky; top: 0; }
    pre { white-space: pre-wrap; background: #15191f; border: 1px solid #2b3038; border-radius: 6px; padding: 10px; overflow: auto; }
    @media (max-width: 760px) { main { grid-template-columns: 1fr; } aside { border-right: 0; border-bottom: 1px solid #2b3038; } }
  </style>
</head>
<body>
  <header>
    <h1>Pain Dataset Gateway</h1>
    <div class="toolbar" style="margin:0">
      <span class="pill">read-only</span>
      <span class="pill">zip-streamed</span>
      <span class="pill" id="status">loading</span>
    </div>
  </header>
  <main>
    <aside>
      <div class="muted" style="margin-bottom:8px">Tables</div>
      <div id="tables"></div>
    </aside>
    <section>
      <div class="toolbar">
        <button id="preview">Preview</button>
        <button id="run">Run SQL</button>
        <input id="limit" type="number" min="1" max="10000" value="100" style="width:96px">
      </div>
      <textarea id="sql">select * from catsa where subject_id = 'Sub1' and sensor = 'EDA' limit 100</textarea>
      <div class="muted" id="meta" style="margin: 10px 0"></div>
      <div id="result"></div>
    </section>
  </main>
<script>
let currentTable = "catsa";
function esc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function renderRows(rows) {
  if (!rows.length) { document.getElementById("result").innerHTML = "<pre>[]</pre>"; return; }
  const cols = [...new Set(rows.flatMap(r => Object.keys(r)))].slice(0, 40);
  document.getElementById("result").innerHTML = "<table><thead><tr>" + cols.map(c => `<th>${esc(c)}</th>`).join("") + "</tr></thead><tbody>" +
    rows.map(r => "<tr>" + cols.map(c => `<td title="${esc(typeof r[c] === "object" ? JSON.stringify(r[c]) : r[c])}">${esc(typeof r[c] === "object" ? JSON.stringify(r[c]) : r[c])}</td>`).join("") + "</tr>").join("") +
    "</tbody></table>";
}
async function loadTables() {
  const res = await fetch("/api/tables");
  const data = await res.json();
  document.getElementById("status").textContent = "online";
  document.getElementById("tables").innerHTML = data.tables.map(t => `<button class="table-btn" data-table="${esc(t.name)}">${esc(t.name)}<div class="muted">${esc(t.source)}</div></button>`).join("");
  document.querySelectorAll(".table-btn").forEach(btn => btn.onclick = () => {
    currentTable = btn.dataset.table;
    document.getElementById("sql").value = `select * from ${currentTable} limit ${document.getElementById("limit").value}`;
    preview();
  });
}
async function preview() {
  const limit = document.getElementById("limit").value;
  const res = await fetch(`/api/preview/${currentTable}?limit=${encodeURIComponent(limit)}`);
  const data = await res.json();
  document.getElementById("meta").textContent = `${data.table}: ${data.rows.length} rows`;
  renderRows(data.rows);
}
async function runSql() {
  const res = await fetch("/api/query", { method: "POST", headers: {"content-type":"application/json"}, body: JSON.stringify({sql: document.getElementById("sql").value}) });
  const data = await res.json();
  if (!res.ok) { document.getElementById("result").innerHTML = `<pre>${esc(JSON.stringify(data, null, 2))}</pre>`; return; }
  document.getElementById("meta").textContent = `${data.table}: ${data.rows.length} rows`;
  renderRows(data.rows);
}
document.getElementById("preview").onclick = preview;
document.getElementById("run").onclick = runSql;
loadTables().then(preview);
</script>
</body>
</html>"""


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "root": str(ROOT),
        "tables": len(TABLES),
        "archives": len(gateway.archives),
        "members": len(gateway.members),
    }


@app.get("/api/connection")
def connection(request: Request) -> dict[str, Any]:
    return {
        "type": "http",
        "base_url": str(request.base_url).rstrip("/"),
        "cors": "enabled",
        "read_only": True,
        "notes": [
            "This is a web/API gateway, not a PostgreSQL wire server.",
            "Rows are streamed from local compressed files on demand.",
        ],
    }


@app.get("/api/tables")
def tables() -> dict[str, Any]:
    return {"tables": [asdict(info) for info in TABLES.values()]}


@app.get("/api/archives")
def archives() -> dict[str, Any]:
    return {"archives": [asdict(info) for info in gateway.archives]}


@app.get("/api/members")
def members(
    dataset_id: str | None = None,
    source_archive: str | None = None,
    limit: int = Query(500, ge=1, le=10_000),
) -> dict[str, Any]:
    rows = []
    for member in gateway.members:
        if dataset_id and member.dataset_id != dataset_id:
            continue
        if source_archive and member.source_archive != source_archive:
            continue
        rows.append(asdict(member))
        if len(rows) >= limit:
            break
    return {"members": rows}


@app.get("/api/preview/{table}")
def preview(table: str, request: Request, limit: int = Query(100, ge=1, le=MAX_LIMIT)) -> dict[str, Any]:
    if table not in TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")
    filters = request_filters(request)
    rows = list(limited(gateway.table_rows(table, filters), limit, filters))
    return {"table": table, "limit": limit, "filters": filters, "rows": rows}


@app.get("/api/stream/{table}")
def stream(table: str, request: Request, limit: int = Query(1000, ge=1, le=MAX_LIMIT)) -> StreamingResponse:
    if table not in TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")
    filters = request_filters(request)

    def generate() -> Iterator[str]:
        for row in limited(gateway.table_rows(table, filters), limit, filters):
            yield json.dumps(row, default=str) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.post("/api/query")
async def query(payload: dict[str, Any]) -> dict[str, Any]:
    sql = str(payload.get("sql", ""))
    table, filters, limit = parse_simple_sql(sql)
    if table not in TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")
    rows = list(limited(gateway.table_rows(table, filters), limit, filters))
    return {"table": table, "limit": limit, "filters": filters, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
