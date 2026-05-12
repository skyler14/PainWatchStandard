# PainThermometer MCP Tool Contract

Endpoint:

```text
https://pain-thermometer-po.web.app/mcp
```

Transport:

```text
Streamable HTTP
```

Authentication:

```text
None
```

## Tools

### `list_patients`

Returns patients visible to a clinician group.

Arguments:

```json
{
  "clinician_group_id": "grp_doctor_a"
}
```

Returns patient ids, FHIR patient ids, names, source, and session counts.

### `summarize_patient_history`

Summarizes known sessions, incidents, scores, survey fields, and transcript notes.

Arguments:

```json
{
  "clinician_group_id": "grp_doctor_a",
  "patient_id": "..."
}
```

### `compute_pain_score`

Recomputes watch-derived pain and stress likelihood from supplied vitals or stored session vitals.

Arguments:

```json
{
  "clinician_group_id": "grp_doctor_a",
  "patient_id": "...",
  "session_id": "..."
}
```

Optional direct vitals input:

```json
{
  "vitals": [
    {
      "sample_time_utc": "2026-05-12T20:50:00.000Z",
      "heart_rate": 104,
      "respiratory_rate": 22,
      "wrist_temperature": 33.8,
      "oxygen_saturation": 0.96
    }
  ]
}
```

### `start_questionnaire`

Starts a GPM-style questionnaire from a watch pain trigger.

Arguments:

```json
{
  "incident_id": "...",
  "local_session_id": "...",
  "pain_score": 0.78,
  "score_history": [],
  "buffer": []
}
```

### `continue_dialogue`

Adds a patient response and returns the next highest-value follow-up question.

Arguments:

```json
{
  "session_id": "...",
  "response_text": "My left knee started hurting when I stood up."
}
```

### `submit_questionnaire_answers`

Submits final structured answers and transcript.

Arguments:

```json
{
  "session_id": "...",
  "transcript": [],
  "answers": {}
}
```
