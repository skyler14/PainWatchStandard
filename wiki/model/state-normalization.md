---
type: model
status: active
updated: 2026-06-08
tags: [state-normalization, confidence, softmax]
source_files:
  - docs/STATE_NORMALIZATION_AND_R_FINDINGS.md
  - outputs/r_phase3_state_coupling/R_PHASE3_STATE_COUPLING_REPORT.md
---

# State Normalization

Old failure:

```yaml
independent_heads:
  pain: can be high
  stress: can be high
  activity: can be high
  confidence: can still be high
```

Bad confidence formula:

```text
confidence = 0.5 * sensor_quality + 0.5 * abs(probability - 0.5) * 2
```

Why bad:

```yaml
extreme_probability_from_leakage: raises confidence
competing_states: ignored
presence_flags: can encode dataset/protocol
result: high-confidence absurd IRL readings
```

Preferred display/action layer:

```yaml
state_scores:
  - pain
  - stress
  - activity
  - low_exertion_context
  - recovery
  - relaxed

state_preference:
  method: softmax over eligible state scores
  unavailable_heads: omitted, not forced to zero
```

Pain action should require:

```yaml
requirements:
  - pain absolute likelihood high
  - pain state preference high
  - state margin strong
  - activity not dominant
  - sensor quality acceptable
  - sustained across multiple ticks
```

R findings:

```yaml
pain_leave_dataset_auc:
  rheumapain: about 0.512
  painmonit: about 0.540
  physiopain_watch: about 0.641

stress_transfer:
  mixed: true

activity_head:
  currently_bad: predicts 1 for many direct-pain rows

pain_pref_norm:
  zero: about 0.187
  mild: about 0.190
  moderate: about 0.221
  severe: about 0.234
```

Interpretation:

```yaml
pain_signal: weak cross-dataset today
stress_signal: pain-correlated but dangerous if untreated
softmax_competition: useful guard against runaway positives
deployment_ready: no, needs calibration validation
```

