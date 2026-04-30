#!/usr/bin/env python3
"""Train and freeze the Phase 3 dashboard inference artifact.

This script intentionally trains small, inspectable sklearn pipelines. The
validation numbers for promotion live in the Phase 3 baseline report; this
script builds the frozen serving artifact from the current Phase 3 feature
table after that validation pass has been reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PHASE3_ANALYSIS = ROOT / "pain-thermometer-exploration" / "phase_3" / "analysis"
sys.path.insert(0, str(PHASE3_ANALYSIS))

from phase3_multitask_baseline import (  # noqa: E402
    Phase3Config,
    clean_feature_frame,
    feature_columns,
    make_classifier,
    make_preprocessor,
    make_regressor,
    task_weights,
)


DEFAULT_INPUT = ROOT / "_normalized" / "phase3" / "target_hz=1" / "window_features.parquet"
DEFAULT_OUTPUT = ROOT / "zerve_flow" / "models" / "pain-thermometer-phase3-final-v1"


@dataclass(frozen=True)
class FinalModelConfig:
    model_alias: str = "pain-thermometer-phase3-final-v1"
    model_version: str = "phase3_fast_hgb_20260429T1851Z"
    pain_feature_set: str = "apple_watch_like"
    stress_feature_set: str = "autonomic_core"
    baseline_feature_set: str = "apple_watch_like"
    high_pain_threshold_nrs: float = 4.0
    flag_threshold: float = 0.65
    window_seconds: int = 30
    anchor_cadence_hz: int = 1
    random_state: int = 42
    model_iterations: int = 80


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pipeline_for_classifier(frame: pd.DataFrame, columns: list[str], config: Phase3Config):
    from sklearn.pipeline import Pipeline

    return Pipeline([("prep", make_preprocessor(clean_feature_frame(frame, columns), columns)), ("model", make_classifier(config))])


def pipeline_for_regressor(frame: pd.DataFrame, columns: list[str], config: Phase3Config):
    from sklearn.pipeline import Pipeline

    return Pipeline([("prep", make_preprocessor(clean_feature_frame(frame, columns), columns)), ("model", make_regressor(config))])


def train_classifier(frame: pd.DataFrame, feature_set: str, target: str, config: Phase3Config, confidence_weighted: bool = False) -> dict[str, Any]:
    columns = feature_columns(frame, feature_set)
    x_train = clean_feature_frame(frame, columns)
    model = pipeline_for_classifier(frame, columns, config)
    model.fit(x_train, frame[target].astype(int), model__sample_weight=task_weights(frame, target, confidence_weighted))
    return {
        "model": model,
        "feature_set": feature_set,
        "target": target,
        "columns": columns,
        "rows": int(len(frame)),
        "positive_rate": float(frame[target].mean()),
    }


def train_regressor(frame: pd.DataFrame, feature_set: str, target: str, config: Phase3Config) -> dict[str, Any]:
    columns = feature_columns(frame, feature_set)
    x_train = clean_feature_frame(frame, columns)
    model = pipeline_for_regressor(frame, columns, config)
    model.fit(x_train, frame[target].astype(float), model__sample_weight=task_weights(frame, target, confidence_weighted=True))
    return {
        "model": model,
        "feature_set": feature_set,
        "target": target,
        "columns": columns,
        "rows": int(len(frame)),
        "target_mean": float(frame[target].mean()),
    }


def build_artifact(input_path: Path, output_dir: Path, final_config: FinalModelConfig) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(input_path).reset_index(drop=True)
    model_config = Phase3Config(
        input_path=str(input_path),
        output_dir=str(output_dir),
        random_state=final_config.random_state,
        model_iterations=final_config.model_iterations,
    )

    direct = frame.loc[frame["label_family"].eq("direct_pain") & frame["target_pain_nrs_0_10"].notna()].copy()
    direct["pain_high_4_plus"] = (direct["target_pain_nrs_0_10"].astype(float) >= final_config.high_pain_threshold_nrs).astype(int)

    stress = frame.loc[pd.to_numeric(frame["target_stress_binary"], errors="coerce").notna()].copy()
    stress["target_stress_binary"] = stress["target_stress_binary"].astype(int)

    baseline = frame.loc[pd.to_numeric(frame["target_baseline_binary"], errors="coerce").notna()].copy()
    baseline["target_baseline_binary"] = baseline["target_baseline_binary"].astype(int)

    artifact = {
        "config": asdict(final_config),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "input_sha256": sha256_file(input_path),
        "models": {
            "pain_high_4_plus": train_classifier(direct, final_config.pain_feature_set, "pain_high_4_plus", model_config, True),
            "pain_nrs_regression": train_regressor(direct, final_config.pain_feature_set, "target_pain_nrs_0_10", model_config),
            "stress_binary": train_classifier(stress, final_config.stress_feature_set, "target_stress_binary", model_config),
            "baseline_state_binary": train_classifier(baseline, final_config.baseline_feature_set, "target_baseline_binary", model_config),
        },
        "routing": {
            "pain_supervision": "label_family=direct_pain and non-null target_pain_nrs_0_10",
            "auxiliary_supervision": "stress/baseline rows train auxiliary outputs only",
            "serving_endpoint": "POST /v1/inference/pain-thermometer-phase3-final-v1/live-samples",
        },
    }

    model_path = output_dir / "model.joblib"
    joblib.dump(artifact, model_path, compress=3)
    manifest = {
        "model_alias": final_config.model_alias,
        "model_version": final_config.model_version,
        "created_at_utc": artifact["trained_at_utc"],
        "artifact_path": str(model_path),
        "artifact_sha256": sha256_file(model_path),
        "artifact_bytes": model_path.stat().st_size,
        "input_path": str(input_path),
        "input_sha256": artifact["input_sha256"],
        "models": {
            name: {key: value for key, value in payload.items() if key != "model"}
            for name, payload in artifact["models"].items()
        },
        "validation_report": "_normalized/phase3/target_hz=1/baselines/PHASE_3_BASELINE_REPORT.md",
        "validation_metrics": "_normalized/phase3/target_hz=1/baselines/phase3_metrics.csv",
        "promotion_note": "Frozen dashboard inference artifact. Dashboard training jobs must create candidate aliases and cannot overwrite this alias.",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the frozen Phase 3 Zerve inference artifact.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--model-iterations", type=int, default=80)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = FinalModelConfig(model_iterations=args.model_iterations)
    manifest = build_artifact(Path(args.input), Path(args.output), config)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
