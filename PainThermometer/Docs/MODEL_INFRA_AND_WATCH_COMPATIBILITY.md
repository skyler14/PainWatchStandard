# Model Infrastructure And Watch Compatibility

Status: current architecture spec
Date: 2026-04-30

## Current Model Stack

PainThermometer currently has one frozen server-side model artifact and one watch-side local model scaffold.

The frozen server artifact is:

```text
inference_flow/models/pain-thermometer-phase3-final-v1/model.joblib
```

The manifest is:

```text
inference_flow/models/pain-thermometer-phase3-final-v1/manifest.json
```

Current identity:

```text
model_alias = pain-thermometer-phase3-final-v1
model_version = phase3_fast_hgb_20260429T1851Z
artifact_sha256 = 084f00fb024ad871d646ea929b9b93ac166ca6299c446adfea6d710f6a180cf6
```

The source table for this model is:

```text
_normalized/phase3/target_hz=1/window_features.parquet
```

That table contains 1 Hz trailing feature windows. One row represents one prediction anchor over a trailing 30 second physiology window.

## Frozen Server Artifact Shape

`model.joblib` is a Python `joblib` bundle. It contains:

```text
config
trained_at_utc
input_path
input_sha256
models
routing
```

The `models` map contains four sklearn pipelines:

```text
pain_high_4_plus        classifier, direct pain >= 4 NRS
pain_nrs_regression    regressor, direct pain 0-10 NRS
stress_binary          auxiliary stress classifier
baseline_state_binary  auxiliary baseline-like state classifier
```

The promoted pain feature set is:

```text
apple_watch_like
```

The current model family is:

```text
sklearn HistGradientBoosting pipelines with preprocessing
```

This artifact is the canonical server artifact. Dashboard jobs and local watch conversion attempts must not overwrite it.

## Server Inference Contract

The current server scoring helper is:

```text
inference_flow/inference.py
```

Primary entrypoint:

```python
score_feature_row(row, model_path=DEFAULT_MODEL, prior_scores=None)
```

Input is already-windowed Phase 3 feature JSON. Raw watch samples must first be transformed into the same feature-window shape.

Minimum required row context:

```text
run_id
device_id
anchor_time_utc
all model feature columns
```

Missing features are tolerated by the sklearn preprocessing pipeline, but the preferred serving behavior is to include explicit zero/presence values:

```text
<sensor>__present = 0
<sensor>__valid_count = 0
<sensor>__valid_frac = 0
missing numeric summaries = 0 or null before preprocessing
```

## Server Output Shape

`score_feature_row` returns:

```json
{
  "schema_version": 1,
  "score_available": true,
  "latest_score": {
    "schema_version": 1,
    "run_id": "uuid",
    "device_id": "uuid",
    "model_alias": "pain-thermometer-phase3-final-v1",
    "model_version": "phase3_fast_hgb_20260429T1851Z",
    "model_family": "hist_gradient_boosting_multitask_windows",
    "feature_set": "apple_watch_like",
    "anchor_time_utc": "ISO-8601 UTC",
    "window_seconds": 30,
    "anchor_cadence_hz": 1,
    "pain_likelihood_0_1": 0.72,
    "pain_score_0_100": 68,
    "pain_flag": true,
    "flag_threshold": 0.65,
    "confidence_0_1": 0.62,
    "quality_0_1": 0.84,
    "stress_likelihood_0_1": 0.44,
    "baseline_departure_0_1": 0.31,
    "sensors_used": ["hr", "acc"],
    "missing_sensor_blocks": ["spo2", "temperature"],
    "pain_blocks_10": [],
    "contributory_factors": [],
    "display": {
      "primary_text": "Pain-like pattern",
      "secondary_text": "Moderate confidence",
      "color_hint": "amber",
      "filled_block_count": 7
    }
  }
}
```

The watch and dashboard should treat `pain_likelihood_0_1` as the primary continuous signal and `pain_flag` as a display-level sustained-pattern flag, not as a clinical diagnosis.

## Watch Endpoint Contract

The endpoint-facing app spec is:

```text
PainThermometer/Docs/ENDPOINT_SPEC.md
```

The watch supports:

```text
POST /v1/connect
POST /v1/live-samples
POST /v1/runs/import-jsonl
```

Live and historical responses may return:

```text
scores
dropout_signals
```

Pain detected mode is a rolling display state:

```text
7 positive score windows out of the last 10 windows
```

## Local Apple Watch Core ML Scaffold

The watch app has a local Core ML loader:

```text
PainThermometer/PainThermometerWatchApp/LocalCoreMLPainScorer.swift
```

