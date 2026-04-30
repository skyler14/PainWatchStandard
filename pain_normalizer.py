#!/usr/bin/env python3
"""Compressed-file normalizers for the pain thermometer datasets.

The normalizer keeps source archives compressed and writes only compressed
Parquet outputs. Production paths target direct pain-labeled datasets first so
the gateway can expose usable training tables without a dedicated database.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "_normalized"


@dataclass
class NormalizedFile:
    dataset_id: str
    output_kind: str
    path: str
    rows: int
    bytes: int


def normalize_column(name: str) -> str:
    name = name.strip().replace("\ufeff", "")
    name = re.sub(r"[^0-9A-Za-z]+", "_", name)
    return re.sub(r"_+", "_", name).strip("_").lower()


def clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def clean_numeric(series: pd.Series) -> pd.Series:
    if not pd.api.types.is_numeric_dtype(series):
        series = series.astype("string").str.replace(",", ".", regex=False)
    return pd.to_numeric(series, errors="coerce")


def clean_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        text = str(value).strip().replace(",", ".")
        if not text or text.lower() == "nan":
            return None
        return float(text)
    except ValueError:
        return None


def numeric_values(value: Any) -> list[float]:
    if value is None or pd.isna(value):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    text = str(value)
    values: list[float] = []
    for match in re.findall(r"\d+(?:\.\d+)?", text):
        values.append(float(match))
    return values


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def useful_zip_infos(zip_path: Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(zip_path) as zf:
        infos = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split("/")
            name = parts[-1]
            if parts[0] == "__MACOSX" or name.startswith("._") or name == ".DS_Store":
                continue
            infos.append(info)
        return infos


def inspect_sources() -> dict[str, Any]:
    sources: dict[str, Any] = {}
    for path in sorted(ROOT.glob("*.zip")):
        infos = useful_zip_infos(path)
        sources[path.name] = {
            "compressed_bytes": path.stat().st_size,
            "members": len(infos),
            "uncompressed_bytes": sum(i.file_size for i in infos),
            "extensions": {},
        }
        for info in infos:
            suffix = Path(info.filename).suffix.lower() or "<none>"
            sources[path.name]["extensions"][suffix] = sources[path.name]["extensions"].get(suffix, 0) + 1
    for path in sorted(ROOT.glob("*.csv")):
        sources[path.name] = {
            "compressed_bytes": path.stat().st_size,
            "members": 1,
            "uncompressed_bytes": path.stat().st_size,
            "extensions": {".csv": 1},
        }
    return sources


def rheumapain_processed_members(frequency_hz: int) -> list[zipfile.ZipInfo]:
    archive = ROOT / "RheumaPain Dataset.zip"
    pattern = f"/Processed Data/{frequency_hz}Hz/"
    return [
        info
        for info in useful_zip_infos(archive)
        if pattern in info.filename and info.filename.lower().endswith(".csv")
    ]


def load_rheumapain_demographics() -> dict[str, dict[str, Any]]:
    archive = ROOT / "RheumaPain Dataset.zip"
    with zipfile.ZipFile(archive) as zf:
        member = next(
            info.filename
            for info in zf.infolist()
            if info.filename.endswith("RheumaPain/Demographic Data/patients.xlsx")
        )
        with zf.open(member) as raw:
            frame = pd.read_excel(raw)

    frame.columns = [normalize_column(c) for c in frame.columns]
    demographics: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        subject_id = clean_text(row.get("uid"))
        if not subject_id:
            continue
        subject_id = subject_id.lower()
        gender = clean_text(row.get("gender"))
        demographics[subject_id] = {
            "subject_id": subject_id,
            "sex": gender.lower() if gender else None,
            "age": None if pd.isna(row.get("age")) else float(row.get("age")),
            "diagnosis": clean_text(row.get("diagnosis")),
            "pain_rest_values": numeric_values(row.get("pain_scale_rest")),
            "pain_exercise_values": numeric_values(row.get("pain_scale_exercise")),
            "exercise_durations": clean_text(row.get("exercise_durations_seconds")),
        }
    return demographics


def normalize_rheumapain(frequency_hz: int, output_root: Path, chunksize: int) -> list[NormalizedFile]:
    archive = ROOT / "RheumaPain Dataset.zip"
    if not archive.exists():
        raise FileNotFoundError(archive)

    members = rheumapain_processed_members(frequency_hz)
    if not members:
        raise RuntimeError(f"No RheumaPain processed CSVs found for {frequency_hz} Hz")

    out_dir = output_root / "rheumapain" / f"frequency_hz={frequency_hz}"
    out_dir.mkdir(parents=True, exist_ok=True)
    stream_path = out_dir / "measurement_stream.parquet"
    labels_path = out_dir / "labels.parquet"
    subjects_path = out_dir / "subjects.parquet"
    manifest_path = out_dir / "manifest.json"

    writer: pq.ParquetWriter | None = None
    total_rows = 0
    label_rows: list[dict[str, Any]] = []
    subject_rows: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    demographics = load_rheumapain_demographics()

    with zipfile.ZipFile(archive) as zf:
        for info in sorted(members, key=lambda x: x.filename):
            source_rows.append(
                {
                    "source_archive": archive.name,
                    "source_member": info.filename,
                    "compressed_bytes": info.compress_size,
                    "uncompressed_bytes": info.file_size,
                    "crc32": f"{info.CRC:08x}",
                }
            )
            cumulative = 0
            file_label_values: set[float] = set()
            file_subject_id: str | None = None
            file_session_id: str | None = None
            file_condition: str | None = None
            file_diagnosis: str | None = None
            file_sex: str | None = None
            file_age: float | None = None

            with zf.open(info) as raw:
                reader = pd.read_csv(raw, chunksize=chunksize)
                for chunk in reader:
                    chunk.columns = [normalize_column(c) for c in chunk.columns]
                    required = {
                        "bvp",
                        "eda",
                        "x",
                        "y",
                        "z",
                        "temperature",
                        "pain_scale",
                        "diagnosis",
                        "person_id",
                        "sex",
                        "age",
                        "exercise_rest",
                    }
                    missing = sorted(required.difference(chunk.columns))
                    if missing:
                        raise RuntimeError(f"{info.filename} missing required columns: {missing}")

                    row_count = len(chunk)
                    if row_count == 0:
                        continue

                    sample_index = pd.Series(range(cumulative, cumulative + row_count), index=chunk.index)
                    cumulative += row_count
                    total_rows += row_count

                    person_id = chunk["person_id"].astype("string").str.strip()
                    condition = chunk["exercise_rest"].astype("string").str.strip().str.lower()
                    session_id = person_id.fillna(Path(info.filename).stem) + "_" + condition.fillna("unknown")

                    out = pd.DataFrame(
                        {
                            "dataset_id": "rheumapain",
                            "source_archive": archive.name,
                            "source_member": info.filename,
                            "subject_id": person_id,
                            "session_id": session_id,
                            "condition": condition,
                            "device": "empatica_e4",
                            "sample_rate_hz": float(frequency_hz),
                            "sample_index": sample_index.astype("int64"),
                            "sample_offset_s": sample_index.astype("float64") / float(frequency_hz),
                            "bvp": clean_numeric(chunk["bvp"]),
                            "eda": clean_numeric(chunk["eda"]),
                            "acc_x": clean_numeric(chunk["x"]),
                            "acc_y": clean_numeric(chunk["y"]),
                            "acc_z": clean_numeric(chunk["z"]),
                            "temperature": clean_numeric(chunk["temperature"]),
                            "pain_score": clean_numeric(chunk["pain_scale"]),
                            "pain_scale_type": "wong_baker_faces",
                            "diagnosis": chunk["diagnosis"].astype("string").str.strip(),
                            "sex": chunk["sex"].astype("string").str.strip(),
                            "age": clean_numeric(chunk["age"]),
                        }
                    )

                    first = out.iloc[0]
                    file_subject_id = clean_text(first["subject_id"])
                    file_session_id = clean_text(first["session_id"])
                    file_condition = clean_text(first["condition"])
                    demo = demographics.get(file_subject_id or "")
                    file_diagnosis = (demo or {}).get("diagnosis") or clean_text(first["diagnosis"])
                    file_sex = (demo or {}).get("sex") or clean_text(first["sex"])
                    file_age = (demo or {}).get("age")
                    if file_age is None:
                        file_age = None if pd.isna(first["age"]) else float(first["age"])
                    if demo:
                        out["sex"] = pd.Series([demo.get("sex")] * len(out), dtype="string")
                        out["age"] = demo.get("age")
                        out["diagnosis"] = pd.Series([demo.get("diagnosis")] * len(out), dtype="string")
                        if file_condition == "rest" and len(demo.get("pain_rest_values", [])) == 1:
                            out["pain_score"] = demo["pain_rest_values"][0]
                        elif file_condition == "exercise" and len(demo.get("pain_exercise_values", [])) == 1:
                            out["pain_score"] = demo["pain_exercise_values"][0]
                    out["sex"] = out["sex"].astype("string")
                    out["diagnosis"] = out["diagnosis"].astype("string")
                    out["pain_score"] = pd.to_numeric(out["pain_score"], errors="coerce").astype("float64")
                    for value in out["pain_score"].dropna().unique().tolist():
                        file_label_values.add(float(value))

                    if file_subject_id:
                        existing = subject_rows.get(file_subject_id, {})
                        subject_rows[file_subject_id] = {
                            "dataset_id": "rheumapain",
                            "subject_id": file_subject_id,
                            "sex": file_sex or existing.get("sex"),
                            "age": file_age if file_age is not None else existing.get("age"),
                            "diagnosis": file_diagnosis or existing.get("diagnosis"),
                        }

                    table = pa.Table.from_pandas(out, preserve_index=False)
                    if writer is None:
                        writer = pq.ParquetWriter(
                            stream_path,
                            table.schema,
                            compression="zstd",
                            use_dictionary=True,
                        )
                    writer.write_table(table)

            if file_subject_id:
                demo = demographics.get(file_subject_id, {})
                canonical_label = None
                if file_condition == "rest":
                    workbook_values = demo.get("pain_rest_values", [])
                elif file_condition == "exercise":
                    workbook_values = demo.get("pain_exercise_values", [])
                else:
                    workbook_values = []
                if len(workbook_values) == 1:
                    canonical_label = workbook_values[0]
                    label_value_policy = "single_workbook_value"
                elif len(file_label_values) == 1:
                    canonical_label = sorted(file_label_values)[0]
                    label_value_policy = "single_csv_value"
                else:
                    label_value_policy = "ambiguous_multi_value_session"
                label_rows.append(
                    {
                        "dataset_id": "rheumapain",
                        "subject_id": file_subject_id,
                        "session_id": file_session_id,
                        "condition": file_condition,
                        "label_type": "pain_wong_baker",
                        "label_value": canonical_label,
                        "label_value_policy": label_value_policy,
                        "label_values_observed": sorted(file_label_values),
                        "label_values_workbook": workbook_values,
                        "label_source": "patients_xlsx_with_csv_crosscheck",
                        "exercise_durations": demo.get("exercise_durations"),
                        "source_archive": archive.name,
                        "source_member": info.filename,
                    }
                )

    if writer is not None:
        writer.close()

    labels = pd.DataFrame(label_rows)
    labels.to_parquet(labels_path, compression="zstd", index=False)

    subjects = pd.DataFrame(sorted(subject_rows.values(), key=lambda row: row["subject_id"]))
    subjects.to_parquet(subjects_path, compression="zstd", index=False)

    manifest = {
        "dataset_id": "rheumapain",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frequency_hz": frequency_hz,
        "source_archive": archive.name,
        "source_members": source_rows,
        "rows": total_rows,
        "outputs": {
            "measurement_stream": display_path(stream_path),
            "labels": display_path(labels_path),
            "subjects": display_path(subjects_path),
        },
        "schema_note": "Wide, per-sample physiology frame for window feature extraction.",
    }
    write_json(manifest_path, manifest)

    outputs = [
        NormalizedFile("rheumapain", "measurement_stream", str(stream_path), total_rows, stream_path.stat().st_size),
        NormalizedFile("rheumapain", "labels", str(labels_path), len(labels), labels_path.stat().st_size),
        NormalizedFile("rheumapain", "subjects", str(subjects_path), len(subjects), subjects_path.stat().st_size),
    ]
    return outputs


def parse_painmonit_session(member: str) -> dict[str, Any]:
    match = re.search(r"/(?P<session>P(?P<subject>\d+)_(?P<trial>\d+))/(?P=session)\.csv$", member)
    if not match:
        raise RuntimeError(f"Could not parse PainMonit session path: {member}")
    session_code = match.group("session")
    return {
        "subject_id": f"p{match.group('subject')}",
        "session_id": session_code.lower(),
        "session_number": int(match.group("trial")),
    }


def painmonit_threshold(inner: zipfile.ZipFile, session_dir: str, filename: str) -> float | None:
    member = f"{session_dir}/{filename}"
    try:
        raw = inner.read(member).decode("utf-8-sig", errors="replace").strip()
    except KeyError:
        return None
    return clean_float(raw)


def normalize_painmonit_clinical(output_root: Path, chunksize: int) -> list[NormalizedFile]:
    archive = ROOT / "PainMonit.zip"
    if not archive.exists():
        raise FileNotFoundError(archive)

    out_dir = output_root / "painmonit" / "clinical"
    out_dir.mkdir(parents=True, exist_ok=True)
    stream_path = out_dir / "measurement_stream.parquet"
    labels_path = out_dir / "labels.parquet"
    subjects_path = out_dir / "subjects.parquet"
    manifest_path = out_dir / "manifest.json"

    writer: pq.ParquetWriter | None = None
    total_rows = 0
    label_rows: list[dict[str, Any]] = []
    subject_sessions: dict[str, set[str]] = {}
    source_rows: list[dict[str, Any]] = []

    with zipfile.ZipFile(archive) as outer:
        nested_name = "PMCD.zip"
        nested_info = outer.getinfo(nested_name)
        with zipfile.ZipFile(outer.open(nested_info)) as inner:
            members = [
                info
                for info in inner.infolist()
                if not info.is_dir()
                and info.filename.lower().endswith(".csv")
                and not info.filename.lower().endswith("_runup.csv")
                and "/raw-data/" in info.filename.lower()
            ]
            if not members:
                raise RuntimeError("No PainMonit PMCD clinical main CSVs found")

            for info in sorted(members, key=lambda item: item.filename):
                parsed = parse_painmonit_session(info.filename)
                session_dir = str(Path(info.filename).parent)
                no_pain_threshold = painmonit_threshold(inner, session_dir, "noPainThreshold.txt")
                severe_pain_threshold = painmonit_threshold(inner, session_dir, "severePainThreshold.txt")

                source_rows.append(
                    {
                        "source_archive": archive.name,
                        "nested_archive": nested_name,
                        "source_member": info.filename,
                        "compressed_bytes": info.compress_size,
                        "uncompressed_bytes": info.file_size,
                        "crc32": f"{info.CRC:08x}",
                    }
                )

                cumulative = 0
                pain_rate_min: float | None = None
                pain_rate_max: float | None = None
                pain_rate_nonnull_rows = 0
                observed_labels: set[str] = set()

                with inner.open(info) as raw:
                    reader = pd.read_csv(
                        raw,
                        sep=";",
                        decimal=",",
                        chunksize=chunksize,
                        na_values=["NaN", "nan", ""],
                    )
                    for chunk in reader:
                        chunk.columns = [normalize_column(c) for c in chunk.columns]
                        required = {
                            "seconds",
                            "bvp",
                            "eda_e4",
                            "tmp",
                            "resp",
                            "eda_rb",
                            "bvp_rb",
                            "emg",
                            "grip",
                            "pain_rates",
                            "pain_labels",
                        }
                        missing = sorted(required.difference(chunk.columns))
                        if missing:
                            raise RuntimeError(f"{info.filename} missing required columns: {missing}")

                        row_count = len(chunk)
                        if row_count == 0:
                            continue

                        sample_index = pd.Series(range(cumulative, cumulative + row_count), index=chunk.index)
                        cumulative += row_count
                        total_rows += row_count

                        pain_label = chunk["pain_labels"].astype("string").str.strip()
                        pain_label = pain_label.mask(
                            pain_label.isna()
                            | pain_label.str.lower().isin(["", "nan", "<na>"]),
                            pd.NA,
                        )
                        for value in pain_label.dropna().unique().tolist():
                            observed_labels.add(str(value))

                        pain_rate = clean_numeric(chunk["pain_rates"]).astype("float64")
                        nonnull_pain = pain_rate.dropna()
                        if not nonnull_pain.empty:
                            chunk_min = float(nonnull_pain.min())
                            chunk_max = float(nonnull_pain.max())
                            pain_rate_min = chunk_min if pain_rate_min is None else min(pain_rate_min, chunk_min)
                            pain_rate_max = chunk_max if pain_rate_max is None else max(pain_rate_max, chunk_max)
                            pain_rate_nonnull_rows += int(nonnull_pain.shape[0])

                        out = pd.DataFrame(
                            {
                                "dataset_id": "painmonit",
                                "source_archive": archive.name,
                                "nested_archive": nested_name,
                                "source_member": info.filename,
                                "subject_id": parsed["subject_id"],
                                "session_id": parsed["session_id"],
                                "session_number": parsed["session_number"],
                                "condition": "clinical_physiotherapy",
                                "record_type": "clinical_main",
                                "device": "empatica_e4_respiratory_belt_emg_grip",
                                "sample_rate_hz": 250.0,
                                "sample_index": sample_index.astype("int64"),
                                "sample_offset_s": clean_numeric(chunk["seconds"]).astype("float64"),
                                "bvp": clean_numeric(chunk["bvp"]).astype("float64"),
                                "eda_e4": clean_numeric(chunk["eda_e4"]).astype("float64"),
                                "temperature": clean_numeric(chunk["tmp"]).astype("float64"),
                                "respiration": clean_numeric(chunk["resp"]).astype("float64"),
                                "eda_rb": clean_numeric(chunk["eda_rb"]).astype("float64"),
                                "bvp_rb": clean_numeric(chunk["bvp_rb"]).astype("float64"),
                                "emg": clean_numeric(chunk["emg"]).astype("float64"),
                                "grip": clean_numeric(chunk["grip"]).astype("float64"),
                                "pain_rate_nrs": pain_rate,
                                "pain_label": pain_label.astype("string"),
                                "pain_scale_type": "nrs_0_10",
                                "no_pain_threshold": no_pain_threshold,
                                "severe_pain_threshold": severe_pain_threshold,
                            }
                        )
                        for column in [
                            "dataset_id",
                            "source_archive",
                            "nested_archive",
                            "source_member",
                            "subject_id",
                            "session_id",
                            "condition",
                            "record_type",
                            "device",
                            "pain_label",
                            "pain_scale_type",
                        ]:
                            out[column] = out[column].astype("string")
                        out["no_pain_threshold"] = out["no_pain_threshold"].astype("float64")
                        out["severe_pain_threshold"] = out["severe_pain_threshold"].astype("float64")

                        table = pa.Table.from_pandas(out, preserve_index=False)
                        if writer is None:
                            writer = pq.ParquetWriter(
                                stream_path,
                                table.schema,
                                compression="zstd",
                                use_dictionary=True,
                            )
                        writer.write_table(table)

                subject_sessions.setdefault(parsed["subject_id"], set()).add(parsed["session_id"])
                label_rows.append(
                    {
                        "dataset_id": "painmonit",
                        "subject_id": parsed["subject_id"],
                        "session_id": parsed["session_id"],
                        "session_number": parsed["session_number"],
                        "condition": "clinical_physiotherapy",
                        "record_type": "clinical_main",
                        "label_type": "pain_nrs_timeseries",
                        "pain_scale_type": "nrs_0_10",
                        "pain_rate_min": pain_rate_min,
                        "pain_rate_max": pain_rate_max,
                        "pain_rate_nonnull_rows": pain_rate_nonnull_rows,
                        "pain_labels_observed": sorted(observed_labels),
                        "no_pain_threshold": no_pain_threshold,
                        "severe_pain_threshold": severe_pain_threshold,
                        "label_source": "Pain rates and Pain labels columns",
                        "source_archive": archive.name,
                        "nested_archive": nested_name,
                        "source_member": info.filename,
                    }
                )

    if writer is not None:
        writer.close()

    labels = pd.DataFrame(label_rows)
    labels.to_parquet(labels_path, compression="zstd", index=False)

    subject_rows = []
    for subject_id, sessions in sorted(subject_sessions.items()):
        subject_labels = labels[labels["subject_id"] == subject_id]
        subject_rows.append(
            {
                "dataset_id": "painmonit",
                "subject_id": subject_id,
                "session_count": len(sessions),
                "pain_rate_min": clean_float(subject_labels["pain_rate_min"].min()),
                "pain_rate_max": clean_float(subject_labels["pain_rate_max"].max()),
                "no_pain_threshold_min": clean_float(subject_labels["no_pain_threshold"].min()),
                "no_pain_threshold_max": clean_float(subject_labels["no_pain_threshold"].max()),
                "severe_pain_threshold_min": clean_float(subject_labels["severe_pain_threshold"].min()),
                "severe_pain_threshold_max": clean_float(subject_labels["severe_pain_threshold"].max()),
            }
        )
    subjects = pd.DataFrame(subject_rows)
    subjects.to_parquet(subjects_path, compression="zstd", index=False)

    manifest = {
        "dataset_id": "painmonit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_archive": archive.name,
        "nested_archive": "PMCD.zip",
        "source_members": source_rows,
        "rows": total_rows,
        "outputs": {
            "measurement_stream": display_path(stream_path),
            "labels": display_path(labels_path),
            "subjects": display_path(subjects_path),
        },
        "schema_note": "Wide, per-sample clinical PainMonit frame with direct NRS pain rates and categorical labels.",
    }
    write_json(manifest_path, manifest)

    return [
        NormalizedFile("painmonit", "measurement_stream", str(stream_path), total_rows, stream_path.stat().st_size),
        NormalizedFile("painmonit", "labels", str(labels_path), len(labels), labels_path.stat().st_size),
        NormalizedFile("painmonit", "subjects", str(subjects_path), len(subjects), subjects_path.stat().st_size),
    ]


def summarize_parquet(path: Path) -> dict[str, Any]:
    meta = pq.ParquetFile(path).metadata
    return {
        "path": display_path(path),
        "rows": meta.num_rows,
        "row_groups": meta.num_row_groups,
        "bytes": path.stat().st_size,
        "columns": meta.num_columns,
    }


def cmd_inventory(args: argparse.Namespace) -> None:
    payload = inspect_sources()
    if args.output:
        write_json(Path(args.output), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_normalize_rheumapain(args: argparse.Namespace) -> None:
    outputs = normalize_rheumapain(args.frequency, Path(args.output), args.chunksize)
    print(json.dumps([asdict(item) for item in outputs], indent=2, sort_keys=True))


def cmd_normalize_painmonit(args: argparse.Namespace) -> None:
    outputs = normalize_painmonit_clinical(Path(args.output), args.chunksize)
    print(json.dumps([asdict(item) for item in outputs], indent=2, sort_keys=True))


def cmd_summarize(args: argparse.Namespace) -> None:
    root = Path(args.path)
    files = sorted(root.rglob("*.parquet")) if root.is_dir() else [root]
    print(json.dumps([summarize_parquet(path) for path in files], indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize compressed pain datasets into Parquet/ZSTD.")
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("inventory", help="Inspect local source archives.")
    inventory.add_argument("--output", default=None)
    inventory.set_defaults(func=cmd_inventory)

    rheuma = sub.add_parser("normalize-rheumapain", help="Normalize RheumaPain processed CSVs.")
    rheuma.add_argument("--frequency", type=int, default=64, choices=[4, 8, 16, 32, 64])
    rheuma.add_argument("--output", default=str(DEFAULT_OUTPUT))
    rheuma.add_argument("--chunksize", type=int, default=100_000)
    rheuma.set_defaults(func=cmd_normalize_rheumapain)

    painmonit = sub.add_parser("normalize-painmonit", help="Normalize PainMonit PMCD clinical CSVs.")
    painmonit.add_argument("--output", default=str(DEFAULT_OUTPUT))
    painmonit.add_argument("--chunksize", type=int, default=100_000)
    painmonit.set_defaults(func=cmd_normalize_painmonit)

    summarize = sub.add_parser("summarize", help="Summarize normalized Parquet outputs.")
    summarize.add_argument("path", nargs="?", default=str(DEFAULT_OUTPUT))
    summarize.set_defaults(func=cmd_summarize)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
