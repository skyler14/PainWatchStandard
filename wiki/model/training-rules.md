---
type: model
status: active
updated: 2026-06-08
tags: [training, leakage, labels]
source_files:
  - src/painwatchstandard/routing.py
  - src/painwatchstandard/features.py
  - docs/STATE_NORMALIZATION_AND_R_FINDINGS.md
---

# Training Rules

Label gating:

```yaml
pain_loss:
  allowed_rows:
    - label_family == direct_pain
    - non_null target pain
  forbidden_rows:
    - stress_proxy
    - cognitive_load_proxy
    - exercise_context
    - baseline_context
    - apple_health_archetypes

stress_loss:
  allowed_rows:
    - explicit stress labels/protocol rows

activity_loss:
  allowed_rows:
    - explicit activity/exertion rows
  current_status: weak, needs better labels
```

Recommended architecture:

```yaml
multi_head:
  shared_features: robust-normalized sensor summaries
  masks: sensor signature / presence / quality
  heads:
    - pain
    - stress
    - activity
    - context
  display_layer:
    - softmax state preference among eligible heads
```

Validation:

```yaml
must_have:
  - subject holdout
  - dataset holdout
  - leave-sensor-signature-out where possible
  - calibration curves
  - no auxiliary labels in pain loss
  - no source/protocol IDs as training features
```

Leakage risks:

```yaml
risk_fields:
  - dataset_id
  - subject_id
  - session_id
  - source_archive
  - source_member
  - protocol labels if target leaked
  - raw presence flags if unconstrained

allowed_use:
  - grouping
  - calibration stratum
  - audit
  - output context
```

