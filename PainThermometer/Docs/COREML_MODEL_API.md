# Core ML Model API

Status: pending Core ML artifact

## Artifact

Bundle the converted model in the watch target as:

```text
PainThermometerPhase3Final.mlmodel
```

Xcode compiles it into the app bundle as:

```text
PainThermometerPhase3Final.mlmodelc
```

Model alias:

```text
pain-thermometer-phase3-final-v1
```

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

The model must return these `Double` outputs:

```text
pain_likelihood_0_1
pain_score_0_100
pain_flag
confidence_0_1
quality_0_1
stress_likelihood_0_1
baseline_departure_0_1
```

Fill a live 10-box pain block when:

```text
pain_likelihood_0_1 >= 0.65
confidence_0_1 >= 0.50
quality_0_1 >= 0.60
```

Pain detected mode activates when 7 of the last 10 live boxes are filled. Server-returned scores and local Core ML scores feed the same rolling display state.

This is a pain-likelihood signal, not a diagnosis.
