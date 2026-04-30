#!/usr/bin/env python3
"""Create a PostgreSQL-compatible compressed SQL dump for demo platforms.

The dump is streamed from Parquet/CSV inputs into COPY blocks so we do not
materialize an expanded database or large intermediate CSV files on disk.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "_exports" / "pain_demo_postgres.sql.gz"


@dataclass(frozen=True)
class ExportTable:
    table_name: str
    path: Path
    source_format: str = "parquet"
    row_limit: int | None = None


DEFAULT_TABLES: tuple[ExportTable, ...] = (
    ExportTable(
        "rheumapain_measurement_stream",
        ROOT / "_normalized" / "rheumapain" / "frequency_hz=64" / "measurement_stream.parquet",
    ),
    ExportTable(
        "rheumapain_labels",
        ROOT / "_normalized" / "rheumapain" / "frequency_hz=64" / "labels.parquet",
    ),
    ExportTable(
        "rheumapain_subjects",
        ROOT / "_normalized" / "rheumapain" / "frequency_hz=64" / "subjects.parquet",
    ),
    ExportTable(
        "painmonit_clinical_measurement_stream",
        ROOT / "_normalized" / "painmonit" / "clinical" / "measurement_stream.parquet",
    ),
    ExportTable(
        "painmonit_labels",
        ROOT / "_normalized" / "painmonit" / "clinical" / "labels.parquet",
    ),
    ExportTable(
        "painmonit_subjects",
        ROOT / "_normalized" / "painmonit" / "clinical" / "subjects.parquet",
    ),
    ExportTable(
        "pain_windows_1hz_30s",
        ROOT / "_normalized" / "window_features" / "target_hz=1" / "window_features.parquet",
    ),
    ExportTable(
        "pain_windows_all_datasets_1hz_30s",
        ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "window_features.parquet",
    ),
    ExportTable(
        "baseline_state_assignments",
        ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "state_atlas" / "baseline_state_assignments.parquet",
    ),
    ExportTable(
        "baseline_state_cluster_summary",
        ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "state_atlas" / "baseline_state_cluster_summary.csv",
        "csv",
    ),
    ExportTable(
        "baseline_state_bins_by_dataset",
        ROOT / "_normalized" / "window_features_all" / "target_hz=1" / "state_atlas" / "baseline_state_bins_by_dataset.csv",
        "csv",
    ),
    ExportTable(
        "phase2_stress_reference_auxiliary_windows",
        ROOT
        / "pain-thermometer-exploration"
        / "phase_2"
        / "analysis"
        / "outputs"
        / "stress_reference_feeder_rows.parquet",
    ),
    ExportTable(
        "phase2_stress_reference_metrics",
        ROOT
        / "pain-thermometer-exploration"
        / "phase_2"
        / "analysis"
        / "outputs"
        / "stress_reference_metrics.csv",
        "csv",
    ),
    ExportTable(
        "phase2_stress_reference_lifts",
        ROOT
        / "pain-thermometer-exploration"
        / "phase_2"
        / "analysis"
        / "outputs"
        / "stress_reference_lifts.csv",
        "csv",
    ),
    ExportTable(
        "phase2_stress_reference_r_audit",
        ROOT
        / "pain-thermometer-exploration"
        / "phase_2"
        / "analysis"
        / "outputs"
        / "stress_reference_r_audit.csv",
        "csv",
    ),
    ExportTable(
        "phase2_stress_reference_r_metrics",
        ROOT
        / "pain-thermometer-exploration"
        / "phase_2"
        / "analysis"
        / "outputs"
        / "stress_reference_r_metrics.csv",
        "csv",
    ),
    ExportTable(
        "phase2_stress_reference_r_lifts",
        ROOT
        / "pain-thermometer-exploration"
        / "phase_2"
        / "analysis"
        / "outputs"
        / "stress_reference_r_lifts.csv",
        "csv",
    ),
    ExportTable(
        "phase3_windows_1hz_30s",
        ROOT / "_normalized" / "phase3" / "target_hz=1" / "window_features.parquet",
    ),
    ExportTable(
        "phase3_label_family_audit",
        ROOT / "_normalized" / "phase3" / "target_hz=1" / "label_family_audit.csv",
        "csv",
    ),
    ExportTable(
        "phase3_multitask_metrics",
        ROOT / "_normalized" / "phase3" / "target_hz=1" / "baselines" / "phase3_metrics.csv",
        "csv",
    ),
)

SMALL_SAMPLE_ROW_LIMITS: dict[str, int] = {
    "rheumapain_measurement_stream": 50_000,
    "painmonit_clinical_measurement_stream": 50_000,
    "pain_windows_1hz_30s": 20_000,
    "pain_windows_all_datasets_1hz_30s": 40_000,
    "baseline_state_assignments": 40_000,
    "phase2_stress_reference_auxiliary_windows": 50_000,
    "phase3_windows_1hz_30s": 60_000,
    "ssl_direct_contrastive_embeddings": 10_000,
    "ssl_all_contrastive_embeddings": 10_000,
}


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def postgres_type(data_type: pa.DataType) -> str:
    if pa.types.is_boolean(data_type):
        return "boolean"
    if pa.types.is_integer(data_type):
        return "bigint"
    if pa.types.is_floating(data_type) or pa.types.is_decimal(data_type):
        return "double precision"
    if pa.types.is_date(data_type):
        return "date"
    if pa.types.is_timestamp(data_type):
        return "timestamp with time zone" if data_type.tz else "timestamp without time zone"
    return "text"


def parquet_schema(path: Path) -> pa.Schema:
    return pq.ParquetFile(path).schema_arrow


def csv_schema(path: Path) -> pa.Schema:
    frame = pd.read_csv(path, nrows=1000)
    fields = []
    for column in frame.columns:
        if pd.api.types.is_bool_dtype(frame[column]):
            data_type = pa.bool_()
        elif pd.api.types.is_integer_dtype(frame[column]):
            data_type = pa.int64()
        elif pd.api.types.is_float_dtype(frame[column]):
            data_type = pa.float64()
        else:
            data_type = pa.string()
        fields.append(pa.field(str(column), data_type))
    return pa.schema(fields)


def table_schema(table: ExportTable) -> pa.Schema:
    if table.source_format == "parquet":
        return parquet_schema(table.path)
    if table.source_format == "csv":
        return csv_schema(table.path)
    raise ValueError(f"Unsupported source format: {table.source_format}")


def create_table_sql(table_name: str, schema: pa.Schema) -> str:
    columns = []
    for field in schema:
        columns.append(f"  {quote_ident(field.name)} {postgres_type(field.type)}")
    return f"CREATE TABLE {quote_ident(table_name)} (\n" + ",\n".join(columns) + "\n);\n"


def escape_copy_value(value: Any) -> str:
    if value is None or value is pd.NA:
        return r"\N"
    if isinstance(value, float):
        if not math.isfinite(value):
            return r"\N"
        return repr(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return r"\N"
        return value.isoformat()
    try:
        if pd.isna(value):
            return r"\N"
    except (TypeError, ValueError):
        pass
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def write_copy_rows(handle: Any, frame: pd.DataFrame) -> int:
    rows_written = 0
    for row in frame.itertuples(index=False, name=None):
        handle.write("\t".join(escape_copy_value(value) for value in row))
        handle.write("\n")
        rows_written += 1
    return rows_written


def iter_table_batches(table: ExportTable, batch_size: int) -> Iterable[pd.DataFrame]:
    emitted = 0
    if table.source_format == "parquet":
        parquet = pq.ParquetFile(table.path)
        for batch in parquet.iter_batches(batch_size=batch_size):
            frame = batch.to_pandas()
            if table.row_limit is not None:
                remaining = table.row_limit - emitted
                if remaining <= 0:
                    break
                frame = frame.head(remaining)
            emitted += len(frame)
            yield frame
            if table.row_limit is not None and emitted >= table.row_limit:
                break
        return
    if table.source_format == "csv":
        for frame in pd.read_csv(table.path, chunksize=batch_size):
            if table.row_limit is not None:
                remaining = table.row_limit - emitted
                if remaining <= 0:
                    break
                frame = frame.head(remaining)
            emitted += len(frame)
            yield frame
            if table.row_limit is not None and emitted >= table.row_limit:
                break
        return
    raise ValueError(f"Unsupported source format: {table.source_format}")


def available_tables(include_ssl: bool = True) -> list[ExportTable]:
    tables = [table for table in DEFAULT_TABLES if table.path.exists()]
    if include_ssl:
        for prefix, ssl_root in (
            ("ssl_direct", ROOT / "_normalized" / "self_supervised" / "full_1hz_30s"),
            ("ssl_all", ROOT / "_normalized" / "self_supervised" / "all_datasets_1hz_30s"),
        ):
            optional = (
                ExportTable(f"{prefix}_reconstruction_metrics", ssl_root / "reconstruction_metrics.csv", "csv"),
                ExportTable(f"{prefix}_next_window_metrics", ssl_root / "next_window_metrics.csv", "csv"),
                ExportTable(f"{prefix}_sensor_interconnection", ssl_root / "sensor_interconnection.csv", "csv"),
                ExportTable(f"{prefix}_contrastive_embeddings", ssl_root / "contrastive_embeddings.parquet"),
            )
            tables.extend(table for table in optional if table.path.exists())
    return tables


def apply_small_sample_limits(tables: list[ExportTable]) -> list[ExportTable]:
    limited = []
    for table in tables:
        row_limit = SMALL_SAMPLE_ROW_LIMITS.get(table.table_name, table.row_limit)
        limited.append(
            ExportTable(
                table_name=table.table_name,
                path=table.path,
                source_format=table.source_format,
                row_limit=row_limit,
            )
        )
    return limited


def export_postgres_dump(output: Path, tables: list[ExportTable], schema_name: str, batch_size: int) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output": str(output),
        "schema_name": schema_name,
        "tables": [],
    }
    with gzip.open(output, "wt", encoding="utf-8", newline="\n") as handle:
        handle.write("-- PostgreSQL-compatible demo dump for pain datasets.\n")
        handle.write("-- Restore with: gunzip -c pain_demo_postgres.sql.gz | psql \"$DATABASE_URL\"\n")
        handle.write("BEGIN;\n")
        handle.write(f"DROP SCHEMA IF EXISTS {quote_ident(schema_name)} CASCADE;\n")
        handle.write(f"CREATE SCHEMA {quote_ident(schema_name)};\n")
        handle.write(f"SET search_path TO {quote_ident(schema_name)};\n\n")

        for table in tables:
            schema = table_schema(table)
            columns = [field.name for field in schema]
            handle.write(f"-- Source: {table.path}\n")
            handle.write(create_table_sql(table.table_name, schema))
            column_sql = ", ".join(quote_ident(column) for column in columns)
            handle.write(
                f"COPY {quote_ident(table.table_name)} ({column_sql}) "
                "FROM stdin WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N');\n"
            )
            rows = 0
            for frame in iter_table_batches(table, batch_size=batch_size):
                frame = frame[[column for column in columns if column in frame.columns]]
                rows += write_copy_rows(handle, frame)
            handle.write("\\.\n\n")
            manifest["tables"].append(
                {
                    **asdict(table),
                    "path": str(table.path),
                    "columns": len(columns),
                    "rows": rows,
                }
            )
            print(f"exported {table.table_name}: {rows} rows")

        handle.write("COMMIT;\n")

    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest["compressed_bytes"] = output.stat().st_size
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a compressed PostgreSQL-compatible demo SQL dump.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--schema-name", default="pain_demo")
    parser.add_argument("--batch-size", type=int, default=50000)
    parser.add_argument("--no-ssl", action="store_true", help="Do not include available self-supervised outputs.")
    parser.add_argument("--small-sample", action="store_true", help="Apply row limits for a compact demo/training dump.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    tables = available_tables(include_ssl=not args.no_ssl)
    if args.small_sample:
        tables = apply_small_sample_limits(tables)
    if not tables:
        raise SystemExit("No exportable normalized tables found.")
    manifest = export_postgres_dump(
        output=Path(args.output),
        tables=tables,
        schema_name=args.schema_name,
        batch_size=args.batch_size,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
