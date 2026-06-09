# Labeled Dataset Instance Analysis

Script:

```text
scripts/analyze_labeled_datasets.py
```

Outputs:

```text
outputs/labeled_dataset_analysis/*.csv
```

## Direct Labeled Datasets

### PainMonit PMCD

Sampled first 18 clinical sessions. Important shape:

```yaml
painmonit_pmcd:
  row_count_per_session: 28k-50k
  labeled_pain_points_per_session: 4-36
  pain_range_seen: 1-10
  label_classes_seen: [0, 1, 2]
  best_use:
    - sparse_event_direct_pain
    - high_confidence_labels_when_present
  problem:
    - most rows have no direct pain value
    - need window label policy based on nearest/sparse pain point
```

Examples:

```yaml
p01_trial1: {rows: 43938, pain_points: 12, pain_min: 4, pain_median: 7, pain_max: 9}
p06_trial1: {rows: 42727, pain_points: 24, pain_min: 4, pain_median: 9, pain_max: 10}
p09_trial2: {rows: 32000, pain_points: 12, pain_min: 7, pain_median: 9, pain_max: 10}
```

### RheumaPain

Full 64 Hz processed pass.

```yaml
rheumapain:
  labels: rest/exercise with weak session-level pain
  pain_values_seen: [0, 1, 2, 3, 4, 5]
  high_pain_absent: true
  best_use:
    - rest_vs_exercise context
    - weak low/moderate direct pain
    - pediatric rheumatology domain
  problem:
    - session label copied across many samples
    - limited high pain range
```

Distribution:

```yaml
exercise:
  zero: {rows: 39101, subjects: 5}
  mild_1_3: {rows: 411860, subjects: 12}
  moderate_4_5: {rows: 160209, subjects: 10}

rest:
  zero: {rows: 302792, subjects: 19}
  mild_1_3: {rows: 442086, subjects: 11}
  moderate_4: {rows: 31183, subjects: 1}
```

### PhysioPain / Multimodal Pain Dataset

Full label-only pass over combined 64 Hz watch file. `PhysioPain Dataset.zip` and `Multimodal Pain Dataset.zip` appear same/overlapping for this combined watch table.

```yaml
physiopain_watch:
  pain_types: [back_pain, headache, menstrual_pain, no_pain]
  pain_scale_values: [1, 2, 3, 4, 5]
  no_pain_rows: 1375850
  best_use:
    - direct pain watch-like labels
    - pain type stratification
    - no-pain archetype candidate
  problem:
    - rows sorted by pain type; naive head sample lies
    - scale semantics still need survey/readme validation
```

Label distribution:

```yaml
back_pain:
  scale_2: {rows: 700323, subjects: 4}
  scale_3: {rows: 1108626, subjects: 5}
  scale_4: {rows: 508871, subjects: 2}
  scale_5: {rows: 177056, subjects: 1}

headache:
  scale_1: {rows: 171552, subjects: 1}
  scale_2: {rows: 572650, subjects: 3}
  scale_3: {rows: 1113645, subjects: 5}
  scale_4: {rows: 183058, subjects: 1}
  scale_5: {rows: 169600, subjects: 1}

menstrual_pain:
  scale_2: {rows: 189536, subjects: 1}
  scale_3: {rows: 170144, subjects: 2}
  scale_4: {rows: 158336, subjects: 2}
  scale_5: {rows: 449058, subjects: 3}

no_pain:
  scale_1: {rows: 1375850, subjects: 8}
```

### SILVER-Pain

New promising direct-pain dataset.

```yaml
silver_pain:
  cohorts: [older_adults, young_adults]
  sensors: [bvp, eda, temperature, hr]
  labels: PainLevel
  best_use:
    - direct pain with older/young cohort split
    - HR/BVP/EDA/temp watch-like but no ACC
  problem:
    - label rows sparse relative to sensor rows
    - need readme semantics before final scale mapping
```

Quick sensor-by-pain sample says label rows are sparse but useful. Young high-pain has BVP/EDA/temp/HR coverage; older HR coverage is thin in labeled points.

## Context Archetype Plan

Do not use one `baseline_departure`.

Apple Watch does not provide a pain category or a no-pain category. It provides physiology and activity context. Pain/no-pain labels must come from explicit pain datasets or user reports.

Use a small set of practical context archetypes now, chosen from datasets + Apple Watch availability:

