# Ingest Pipeline

Source archives stay outside the repo:

```text
/Users/skyler/Downloads/PainDatasets
```

Normalized outputs are rebuildable Parquet/ZSTD artifacts.

## Commands

Inventory:

```bash
python scripts/ingest_datasets.py --source-root /Users/skyler/Downloads/PainDatasets inventory
```

Bounded smoke:

```bash
python scripts/ingest_datasets.py \
  --source-root /Users/skyler/Downloads/PainDatasets \
  --output-root _normalized/smoke \
  --chunksize 5000 \
  normalize-all \
  --max-sessions 1 \
  --max-chunks 1
```

Full ingest:

```bash
python scripts/ingest_datasets.py \
  --source-root /Users/skyler/Downloads/PainDatasets \
  --output-root _normalized/full \
  --chunksize 100000 \
  normalize-all
```

Build Phase 3 windows:

```bash
python scripts/build_windows.py \
  --input-root _normalized/full \
  --output-path _normalized/phase3/target_hz=1/window_features.parquet \
  --target-hz 1 \
  --window-seconds 30
```

## Registered Datasets

```yaml
direct_pain_watch_or_clinical:
  - painmonit
  - painmonit_pmed
  - rheumapain
  - physiopain_watch
  - multimodal_pain_watch
  - silver_pain

context_or_auxiliary:
  - catsa
  - induced_stress_exercise
  - wearable_sports_health
  - wesad
  - wesad_respiban

separate_multimodal_branch:
  - physiopain_eeg
  - multimodal_pain_eeg
```

## Enrichment Rules

```yaml
painmonit:
  pmcd_main:
    use: clinical direct-pain sessions
  pmcd_runup:
    use: paired clinical setup/baseline rows
    pairing_key: baseline_pair_session_id
    pain_truth: false
  pmed:
    dataset_id: painmonit_pmed
    use: induced heat pain sessions
    separates_from_clinical: true

physiopain_multimodal_surveys:
  joined_to:
    - physiopain_watch
    - physiopain_eeg
    - multimodal_pain_watch
    - multimodal_pain_eeg
  derived_fields:
    - survey_age
    - survey_gender
    - survey_sleep_hours_avg
    - survey_sleep_hours_before_test
    - survey_daily_stress_ordinal
    - survey_chronic_pain_flag
    - survey_regular_medication_flag
    - survey_pain_context_score
    - survey_pain_type

rheumapain_workbook:
  joined_fields:
    - workbook_age
    - workbook_sex
    - workbook_diagnosis
    - workbook_pain_rest
    - workbook_pain_exercise
    - workbook_exercise_duration_text

wesad:
  e4:
    use: wrist stream
    joined_from_questionnaire:
      - protocol segment
      - protocol start/end
      - stress flag
      - coarse stress score
  respiban:
    use: chest ECG/EDA/EMG/temp/ACC/respiration stream
    source_rate_hz: 700
    ingested_rate_hz: 63.636
    reason: preserve chest physiology while keeping windowing tractable

ibi_hrv:
  input: sparse IBI events or per-row IBI columns
  window_features:
    - ibi__rmssd_ms
    - ibi__sdnn_ms

induced_stress_exercise:
  joined_fields:
    - target_stress_binary
    - target_stress_score_0_10
    - target_stress_score_mean_0_10
  ibi: included
```

## Current Full Build

Built from `/Users/skyler/Downloads/PainDatasets` on 2026-06-02:

```yaml
normalized_streams:
  path: _normalized/full
  disk_size: 563M
  measurement_stream_rows:
    catsa: 2879750
    induced_stress_exercise: 5232051
    multimodal_pain_eeg: 116189
    multimodal_pain_watch: 7048305
    painmonit: 2969065
    physiopain_eeg: 116189
    physiopain_watch: 7048305
    rheumapain: 1387231
    silver_pain: 3561459
    wearable_sports_health: 500
    wesad: 6844563

phase3_windows:
  path: _normalized/phase3/target_hz=1/window_features.parquet
  disk_size: 192M
  rows: 1490617
  columns: 193
  target_hz: 1
  window_seconds: 30
```

## Output Shape

Each dataset writes:

```yaml
measurement_stream.parquet:
  meaning: wide per-sample physiology stream
  common_columns:
    - dataset_id
    - source_archive
    - source_member
    - subject_id
    - session_id
    - condition
    - device
    - sample_rate_hz
    - sample_index
    - sample_offset_s
    - target_pain_nrs_0_10
    - target_pain_bin
    - label_family
  sensor_columns:
    - bvp
    - eda
    - hr
    - temperature
    - acc_x
    - acc_y
    - acc_z
    - respiration
    - emg
    - grip
    - spo2
    - steps
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

labels.parquet:
  meaning: compact per-session/per-label summary

subjects.parquet:
  meaning: compact subject index

manifest.json:
  meaning: source members, output paths, row count, schema note
```

Stage 2 writes:

```yaml
window_features.parquet:
  meaning: unified causal trailing-window table
  default:
    target_hz: 1
    window_seconds: 30
    include_partial_windows: false
  carries:
    - dataset_id
    - subject_id
    - session_id
    - condition
    - label_family
    - pain_type
    - device
    - cohort
  appends:
    - sensor present/valid/mean/std/min/max/last/slope/peak summaries
    - target_pain_nrs_0_10
    - target_pain_min
    - target_pain_max
    - target_pain_count
    - target_pain_coverage
```

## Label Rules

Apple Watch and context datasets do not create pain truth.

```yaml
pain_truth_allowed_from:
  - PainMonit pain rates
  - RheumaPain pain_scale
  - PhysioPain/Multimodal watch pain_scale + pain_type
  - SILVER PainLevel

pain_truth_not_allowed_from:
  - CATSA baseline/cognitive tasks
  - WESAD stress protocol
  - induced stress/exercise sessions
  - wearable sports activity rows
  - Apple Health archetypes
```

Presence flags are not written as direct state evidence here. Later feature extraction may derive masks/quality terms from actual sensor columns.
