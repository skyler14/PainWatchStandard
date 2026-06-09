from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from painwatchstandard.build_windows import build_unified_window_table
from painwatchstandard.windowing import WindowConfig


def test_build_unified_window_table_from_normalized_streams(tmp_path: Path):
    stream_dir = tmp_path / "normalized" / "painmonit" / "clinical"
    stream_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "dataset_id": ["painmonit"] * 35,
            "subject_id": ["p01"] * 35,
            "session_id": ["p01_1"] * 35,
            "condition": ["clinical"] * 35,
            "label_family": ["direct_pain"] * 35,
            "sample_offset_s": np.arange(35, dtype=float),
            "eda": np.arange(35, dtype=float),
            "pain_intensity": [np.nan] * 30 + [5.0] * 5,
        }
    ).to_parquet(stream_dir / "measurement_stream.parquet", index=False)

    output = build_unified_window_table(
        tmp_path / "normalized",
        tmp_path / "windows" / "window_features.parquet",
        WindowConfig(target_hz=1.0, window_seconds=30.0),
    )
    frame = pd.read_parquet(output.path)

    assert output.rows == 5
    assert frame["dataset_id"].unique().tolist() == ["painmonit"]
    assert frame["label_family"].unique().tolist() == ["direct_pain"]
    assert frame.iloc[0]["target_pain_nrs_0_10"] == 5.0
