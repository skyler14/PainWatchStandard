---
type: pipeline
status: active
updated: 2026-06-09
tags: [schema, fields]
source_files:
  - src/painwatchstandard/ingest.py
  - src/painwatchstandard/build_windows.py
  - src/painwatchstandard/windowing.py
---

# Schema

## Measurement Stream

Meaning: per-sample normalized physiology rows.

Common fields:

```yaml
identity:
  - dataset_id
  - source_archive
  - source_member
  - subject_id
  - session_id

time:
  - sample_rate_hz
  - sample_index
  - sample_offset_s

context:
  - condition
  - label_family
  - pain_type
  - device
  - cohort
  - record_type
  - baseline_pair_session_id
  - pain_protocol_kind
  - aux_state_label

targets:
  - target_pain_nrs_0_10
  - target_pain_bin
  - pain_intensity
  - source_pain_covas_0_100
  - pain_scale_type
  - target_stress_binary
  - target_stress_score_0_10
  - target_stress_score_mean_0_10
```

Sensor columns:

```yaml
watch_like:
  - bvp
  - eda
  - hr
  - temperature
  - acc_x
  - acc_y
  - acc_z
  - ibi

clinical_or_chest:
  - respiration
  - ecg
  - emg
  - grip

consumer_other:
  - spo2
  - steps

eeg:
  - eeg_delta
  - eeg_theta
  - eeg_alpha1
  - eeg_alpha2
  - eeg_beta1
  - eeg_beta2
  - eeg_gamma1
  - eeg_gamma2
  - eeg_attention
  - eeg_meditation
```

## Window Features

Meaning: one prediction tick from trailing recent samples.

Carries:

```yaml
identity:
  - dataset_id
  - subject_id
  - session_id

window:
  - window_start_s
  - window_end_s
  - window_seconds
  - target_hz
  - source_rows
  - window_max_gap_s
  - window_allowed_gap_s
  - window_contiguous

context:
  - condition
  - label_family
  - pain_type
  - device
  - cohort
  - record_type
  - baseline_pair_session_id
  - pain_protocol_kind
  - aux_state_label
  - survey_*
  - workbook_*
  - wesad_protocol_*
```

Per-sensor feature pattern:

```yaml
numeric_summary:
  - __mean
  - __std
  - __min
  - __max
  - __last
  - __slope_per_s
  - __peak_count
  - __valid_count
  - __valid_frac
  - __present

special:
  acc:
    - acc__stillness_frac
  ibi:
    - ibi__rmssd_ms
    - ibi__sdnn_ms
```

Target aggregate fields:

```yaml
pain:
  - target_available
  - target_pain_nrs_0_10
  - target_pain_min
  - target_pain_max
  - target_pain_count
  - target_pain_coverage

stress:
  - target_stress_binary
  - target_stress_score_0_10
  - target_stress_score_mean_0_10
```
