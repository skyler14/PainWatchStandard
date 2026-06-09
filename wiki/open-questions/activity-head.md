---
type: open_question
status: active
updated: 2026-06-08
tags: [activity, exertion]
---

# Activity Head

Problem:

```yaml
r_exploration: activity head predicted 1 for many direct-pain rows
likely_cause: activity labels are one-class or dataset/protocol-defined
```

Need:

```yaml
better_labels:
  - actual workout/exercise state
  - walking vs standing vs rest
  - exertion intensity
  - recovery phase

better_validation:
  - leave-dataset-out
  - sensor-signature-aware calibration
  - avoid using dataset identity as activity truth
```

Current policy:

```yaml
activity_as_hard_pain_gate: not yet
activity_as_context_signal: yes, cautious
```

