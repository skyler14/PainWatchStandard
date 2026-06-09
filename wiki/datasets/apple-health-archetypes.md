---
type: dataset
status: active
updated: 2026-06-08
tags: [apple-health, baseline, archetypes]
source_files:
  - docs/APPLE_HEALTH_ARCHETYPE_READINGS.md
  - scripts/apple_health_archetypes.py
---

# Apple Health Archetypes

Source:

```yaml
path: /Users/skyler/Downloads/pain datasets/export.zip
role: personal baseline/context exploration
included_in_master_windows: false
pain_truth: false
```

Natural metrics found:

```yaml
resting_heart_rate:
  n: 97
  median_bpm: 67

walking_heart_rate_average:
  n: 106
  median_bpm: 116.75

hrv_sdnn:
  n: 321
  median_ms: 40.06

respiratory_rate:
  n: 3247
  median_per_min: 16.0

oxygen_saturation:
  n: 904
  median_fraction: 0.97

physical_effort:
  n: 25229
  median_kcal_per_hr_kg: 3.7
```

Derived HR archetypes:

```yaml
sleep:
  median_bpm: 63

awake_nonworkout:
  median_bpm: 76

standing:
  median_bpm: 108

workout_or_exercise:
  median_bpm: 118
```

Critical interpretation:

```yaml
hr_115:
  normal_for: walking/workout context
  high_for: sleep/rest context
  not_by_itself: pain or stress
```

Use:

```yaml
good:
  - context-aware calibration
  - expected HR/effort under sleep/rest/walking/workout
  - sensor sanity checks

bad:
  - pain labels
  - no-pain labels
  - one global baseline_departure score
```

