---
type: model
status: active
updated: 2026-06-08
tags: [features, standardization, sensors]
source_files:
  - src/painwatchstandard/sensors.py
  - src/painwatchstandard/features.py
  - src/painwatchstandard/baseline.py
---

# Feature Standardization

Window feature blocks:

```yaml
per_sensor:
  - mean
  - std
  - min
  - max
  - last
  - slope_per_s
  - peak_count
  - valid_count
  - valid_frac
  - present

acc_extra:
  - acc_mag summaries
  - stillness_frac

ibi_extra:
  - rmssd_ms
  - sdnn_ms
```

Standardization direction:

```yaml
raw_features: preserved
baseline_relative_features: appended
ids_and_targets: excluded from training features
leaky_protocol_fields: excluded from training features
```

Robust normalization explored:

```yaml
center: median
spread: MAD or IQR
clip: around +/-8 in R exploration
reason: physiological distributions have outliers and subject/device shifts
```

Sensor presence:

```yaml
present_flags:
  allowed_use:
    - quality
    - mask
    - device signature
    - calibration stratum
  forbidden_use:
    - direct evidence of pain/stress/activity
```

Problem from old models:

```yaml
presence_flags_dominated_scores: true
cause: sensor availability correlated with dataset/protocol labels
fix:
  - treat presence as control/mask
  - calibrate per sensor signature
  - simulate plausible dropout
  - prevent impossible sensor combos from becoming fake state evidence
```

