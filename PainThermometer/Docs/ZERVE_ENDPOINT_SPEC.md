# Zerve Endpoint Spec

Status: app contract scaffold
Date: 2026-04-29

## Connect

```text
POST /v1/connect
```

The app sends `device_id`, supported sensor blocks, and display requirements. The server may return endpoint paths, activation settings, and dropout signals.

Pain detected mode is a rolling display state: 7 positive score windows out of the last 10 activates the mode.

## Live Feed

```text
POST /v1/live-samples
```

The app sends batches of `sample` rows while recording when live upload is enabled. The server can return `scores` and `dropout_signals` in the same response.

## Historical Upload

```text
POST /v1/runs/import-jsonl
```

The app sends locally stored JSONL run files. Historical responses may also include `scores` and `dropout_signals`.

## Score Response Shape

```json
{
  "scores": [
    {
      "score_name": "pain",
      "pain_likelihood_0_1": 0.72,
      "pain_score_0_100": 68.0,
      "pain_detected": true,
      "confidence_0_1": 0.62,
      "quality_0_1": 0.84,
      "stress_likelihood_0_1": 0.44,
      "baseline_departure_0_1": 0.31,
      "window_start_utc": "2026-04-29T20:15:00Z",
      "window_end_utc": "2026-04-29T20:15:30Z",
      "model_version": "server-model-v1",
      "dropout_signals": []
    }
  ],
  "dropout_signals": [
    {
      "sensor": "spo2",
      "present": false,
      "valid_frac": 0.0,
      "reason": "no_samples_in_window",
      "severity": "missing"
    }
  ]
}
```

The app also has a local Core ML toggle. When `PainThermometerPhase3Final.mlmodelc` is bundled, local scoring uses the same output field names and feeds the same 7-of-10 display state.
