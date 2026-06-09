---
type: model
status: active
updated: 2026-06-08
tags: [baseline, archetype, calibration]
source_files:
  - docs/LABELED_DATASET_INSTANCE_ANALYSIS.md
  - docs/APPLE_HEALTH_ARCHETYPE_READINGS.md
---

# Baselines And Archetypes

Rejected:

```yaml
baseline_departure:
  as_single_term: rejected
  reason: mixes sleep, rest, walking, exercise, stress, pain into one bad comparison
```

Preferred:

```yaml
context_aware_baselines:
  numeric: median + MAD/IQR/P90 depending context
  categorical: mode
  compare_against: current inferred context/archetype
```

Archetypes v1:

```yaml
sleep_rest:
  sources: Apple sleep HR, respiration, SpO2, HRV
  use: low-exertion calibration
  pain_label: no

awake_low_exertion:
  sources: Apple awake nonworkout, CATSA baseline
  use: low-exertion context
  pain_label: no

walking_light_exertion:
  sources: Apple walking HR, steps/distance, walking workouts
  use: expected exertion HR
  pain_label: no

workout_exertion:
  sources: Apple workouts, physical effort, induced exercise, RheumaPain exercise
  use: activity/exertion context
  pain_label: no

recovery:
  sources: heart-rate recovery, post-workout windows
  use: partial recovery context
  pain_label: no
```

Supervised pain/no-pain remains separate:

```yaml
explicit_no_pain:
  sources:
    - physiopain no_pain
    - rheumapain rest zero

explicit_pain:
  sources:
    - painmonit clinical
    - painmonit_pmed heat
    - rheumapain rest/exercise pain
    - physiopain pain types
    - silver_pain
```

Rule:

```yaml
watch_archetype_explains_physiology: true
watch_archetype_creates_pain_truth: false
```

