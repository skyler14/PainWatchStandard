# Apple Health Archetype Readings

Source:

```text
/Users/skyler/Downloads/pain datasets/export.zip
```

Parser:

```text
scripts/apple_health_archetypes.py
```

## Natural Apple Metrics

```yaml
resting_heart_rate:
  n: 97
  median_bpm: 67
  mean_bpm: 68.5
  p10_p90_bpm: [58, 83.4]

walking_heart_rate_average:
  n: 106
  median_bpm: 116.75
  mean_bpm: 114.64
  p10_p90_bpm: [98.25, 129]

heart_rate_variability_sdnn:
  n: 321
  median_ms: 40.06
  mean_ms: 45.14
  p10_p90_ms: [24.90, 68.66]

respiratory_rate:
  n: 3247
  median_per_min: 16.0
  mean_per_min: 16.31
  p10_p90_per_min: [15.0, 18.0]

oxygen_saturation:
  n: 904
  median_fraction: 0.97
  mean_fraction: 0.966
  p10_p90_fraction: [0.94, 0.99]

physical_effort:
  n: 25229
  median_kcal_per_hr_kg: 3.7
  mean_kcal_per_hr_kg: 3.75
  p10_p90_kcal_per_hr_kg: [1.5, 5.7]

vo2max:
  n: 71
  median_ml_min_kg: 31.11
  mean_ml_min_kg: 31.72
  p10_p90_ml_min_kg: [30.48, 33.36]
```

## Derived HR Archetypes

```yaml
sleep:
  hr_samples: 6697
  median_bpm: 63
  mean_bpm: 63.76
  p10_p90_bpm: [55, 73]

awake_nonworkout:
  hr_samples: 10113
  median_bpm: 76
  mean_bpm: 80.18
  p10_p90_bpm: [67, 100]

standing:
  hr_samples: 3883
  median_bpm: 108
  mean_bpm: 108.36
  p10_p90_bpm: [84.2, 133]

workout_or_exercise:
  hr_samples: 100189
  median_bpm: 118
  mean_bpm: 116.06
  p10_p90_bpm: [72, 151]
```

## Workout Mix

```yaml
walking:
  workouts: 75
  median_duration_min: 25.85
  mean_duration_min: 31.56

cycling:
  workouts: 61
  median_duration_min: 15.63
  mean_duration_min: 17.09

traditional_strength_training:
  workouts: 35
  median_duration_min: 98.39
  mean_duration_min: 105.82

other:
  workouts: 8
  median_duration_min: 4.35
  mean_duration_min: 25.73
```

## Quick Read

Watch data is wear-context biased:

- Many HR samples from workout/exercise.
- Sleep baseline exists and looks coherent.
- Awake nonworkout baseline exists, but smaller.
- Standing HR median is high (`108`), likely because Apple stand/exercise overlap and sparse wear context.
- HR `115` is normal for walking/workout in this export, but high relative to sleep/rest.

Model implication:

```yaml
do:
  - compare HR to context archetype
  - use walking/workout baselines for exertion
  - use sleep/resting HR/HRV/respiration for low-activity baseline
  - model "unknown context" when watch wear is biased
  - keep Apple Health archetypes as context covariates and calibration anchors

do_not:
  - use one baseline_departure term
  - treat HR 115 as pain/stress without context
  - infer a pain category from Apple Watch alone
  - treat awake_nonworkout or sleep as no-pain labels
```

Apple Health context can explain why a sensor value is normal for the moment. It should not create pain truth.
