---
type: model
status: active
updated: 2026-06-10
tags: [inference, output, confidence]
source_files:
  - src/painwatchstandard/inference.py
  - README.md
---

# Inference Contract

Deployment output should expose:

```yaml
scores:
  - pain_likelihood
  - pain_nrs_estimate
  - stress_likelihood
  - activity_likelihood
  - low_exertion_context_likelihood
  - recovery_or_relaxed_context_if_available

state_preference:
  - pain_preference
  - stress_preference
  - activity_preference
  - context_preference
  - state_margin

quality:
  - sensor_quality
  - missing_sensor_blocks
  - sensor_signature
  - calibration_context
  - confidence
```

Functional display layer:

```yaml
functional_pain_v1:
  type: ternary physiology tracker
  vertices:
    - sympathetic
    - parasympathetic
    - homeostasis
  outputs:
    - ternary_x
    - ternary_y
    - functional_pain_0_1
    - recovery_0_1
  use: intervention tracking and return-to-baseline visualization
  not: standalone diagnosis or supervised pain truth
```

See [[model/functional-pain-v1]].

Confidence must not mean:

```yaml
not: raw probability far from 0.5
```

Confidence should mean:

```yaml
better:
  - enough useful sensors
  - known sensor signature
  - calibrated context
  - strong margin over competing states
  - sustained state over recent ticks
```

Missing sensors:

```yaml
dropout_behavior:
  relevant_head_missing_required_sensor: omit or lower eligibility
  no_fake_zero: true
  no_presence_as_positive_evidence: true
```

Live row meaning:

```yaml
each_tick: current score from trailing physiology window
current_master_cadence: 1Hz
future_possible_cadence: 2Hz
```