It looks for:

```text
Bundle.main.url(forResource: "PainThermometerPhase3Final", withExtension: "mlmodelc")
```

Expected source file path before Xcode compilation:

```text
PainThermometer/Models/PainThermometerPhase3Final.mlmodel
```

Current status:

```text
No .mlmodel exists yet.
No .mlmodelc exists yet.
```

The attempted conversion record is:

```text
PainThermometer/Models/PainThermometerPhase3Final.conversion.json
```

Conversion script:

```text
inference_flow/convert_to_coreml.py
```

Conversion dependencies:

```text
inference_flow/requirements-coreml.txt
```

Current direct-conversion result:

```text
coremltools 9.0 installed in .venv-coreml
direct sklearn conversion failed
reason: coremltools disables sklearn conversion for scikit-learn 1.6.1
secondary error: name '_tree' is not defined
```

The failure is expected for this artifact family. The server model should remain unchanged. The practical Core ML path is to train a separate watch-local model with the same input/output contract and a Core ML compatible estimator.

## ONNX Status

There is currently no ONNX artifact.

Recommended target path if added:

```text
PainThermometer/Models/PainThermometerPhase3Final.onnx
```

Current server model may be partially exportable through `skl2onnx`, but this has not been tested. The same risk applies as Core ML: the sklearn pipeline and `HistGradientBoosting` family may require a simpler export-compatible local model.

ONNX should be treated as a cross-platform phone/server/runtime artifact, not an Apple Watch local runtime artifact.

## Recommended Model Targets

### Server

Use the current `joblib` artifact.

```text
format = joblib
runtime = Python + sklearn
deployment = server
status = current best model
```

### Apple Watch Local

Train a lightweight separate model.

```text
format = Core ML .mlmodel
runtime = Core ML on watchOS
deployment = watch app bundle
status = needed
```

Preferred first local model family:

```text
logistic regression or small tree ensemble known to convert through coremltools
```

Minimum outputs:

```text
pain_likelihood_0_1
pain_flag
```

Preferred outputs:

```text
pain_likelihood_0_1
pain_score_0_100
pain_flag
confidence_0_1
quality_0_1
stress_likelihood_0_1
baseline_departure_0_1
```

### Android/Wear OS Local

If this project expands beyond Apple Watch, train/export a TFLite or ONNX-compatible local model rather than trying to reuse the Core ML artifact.

```text
format = .tflite preferred, .onnx possible
runtime = TensorFlow Lite or ONNX Runtime Mobile
deployment = Wear OS app module
status = future
```

## Watch Platform Compatibility Matrix

| Brand/ecosystem | Watch OS family | Core ML | ONNX Runtime | TensorFlow Lite | Practical PainThermometer path |
| --- | --- | --- | --- | --- | --- |
| Apple Watch | watchOS | Supported through Core ML model format on watchOS. Current app scaffold is built for this. | Not suitable for watch-local use. ONNX Runtime iOS docs explicitly exclude watchOS builds. | Not the native path; possible only with custom unsupported porting effort. | Core ML local model plus server fallback. |
| iPhone companion | iOS | Supported. | Supported by ONNX Runtime iOS builds. | Supported by TensorFlow Lite iOS APIs. | Good bridge target for heavier local inference if watch power/runtime is too constrained. |
| Google Pixel Watch | Wear OS / Android | Not supported. | Possible through Android ONNX Runtime Mobile in principle, but watch packaging/performance must be validated. | Supported through Android TensorFlow Lite APIs; best Android watch path. | TFLite local model or server/phone bridge. |
| Samsung Galaxy Watch 4+ | Wear OS / One UI Watch | Not supported. | Same as Wear OS: possible Android runtime path, not guaranteed watch-optimized. | Same as Wear OS: preferred local Android watch path. | TFLite local model or server/phone bridge. |
| Samsung Galaxy Watch legacy | Tizen wearable | Not supported. | No normal ONNX path documented for wearable apps. | Tizen native ML APIs support TensorFlow Lite on Tizen wearable versions. | TFLite possible only for legacy native Tizen targets; not a priority. |
| Garmin | Connect IQ / Monkey C | Not supported. | Not supported as a documented Connect IQ runtime. | Not supported as a documented Connect IQ runtime. | No local model. Send features/samples to phone/server; optionally implement simple threshold rules in Monkey C. |
| Fitbit legacy smartwatches | Fitbit OS SDK / JavaScript | Not supported. | Not supported as a documented Fitbit watch runtime. | Not supported as a documented Fitbit watch runtime. | No local model. Use phone/cloud API flow if available. |
| Fitbit/Pixel current ecosystem | Wear OS for Pixel Watch; Fitbit service layer | Not a Fitbit SDK path. Pixel Watch follows Wear OS. | Same as Wear OS for native Pixel Watch apps. | Same as Wear OS for native Pixel Watch apps. | Treat as Wear OS for watch-local inference; Fitbit cloud APIs are historical/data integration only. |
| Huawei Watch | HarmonyOS / LiteOS variants | Not supported. | No portable public watch-runtime path assumed. | Possible only if a native Huawei/HarmonyOS ML runtime is available for the target device and app distribution path. | Server/phone bridge unless a target-specific Huawei ML runtime is selected later. |
| Amazfit / Zepp | Zepp OS Mini Program JavaScript runtime | Not supported. | Not supported as a documented Zepp Mini Program runtime. | Not supported as a documented Zepp Mini Program runtime. | No local model. Server/phone bridge or simple JS threshold rules only. |

