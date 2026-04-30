# Pain Thermometer Feeder Specification

Status: active first implementation
Date: 2026-04-29
Implementation: [pain_feeder.py](</Users/skyler/Downloads/pain datasets/pain_feeder.py:1>)

## Goal

Create a generalized feeder that turns normalized per-sample physiology tables into model-ready rows at a controlled prediction cadence.

The feeder should support:

- Minimum prediction cadence: 1-2 Hz.
- Supported prediction cadence: 1-10 Hz.
- Native-sample feature extraction, so high-frequency signals like BVP and EMG are not reduced to only 1 Hz raw means before features are computed.
- Sensor-block missingness, so devices with only a subset of sensors can still be used.
- Explicit label-quality metadata, so dense, sparse, session-level, and proxy labels are not treated as equivalent.

## Core Shape

The feeder output is a sliding-window feature table:

```text
one row = one prediction anchor
window = trailing native-sample interval ending at that anchor
target_hz = how often anchors are emitted
window_seconds = how much history each row sees
```

Example input window shape:

```text
dataset_id=painmonit
subject_id=PMCD_014
session_id=PMCD_014_clinical_physiotherapy
window_start_s=510.0
window_end_s=540.0
target_hz=1.0
window_seconds=30.0

label_family=direct_pain
source_family=clinical_direct_pain
collection_protocol=painmonit_pmcd_clinical
target_available=1
target_pain_nrs_0_10=6.0
target_pain_class_3=2
target_confidence=0.75

aux_stress_label=NULL
target_stress_binary=NULL
baseline_anchor_id=NULL
baseline_state_bin=no_subject_baseline

eda__present=1
eda__valid_frac=0.98
eda__mean=...
hr__present=1
hr__valid_frac=1.00
hr__mean=...
acc__present=1
acc__valid_frac=1.00
acc__mag__mean=...
```

This emits one row per second. Each row summarizes the prior 30 seconds of native samples. For 2 Hz, it emits one row every 0.5 seconds. For 10 Hz, one row every 0.1 seconds.

This is different from tokenizing raw samples. The model still receives tabular features usable by tree/boost/GBM methods, but each sensor remains a block with presence, quality, and summary features.

Stress/proxy rows use the same shape but remain auxiliary:

```text
dataset_id=stress_reference_real
source_dataset=WESAD
label_family=stress_proxy
source_family=derived_hr_eda_stress
collection_protocol=xalentis_stress_derived_features
target_available=0
target_pain_nrs_0_10=NULL
aux_stress_label=1
target_stress_binary=1
target_confidence=0.0
hr__present=1
eda__present=1
```

These rows can train stress/state heads and improve physiological coverage, but they must not contribute gradients to the direct pain head.

## Current Feeder Inputs

The first feeder reads compressed Parquet outputs already created by the normalizer.

| Dataset | Input table | Label regime |
| --- | --- | --- |
| `painmonit` | `_normalized/painmonit/clinical/measurement_stream.parquet` | Sparse direct pain samples inside synchronized PMCD clinical streams |
| `rheumapain` | `_normalized/rheumapain/frequency_hz=64/measurement_stream.parquet` | Weak/session-level direct pain score |

Future inputs:

| Dataset | Expected input | Label regime |
| --- | --- | --- |
| `physiopain` | processed watch Parquet plus survey/covariates | Direct pain intensity/type, exact granularity to confirm |
| `painmonit_pmed` | PMED experimental stream | Direct COVAS/heat-pain labels |
| `catsa`, `epm_e4`, `wesad` | proxy/self-supervised windows | No direct pain target |

## Canonical Sensor Blocks

The feeder maps dataset-specific columns into canonical sensor blocks.

| Block | Canonical columns | Notes |
| --- | --- | --- |
| `bvp` | `bvp` | Empatica/watch blood volume pulse |
| `bvp_rb` | `bvp_rb` | PainMonit respiratory-belt BVP variant |
| `eda` | `eda` | Empatica/watch EDA; PainMonit `Eda_E4` maps here |
| `eda_rb` | `eda_rb` | PainMonit respiratory-belt EDA |
| `temperature` | `temperature` | Skin/body/wrist temperature channel |
| `acc` | `acc_x`, `acc_y`, `acc_z`, derived `acc_mag` | Activity/motion block |
| `respiration` | `respiration` | PainMonit respiration |
| `emg` | `emg` | PainMonit EMG |
| `grip` | `grip` | PainMonit grip sensor |

Each block emits:

```text
<sensor>__present
<sensor>__valid_count
<sensor>__valid_frac
<sensor>__mean
<sensor>__std
<sensor>__min
<sensor>__max
<sensor>__last
<sensor>__slope_per_s
<sensor>__peak_count
```

`acc` additionally emits per-axis features plus magnitude and stillness features.

## Label Matching

Labels are canonicalized, but label quality is preserved.

