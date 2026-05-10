# Core ML Model API

Status: pending Core ML artifact; conversion attempted and blocked by sklearn/CoreMLTools compatibility

## Artifact

Frozen server artifact:

```text
inference_flow/models/pain-thermometer-phase3-final-v1/model.joblib
```

Manifest:

```text
inference_flow/models/pain-thermometer-phase3-final-v1/manifest.json
```

Model alias:

```text
pain-thermometer-phase3-final-v1
```

Model version:

```text
phase3_fast_hgb_20260429T1851Z
```

Converted watch artifact target:

```text
PainThermometerPhase3Final.mlmodel
```

Xcode compiles it into the app bundle as:

```text
PainThermometerPhase3Final.mlmodelc
```

Expected repo path after conversion:

```text
PainThermometer/Models/PainThermometerPhase3Final.mlmodel
```

There is no committed `.mlmodel` or `.mlmodelc` yet.

Current conversion record:

```text
PainThermometer/Models/PainThermometerPhase3Final.conversion.json
```

## Conversion

Use:

```sh
python3 -m pip install -r inference_flow/requirements-coreml.txt
python3 inference_flow/convert_to_coreml.py
```

The script writes a sidecar conversion record:

```text
PainThermometer/Models/PainThermometerPhase3Final.conversion.json
```

The current frozen artifact is a sklearn `HistGradientBoosting` pipeline bundle. If `coremltools` cannot convert that estimator family directly, the script fails without overwriting the joblib artifact and records the failure plus next step in the sidecar JSON.

If direct conversion fails, train a watch-local CoreML-compatible artifact with the same feature names and output field names below. Do not replace the frozen server artifact just to satisfy CoreML export.

Current result:

```text
coremltools 9.0 installed in .venv-coreml
direct conversion failed
reason: coremltools disables sklearn conversion for scikit-learn 1.6.1, and the frozen joblib was built with sklearn 1.6.1
secondary error: name '_tree' is not defined
```

Next practical path: train a small watch-local CoreML-compatible model from the same Phase 3 window table and same feature contract, likely using a tree/logistic model family supported by CoreMLTools, while keeping the frozen server `model.joblib` unchanged.

## Access

Use the existing watch scorer:

```swift
let result = await localScorer.score(featureWindow, enabled: true)
```

Internally it loads:

```swift
Bundle.main.url(forResource: "PainThermometerPhase3Final", withExtension: "mlmodelc")
```

## Input

One call scores one trailing 30 second `FeatureWindow`.

Pass a flat `[String: Double]` dictionary whose keys exactly match the Core ML input feature names. Missing sensor blocks must be zero-filled:

```text
<sensor>__present = 0
<sensor>__valid_count = 0
<sensor>__valid_frac = 0
all other missing numeric features = 0
```

Primary watch blocks:

```text
hr, acc, gyro, temperature, spo2, ibi, ecg
```

## Output

The watch-local model should return these `Double` outputs:

```text
pain_likelihood_0_1
pain_score_0_100
pain_flag
confidence_0_1
quality_0_1
stress_likelihood_0_1
baseline_departure_0_1
```

Minimum viable local model output is:

```text
pain_likelihood_0_1
pain_flag
```

When only the minimum output exists, the watch should treat missing optional outputs as unavailable and continue using server scores when connected.

Fill a live 10-box pain block when:

```text
pain_likelihood_0_1 >= 0.65
confidence_0_1 >= 0.50
quality_0_1 >= 0.60
```

Pain detected mode activates when 7 of the last 10 live boxes are filled. Server-returned scores and local Core ML scores feed the same rolling display state.

This is a pain-likelihood signal, not a diagnosis.