## Compatibility Notes

### Apple

Core ML is the correct local model format for Apple Watch. Apple’s Core ML format has watchOS availability, and Core ML is Apple’s on-device inference framework. ONNX Runtime supports iOS builds, but its iOS build documentation states that watchOS is not supported. Therefore:

```text
Apple Watch local = Core ML
iPhone bridge = Core ML or ONNX or TFLite
```

### Wear OS

Wear OS apps are Android apps for watches. Google’s Health Services API is the sensor/exercise path, and TensorFlow Lite is the most natural local inference runtime for Android. ONNX Runtime Mobile supports Android generally, but a watch-specific integration still needs packaging, ABI, battery, and memory validation.

```text
Wear OS local preferred = TFLite
Wear OS local possible = ONNX Runtime Mobile, validation required
Wear OS unsupported = Core ML
```

### Samsung

Modern Samsung Galaxy Watch devices use Wear OS, so they follow the Wear OS line above. Older Tizen-based watches are a separate legacy target. Tizen native ML documentation includes TensorFlow Lite support for wearable native apps, but that is not relevant to the Apple Watch PoC.

### Garmin

Garmin Connect IQ apps use Monkey C and Connect IQ APIs. There is no documented Core ML, ONNX Runtime, or TensorFlow Lite runtime for Connect IQ watch apps. Garmin is not a viable local inference target for this model unless the model is reduced to hand-coded rules or inference is delegated to a phone/server.

### Fitbit

Fitbit’s third-party model is API/SDK oriented and does not provide a documented on-watch Core ML, ONNX, or TensorFlow Lite runtime for this use case. Treat Fitbit data as an ingestion source, not as a local inference target. Pixel Watch devices should be handled as Wear OS devices.

### Huawei And Amazfit

Huawei HarmonyOS/LiteOS and Zepp OS are not portable targets for the current model artifact. Zepp OS Mini Programs use a JavaScript runtime. Without a documented ML runtime for the exact device family, the safe assumption is server/phone inference only.

## Deployment Decision

Current recommended deployment:

```text
server = current joblib model
Apple Watch local fallback = train a separate Core ML model
Wear OS future fallback = train/export a TFLite model
ONNX = useful for phone/server/Android experiments, not Apple Watch
Garmin/Fitbit/Zepp/Huawei = server/phone bridge unless target-specific ML runtime is proven
```

## Sources

- Apple Core ML documentation: `https://developer.apple.com/documentation/CoreML`
- Apple Core ML format availability: `https://apple.github.io/coremltools/mlmodel/Format/Model.html`
- ONNX Runtime compatibility: `https://onnxruntime.ai/docs/reference/compatibility.html`
- ONNX Runtime iOS build documentation: `https://onnxruntime.ai/docs/build/ios.html`
- ONNX Runtime Mobile: `https://onnxruntime.ai/docs/get-started/with-mobile.html`
- Android Wear OS Health Services: `https://developer.android.com/training/wearables/health-services`
- Android TensorFlow Lite: `https://android.googlesource.com/platform/external/tensorflow/+/main/tensorflow/lite/g3doc/android/index.md`
- Tizen Machine Learning: `https://developer.tizen.org/machine-learning/`
- Tizen Machine Learning Service: `https://docs.tizen.org/application/native/guides/machine-learning/machine-learning-service/`
- Garmin Connect IQ overview: `https://developer.garmin.com/connect-iq/overview/`
- Garmin Monkey C: `https://developer.garmin.com/connect-iq/monkey-c/`
- Fitbit developer/API entrypoint: `https://www.fitbit.com/dev`
- Zepp OS developer introduction: `https://docs.zepp.com/docs/guides/framework/device/intro/`