| Dataset | Source label | Canonical target | Scale | Granularity | Training use |
| --- | --- | --- | --- | --- | --- |
| PainMonit PMCD | `pain_rate_nrs` | `target_pain_nrs_0_10` | NRS 0-10 | sparse sample/event | Primary direct target when observed in a window |
| PainMonit PMCD | `pain_label` | `target_pain_class_3` | 0 no / 1 moderate / 2 severe | sparse sample/event | Auxiliary ordinal/class target |
| RheumaPain | `pain_score` | `target_pain_nrs_0_10` | Wong-Baker 0-10 | session weak | Use with lower weight or session aggregation |
| PhysioPain | `pain_scale` | `target_pain_nrs_0_10` | to confirm | processed sample/segment to confirm | Add after normalization verifies scale |
| PhysioPain | `pain_type` | `target_pain_type` | categorical pain type | processed sample/segment to confirm | Context/stratification, not intensity alone |
| CATSA/EPM/WESAD/etc. | stress/emotion/activity labels | `aux_arousal_context` | proxy, not pain | dataset-specific | Self-supervised/auxiliary only |

The feeder columns that protect this distinction:

```text
target_available
target_pain_nrs_0_10
target_pain_min
target_pain_max
target_pain_count
target_pain_coverage
target_pain_class_3
target_scale
target_granularity
target_confidence
```

Current confidence defaults:

| Regime | Confidence |
| --- | ---: |
| PainMonit sparse direct sample/event | 0.75 |
| RheumaPain weak session label | 0.35 |
| no observed pain target | 0.0 |

These are not scientific constants. They are training weights/placeholders to avoid accidentally treating every label regime as equally precise.

## Window Semantics

Default windowing:

```text
anchor at t
window_start = t - window_seconds
window_end = t
include rows where sample_offset_s > window_start and <= window_end
```

This makes the row causal/trailing: the model only sees history up to the prediction anchor.

Recommended initial settings:

| Use | target_hz | window_seconds |
| --- | ---: | ---: |
| First training table | 1 Hz | 30 s |
| Higher-cadence local experimentation | 2 Hz | 30 s |
| Sensor/debug stress test | 10 Hz | 10-30 s |
| Slow autonomic drift features | 1 Hz | 60-120 s |

The first implementation emits only full windows by default. Partial windows can be enabled for short sessions, but should be avoided in first model training unless a feature marks them clearly.

## Normalization Policy

Do not permanently z-score raw sensor streams inside the feeder as the only representation.

The feeder should output:

1. Raw native-sample window features.
2. Sensor presence and valid-fraction features.
3. Optional personal-baseline features when an explicit baseline/rest condition exists.

Personal baseline features are appended, not substituted:

```text
<feature>__baseline_mean
<feature>__baseline_std
<feature>__delta_from_baseline
<feature>__z_from_baseline
baseline_available
```

When z-score makes sense now:

- Use it as an additional feature when the dataset has an explicit baseline/rest condition for that subject.
- RheumaPain has `condition=rest`, so personal baseline features are meaningful.

When z-score belongs downstream:

- Population z-score/global scaling must be fitted only on the training fold inside the model pipeline.
- Do not compute population normalization over the full dataset before train/test split, because that leaks evaluation distribution into training.
- PainMonit PMCD run-up baselines are not normalized yet, so baseline z-score should not be forced for PainMonit clinical rows until those run-up streams are ingested or another baseline definition is chosen.

## Metadata Policy

Metadata is first-class, but must be guarded against leakage.

Safe feeder metadata:

```text
dataset_id
subject_id
session_id
condition
record_type
device
diagnosis
sex
age
pain_scale_type
no_pain_threshold
severe_pain_threshold
```

Training cautions:

- `subject_id` and `session_id` are allowed in the feeder table for traceability, but should usually be dropped or encoded carefully before model training.
- Always evaluate with leave-subject-out splits.
- For cross-dataset claims, also evaluate leave-dataset-out.
- Dataset/protocol metadata can become a shortcut. It is useful for calibration, but it can hide poor physiological generalization if validation is weak.

## Self-Supervised Phase Compatibility

The feeder supports a light self-supervised phase without transformers:

1. Build the same window table over all datasets.
2. Randomly blank sensor blocks with modality dropout.
3. Train reconstruction models to predict one sensor block from the others.
4. Store prediction residuals as additional features for supervised pain models.

The implemented `drop_sensor_blocks` function is the primitive for this. Reconstruction models can be tree/GBM/sklearn models over the feeder rows.

## Commands

Print canonical label matches:

```bash
python3 pain_feeder.py label-map
```

Build the first 1 Hz / 30 s feeder table:

```bash
python3 pain_feeder.py build-windows --dataset all --target-hz 1 --window-seconds 30
```

Build a 2 Hz table:

```bash
python3 pain_feeder.py build-windows --dataset all --target-hz 2 --window-seconds 30 --output _normalized/window_features/target_hz=2/window_features.parquet
```

Fast development run:

```bash
python3 pain_feeder.py build-windows --dataset all --target-hz 1 --window-seconds 30 --max-sessions 4
```

Summarize an output:

```bash
python3 pain_feeder.py summarize _normalized/window_features/target_hz=1/window_features.parquet
```
