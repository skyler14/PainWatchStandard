"""PainMonit parsing helpers.

Full normalization stays compressed-first. These helpers are intentionally
small and testable because PainMonit has several format traps: nested zips,
semicolon CSV, decimal comma, and threshold sidecars.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


def normalize_column(name: str) -> str:
    text = name.strip().replace("\ufeff", "")
    text = re.sub(r"[^0-9A-Za-z]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_").lower()


def parse_painmonit_session(member: str) -> dict[str, Any]:
    match = re.search(r"/?(?P<session>P(?P<subject>\d+)_(?P<trial>\d+))/(?P=session)\.csv$", member)
    if not match:
        raise ValueError(f"Could not parse PainMonit session path: {member}")
    return {
        "subject_id": f"p{match.group('subject')}",
        "session_id": match.group("session").lower(),
        "session_number": int(match.group("trial")),
    }


def clean_numeric(series: pd.Series) -> pd.Series:
    if not pd.api.types.is_numeric_dtype(series):
        series = series.astype("string").str.replace(",", ".", regex=False)
    return pd.to_numeric(series, errors="coerce")
