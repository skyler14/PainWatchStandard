# PainThermometer Questionnaire MCP Spec

## Purpose

The watch app records biosensor samples, builds rolling inference windows, and
enters pain activation mode when at least 7 of the last 10 score windows are
positive. When that threshold is reached, the app can call a local or remote MCP
server to administer a short questionnaire for the current run.

## Trigger Payload

```json
{
  "run_id": "6F02A9DB-9E83-47A2-9486-0660FB83E537",
  "device_id": "9F8C667D-9057-4890-A174-88187B866308",
  "trigger_score": 0.78,
  "activation_positive_count": 7,
  "activation_window_count": 10
}
```

The initial MCP tool is `start_questionnaire`. It returns a `session_id`, the
questionnaire state, and item definitions. Follow-up calls use
`get_questionnaire` and `submit_questionnaire_answers`.

## Watch Buffer

The watch now maintains a 100-measurement display buffer in memory. The durable
JSONL run store is unchanged and keeps every sample. When the display buffer
exceeds capacity, samples are ranked for eviction with a Visvalingam-Whyatt
style triangle-area score per sensor:

- keep newest samples and per-sensor endpoints where possible
- prefer removing low-area older points that contribute least to local shape
- fall back to absolute oldest sample when a sensor has too few points

This preserves useful shape in the live sensor page without changing upload or
historical export semantics.

## Watch Display Requirements

- Recording tab: elapsed time, 7/10 activation strip, dropout summary, buffer
  count, and questionnaire trigger state.
- Sensors tab: latest readable value per sensor, unit, sample count, and last
  update time.
- Scores tab: activation state plus any score fields returned by local CoreML or
  the endpoint, including pain likelihood, pain score, stress likelihood,
  baseline departure, confidence, quality, and model version.

## Open Work

- Add an app-side MCP client call from the watch or paired phone after
  `questionnaireText` becomes trigger-ready.
- Persist questionnaire sessions outside process memory.
- Decide whether completed answers are uploaded with the run archive or stored
  only through the MCP server.