```yaml
context_archetypes_v1:
  sleep_rest:
    source_now:
      - apple_health_sleep_hr
      - apple_health_respiration
      - apple_health_spo2
      - apple_health_hrv
    statistic:
      numeric_terms: median_and_mad
      categorical_state: mode
    output_labels_supported:
      low_exertion_context: yes
      pain_label: no
    reason: cleanest personal low-activity baseline

  awake_low_exertion:
    source_now:
      - apple_health_awake_nonworkout_hr
      - catsa_baseline
    statistic:
      numeric_terms: median_and_mad
      categorical_state: mode
    output_labels_supported:
      low_exertion_context: yes
      pain_label: no
      no_pain_label: no
    reason: best practical non-sleep watch context; not evidence of no pain

  walking_light_exertion:
    source_now:
      - apple_health_walking_hr_average
      - apple_health_steps_distance
      - workouts_walking
    statistic:
      numeric_terms: median_and_iqr
      categorical_state: mode
    output_labels_supported:
      activity_context: yes
      exertion_expected_hr: yes
    reason: HR 115 normal here, not pain/stress by itself

  workout_exertion:
    source_now:
      - apple_health_workouts
      - apple_health_physical_effort
      - induced_stress_exercise_aerobic_anaerobic
      - rheumapain_exercise
    statistic:
      numeric_terms: median_and_p90
      categorical_state: mode
    output_labels_supported:
      exercise_context: yes
      pain_label: no
    reason: separate exertion physiology from pain physiology

  recovery:
    source_now:
      - apple_health_heart_rate_recovery
      - post_workout_windows_later
    statistic:
      numeric_terms: median_drop_curve
      categorical_state: mode
    output_labels_supported:
      recovery_context: partial
    reason: useful but needs more derived windows
```

Supervised pain/no-pain labels stay separate:

```yaml
supervised_label_contexts_v1:
  explicit_no_pain:
    source_now:
      - physiopain_no_pain
      - rheumapain_rest_zero
    output_labels_supported:
      no_pain_label: yes
    reason: comes from dataset label, not watch archetype

  explicit_pain:
    source_now:
      - painmonit_clinical_nonexercise_if_detectable
      - rheumapain_rest_pain
      - physiopain_pain_types
      - silver_pain
    statistic:
      numeric_terms: median_and_mad_by_person_if_possible
      categorical_state: mode_pain_type
    output_labels_supported:
      passive_pain: yes
      pain_severity: yes
    reason: pain-specific supervised label source; use watch context only as covariate/gate
```

## Median vs Mode Rule

```yaml
numeric_sensor_baselines:
  use: median
  spread: mad_or_iqr
  examples:
    - heart_rate
    - hrv_sdnn
    - respiratory_rate
    - spo2
    - physical_effort
    - eda
    - temperature

categorical_archetype_labels:
  use: mode
  examples:
    - pain_type
    - workout_type
    - sleep_stage
    - activity_context

ordinal_pain_labels:
  use: median_for_session_summary
  also_keep: full_distribution
  examples:
    - PainMonit sparse NRS
    - RheumaPain Wong-Baker
    - PhysioPain 1-5 source scale
```

## Output Labels To Populate Now

```yaml
labels_v1:
  pain_present:
    from:
      - PainMonit pain_rates > threshold
      - RheumaPain pain_scale > 0 with weak confidence
      - PhysioPain pain_type != no_pain
      - SILVER PainLevel > 0 after readme validation

  pain_severity:
    from:
      - PainMonit NRS 0-10
      - RheumaPain 0-5 weak/session
      - PhysioPain 1-5 source
      - SILVER PainLevel

  pain_type:
    from:
      - PhysioPain pain_type
      - Multimodal pain_type

  explicit_no_pain:
    from:
      - PhysioPain no_pain
      - RheumaPain rest zero
    not_from:
      - CATSA Baseline
      - Apple awake_nonworkout

  awake_low_exertion_context:
    from:
      - Apple awake_nonworkout
      - CATSA Baseline
    means: low exertion or neutral protocol only
    does_not_mean: no pain

  sleep_rest:
    from:
      - Apple sleep
    means: sleep physiology context only
    does_not_mean: no pain

  walking_light_exertion:
    from:
      - Apple walking HR average
      - walking workouts
    means: exertion context only
    does_not_mean: pain

  workout_exertion:
    from:
      - Apple workouts
      - physical_effort
      - induced stress/exercise activity labels
      - RheumaPain exercise context

  cognitive_stress:
    from:
      - CATSA Logic/Nback/Stroop/Sudoku

  generic_stress:
    from:
      - WESAD stress protocol
      - stress reference rows
      - induced stress labels
```

## Later With User Permission

Collect explicitly:

```yaml
future_userbase_archetypes:
  sitting_rest:
    needs: watch_worn_awake_low_motion_low_effort
  pain_at_rest:
    needs: self_report_pain + low activity_context
  pain_during_exertion:
    needs: self_report_pain + workout/walk_context
  recovery_after_pain:
    needs: repeated post-event windows
  medication_response:
    needs: medication timestamp + symptom followup
```
