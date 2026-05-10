#!/usr/bin/env python3
"""Best-effort Core ML conversion for the frozen PainThermometer artifact.

The current frozen serving artifact is a sklearn/joblib bundle trained by
`train_final_model.py`. This script does not retrain or overwrite that model.
It attempts to convert one sklearn pipeline from the bundle into a Core ML
model that Xcode can compile into `PainThermometerPhase3Final.mlmodelc`.

Important: sklearn HistGradientBoosting support depends on the installed
coremltools version. If conversion fails, the correct next step is to train an
export-compatible local-watch artifact with the same input/output contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = ROOT / "inference_flow" / "models" / "pain-thermometer-phase3-final-v1"
DEFAULT_OUTPUT = ROOT / "PainThermometer" / "Models" / "PainThermometerPhase3Final.mlmodel"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert the frozen Phase 3 sklearn artifact to Core ML.")
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR), help="Directory containing model.joblib and manifest.json.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Destination .mlmodel path.")
    parser.add_argument(
        "--model-key",
        default="pain_high_4_plus",
        help="Model inside artifact['models'] to convert first. Default: pain_high_4_plus.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    model_dir = Path(args.model_dir)
    model_path = model_dir / "model.joblib"
    manifest_path = model_dir / "manifest.json"
    output_path = Path(args.output)
    conversion_manifest_path = output_path.with_suffix(".conversion.json")

    try:
        import coremltools as ct
    except ImportError:
        print("coremltools is not installed. Install with: python3 -m pip install coremltools", file=sys.stderr)
        return 2

    manifest = load_json(manifest_path)
    artifact = joblib.load(model_path)
    model_payload = artifact["models"][args.model_key]
    sklearn_pipeline = model_payload["model"]
    columns = list(model_payload["columns"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    conversion_record: dict[str, Any] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_model": str(model_path),
        "source_manifest": str(manifest_path),
        "source_model_alias": manifest.get("model_alias"),
        "source_model_version": manifest.get("model_version"),
        "source_artifact_sha256": manifest.get("artifact_sha256"),
        "model_key": args.model_key,
        "columns": columns,
        "output": str(output_path),
        "status": "started",
    }

    try:
        # The sklearn converter keeps preprocessing inside the Pipeline when the
        # estimator family is supported by coremltools.
        coreml_model = ct.converters.sklearn.convert(
            sklearn_pipeline,
            input_features=columns,
            output_feature_names=["pain_likelihood_0_1", "pain_flag"],
        )
        coreml_model.short_description = "PainThermometer Phase 3 local watch model"
        coreml_model.author = "StartAI"
        coreml_model.license = "Personal PoC"
        coreml_model.version = str(manifest.get("model_version", "unknown"))
        coreml_model.user_defined_metadata["model_alias"] = str(manifest.get("model_alias", "pain-thermometer-phase3-final-v1"))
        coreml_model.user_defined_metadata["model_key"] = args.model_key
        coreml_model.save(str(output_path))
        conversion_record["status"] = "converted"
    except Exception as exc:
        conversion_record["status"] = "failed"
        conversion_record["error_type"] = type(exc).__name__
        conversion_record["error"] = str(exc)
        conversion_record["next_step"] = (
            "Train/export a CoreML-compatible local artifact with the same feature columns and "
            "watch outputs, or switch the final local model family to a coremltools-supported estimator."
        )
        conversion_manifest_path.write_text(json.dumps(conversion_record, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(conversion_record, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    conversion_manifest_path.write_text(json.dumps(conversion_record, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(conversion_record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
