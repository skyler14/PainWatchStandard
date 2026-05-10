# Pain Trigger Signal and Dialogue Spec

## Goal

When the watch enters pain activation mode, the app sends the current score
context and display buffer to the backend. The backend can either run inference
itself or use the watch/CoreML score as the trigger, then starts an approachable
conversation that combines open testimony with structured Geriatric Pain Measure
fields.

## Trigger Modes

### Watch/CoreML Trigger

The watch computes rolling features locally and, when a bundled Core ML model is
available, emits `ScoreResult` fields:

```text
pain_likelihood_0_1
pain_score_0_100
pain_detected
confidence_0_1
quality_0_1
stress_likelihood_0_1
baseline_departure_0_1
```

Pain activation is still the display rule: 7 positive score windows out of the
last 10. On activation, the watch sends `/v1/pain-trigger` with the latest score
and the 100-measurement display buffer. The full run archive remains local until
normal historical upload.

### Backend-Hosted Inference

If Core ML is unavailable or disabled, the watch can send the same trigger
payload with bulk buffered data and any endpoint-returned scores. The backend
may run the Python model against the buffer or request the full run archive. In
this mode, the MCP server can host both inference and questionnaire tools:

- score the buffered signal
- revise the score as testimony adds context
- return the next question based on missing or low-certainty fields
- package structured answers as transport records, including FHIR-compatible
  Observation/QuestionnaireResponse mappings when available

## Pain Trigger Payload

```json
{
  "schema_version": 1,
  "source": "PainThermometerWatchApp",
  "run_id": "6F02A9DB-9E83-47A2-9486-0660FB83E537",
  "device_id": "9F8C667D-9057-4890-A174-88187B866308",
  "triggered_at": "2026-05-10T08:00:00Z",
  "activation_positive_count": 7,
  "activation_window_count": 10,
  "score": {
    "score_name": "local_coreml",
    "pain_likelihood_0_1": 0.78,
    "pain_score_0_100": 78,
    "confidence_0_1": 0.71,
    "quality_0_1": 0.82
  },
  "buffer": [],
  "suggested_prompt": "What happened around when the pain started?"
}
```

## GPM Dialogue

The local reference survey is `/Users/skyler/Downloads/Geriatric Pain Measure
GPM.pdf`. It has 22 yes/no items plus two 0-10 severity items. The total is
0-42, and adjusted score is `total * 2.38` on a 0-100 scale.

The MCP server should first ask an open question, then infer which fields are
answered, missing, or low certainty. Follow-up questions should be simple and
natural, not form-like:

- location and quality
- activity or movement context
- pain today, 0-10
- average pain in the last week, 0-10
- sleep, fatigue, help needed, mood, walking/stairs, social/activity impact

Each answer can update:

- `gpm_total_0_42`
- `gpm_adjusted_0_100`
- `gpm_band`
- qualitative summary
- per-field certainty
- revised sensor/model interpretation

Some fields should stay binary yes/no when the natural response is uncertain.
Score fields can be revised as testimony accumulates, but raw watch samples and
original score outputs must remain immutable.

## Voice

The app now has TTS scaffolding for the pain-trigger prompt and STT permission
scaffolding. The intended flow is:

1. Pain trigger fires.
2. The app speaks the open prompt.
3. The user answers by voice.
4. The transcript is sent to MCP `continue_dialogue`.
5. MCP returns the next highest-value question.

The current watch implementation includes TTS and a listening placeholder. The
next app step is a real streaming speech recognizer path, likely on the paired
phone if watchOS speech capture is too constrained.

## Synthetic Mode

Synthetic mode generates a rough random walk for heart rate, respiratory rate,
oxygen saturation, wrist temperature, accelerometer, and gyroscope. The Digital
Crown controls `pain_bias` from 0 to 1. Higher bias raises heart rate,
respiratory rate, motion, and temperature while nudging oxygen saturation down.

Synthetic rows use `source = synthetic_random_walk` and keep `pain_bias` in row
metadata, so they can be excluded from real analysis.

## Core ML Review

Current state:

- No committed `.mlmodel`.
- No committed `.mlmodelc`.
- Conversion script exists at `inference_flow/convert_to_coreml.py`.
- The recorded attempt used `coremltools 9.0`.
- Direct conversion failed because the frozen sklearn artifact was built with
  sklearn 1.6.1 and uses a model family/path that coremltools did not convert.

A recent systemwide update may improve the Python environment or Xcode runtime,
but it probably does not make the existing frozen artifact directly transpilable
unless it also changes the supported sklearn/coremltools conversion matrix. The
best next attempt is still:

1. Re-run the conversion script in the updated environment.
2. If it fails, train a separate small watch-local model using the same feature
   and output contract, with an estimator known to export cleanly.
3. Keep the server model unchanged.
