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

The MCP server should be registered/invoked in PromptOpinion as:

```text
PainThermometer
```

When PromptOpinion shows a tool namespace, use the exact tool name under the `PainThermometer` MCP server. For example, if the UI exposes namespaced tools, the intended invocations are:

```text
PainThermometer.list_patients
PainThermometer.summarize_patient_history
PainThermometer.compute_pain_score
PainThermometer.start_questionnaire
PainThermometer.get_questionnaire
PainThermometer.continue_dialogue
PainThermometer.submit_questionnaire_answers
```

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

## GPM Questionnaire Field Content

These are the actual Geriatric Pain Measure style fields the agent should cover. The agent should ask natural combined questions, but the internal fields and meanings are:

| Field id | Type | Content |
| --- | --- | --- |
| `vigorous_activity` | yes/no | pain with vigorous activities such as running, lifting, or strenuous sports |
| `moderate_activity` | yes/no | pain with moderate activities such as pushing a vacuum, bowling, or golf |
| `groceries` | yes/no | pain with lifting or carrying groceries |
| `stairs_flight` | yes/no | pain climbing more than one flight of stairs |
| `few_steps` | yes/no | pain climbing only a few steps |
| `walk_block_plus` | yes/no | pain walking more than one block |
| `walk_block_or_less` | yes/no | pain walking one block or less |
| `bathing_dressing` | yes/no | pain with bathing or dressing |
| `reduced_time` | yes/no | cutting down time spent on work or activities because of pain |
| `accomplish_less` | yes/no | accomplishing less than wanted because of pain |
| `limited_activities` | yes/no | limiting the kind of work or activities because of pain |
| `extra_effort` | yes/no | needing extra effort for work or activities because of pain |
| `sleep_trouble` | yes/no | trouble sleeping because of pain |
| `religious_activity` | yes/no | pain preventing religious activities |
| `social_recreation` | yes/no | pain preventing social or recreational activities |
| `transportation` | yes/no | pain preventing travel or standard transportation |
| `fatigue` | yes/no | pain making the patient feel fatigued or tired |
| `help_needed` | yes/no | relying on family or friends for help because of pain |
| `pain_today_0_10` | score 0-10 | pain severity today from zero to ten |
| `pain_week_average_0_10` | score 0-10 | average pain severity over the last seven days from zero to ten |
| `never_goes_away` | yes/no | pain that never completely goes away |
| `daily_pain` | yes/no | pain every day |
| `several_times_week` | yes/no | pain several times a week |
| `sad_depressed` | yes/no | sadness or depression caused by pain over the last seven days |

Recommended opening:

```text
Tell me what happened when the pain started, where you felt it, and what it felt like.
```

Recommended combined follow-ups:

- "How much did this affect stairs, walking a block, bathing or dressing, or carrying groceries?"
- "Did the pain make you cut down activities, accomplish less, limit what you could do, or require extra effort?"
- "Did it affect sleep, make you tired, limit social/religious activities or transportation, or make you need help?"
- "What number from zero to ten is the pain today, and what has it averaged over the last seven days?"
- "Does it ever completely go away, is it daily, or does it happen several times per week?"
