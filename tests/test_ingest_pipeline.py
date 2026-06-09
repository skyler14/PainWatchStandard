from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from painwatchstandard.ingest import (
    inventory_sources,
    normalize_catsa,
    normalize_silver,
    normalize_watch_pain_archive,
)


def _write_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, text in members.items():
            zf.writestr(name, text)


def test_inventory_sources_counts_zip_members(tmp_path: Path):
    _write_zip(tmp_path / "sample.zip", {"a.csv": "x\n1\n", "folder/b.txt": "ok\n"})

    payload = inventory_sources(tmp_path)

    assert payload["sample.zip"]["members"] == 2
    assert payload["sample.zip"]["extensions"][".csv"] == 1


def test_watch_pain_archive_normalizes_direct_pain_rows(tmp_path: Path):
    member = "PhysioPain Dataset/Multimodal Pain Dataset/PROCESSED WATCH DATA/combined/combined_all_data/all_watch_data_64hz.csv"
    _write_zip(
        tmp_path / "PhysioPain Dataset.zip",
        {
            member: (
                "bvp,eda,x,y,z,temperature,pain_scale,pain_type,person_id\n"
                "1,0.1,0,1,2,33,3,back_pain,S001\n"
                "2,0.2,1,2,3,34,3,back_pain,S001\n"
            )
        },
    )

    outputs = normalize_watch_pain_archive(tmp_path, tmp_path / "out", "PhysioPain Dataset.zip", "physiopain_watch", chunksize=10)
    stream_path = Path(next(item.path for item in outputs if item.output_kind == "measurement_stream"))
    frame = pd.read_parquet(stream_path)

    assert frame["dataset_id"].unique().tolist() == ["physiopain_watch"]
    assert frame["label_family"].unique().tolist() == ["direct_pain"]
    assert frame["sample_offset_s"].tolist() == [0.0, 1.0 / 64.0]


def test_silver_normalizer_keeps_watch_context_separate_from_pain_truth(tmp_path: Path):
    _write_zip(
        tmp_path / "SILVER-Pain Dataset.zip",
        {
            "SILVER-Pain Dataset/data/older_adults/older_adults.csv": (
                "timestamp_ns,datetime_utc,segment,bvp,eda,temperature,hr,section,PainLevel,Trial,subject\n"
                "1000000000,t,0,1,0.1,33,80,0,4,1,001\n"
            ),
            "SILVER-Pain Dataset/data/young_adults/young_adults.csv": (
                "timestamp_ns,datetime_utc,segment,section,bvp,eda,temperature,hr,PainLevel,Trial,subject\n"
                "2000000000,t,0,0,2,0.2,34,90,0,1,101\n"
            ),
        },
    )

    outputs = normalize_silver(tmp_path, tmp_path / "out", chunksize=10)
    stream_path = Path(next(item.path for item in outputs if item.output_kind == "measurement_stream"))
    frame = pd.read_parquet(stream_path)

    assert set(frame["cohort"]) == {"older_adults", "young_adults"}
    assert frame.loc[frame["subject_id"].eq("older_adults_001"), "label_family"].iloc[0] == "direct_pain"
    assert frame.loc[frame["subject_id"].eq("young_adults_101"), "target_pain_bin"].iloc[0] == 0


def test_catsa_context_normalizer_does_not_create_pain_labels(tmp_path: Path):
    _write_zip(
        tmp_path / "CATSA.zip",
        {
            "CATSA/Sub1/Baseline/BVP.csv": "0\n1\n1\n2\n3\n",
            "CATSA/Sub1/Baseline/EDA.csv": "0\n1\n0.1\n0.2\n0.3\n",
            "CATSA/Sub1/Baseline/TEMP.csv": "0\n1\n33\n33.1\n33.2\n",
            "CATSA/Sub1/Baseline/HR.csv": "0\n1\n70\n71\n72\n",
            "CATSA/Sub1/Baseline/ACC.csv": "0\n1\n0,0,1\n0,1,1\n1,1,1\n",
        },
    )

    outputs = normalize_catsa(tmp_path, tmp_path / "out")
    stream_path = Path(next(item.path for item in outputs if item.output_kind == "measurement_stream"))
    frame = pd.read_parquet(stream_path)

    assert frame["label_family"].unique().tolist() == ["baseline_context"]
    assert frame["target_pain_nrs_0_10"].isna().all()
