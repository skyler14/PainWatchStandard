# Normalization Status

Date: 2026-04-29

## Current Bearings

Three new pain-labeled zip datasets are present locally:

| Source | Compressed size | Useful structure | Normalization priority |
| --- | ---: | --- | --- |
| `PainMonit.zip` | 923.5 MiB | Nested `PMED.zip` and `PMCD.zip`; synchronized CSVs with direct pain labels/rates | Clinical PMCD done |
| `PhysioPain Dataset.zip` | 1.2 GiB | E4 raw zips, processed watch data at 4/8/16/32/64 Hz, EEG, survey workbook | Next |
| `RheumaPain Dataset.zip` | 53.2 MiB | Processed E4-like CSVs at 4/8/16/32/64 Hz plus demographic workbook | Done first |

Disk is tight, so normalization is compressed-first:

- Keep source zips compressed.
- Write Parquet with ZSTD compression.
- Avoid duplicating every processed frequency unless needed.
- Treat 64 Hz as canonical for RheumaPain because it preserves BVP timing best.

## Completed

Created:

- [pain_normalizer.py](</Users/skyler/Downloads/pain datasets/pain_normalizer.py:1>)
- `_normalized/source_inventory.json`
- `_normalized/rheumapain/frequency_hz=64/measurement_stream.parquet`
- `_normalized/rheumapain/frequency_hz=64/labels.parquet`
- `_normalized/rheumapain/frequency_hz=64/subjects.parquet`
- `_normalized/rheumapain/frequency_hz=64/manifest.json`
- `_normalized/painmonit/clinical/measurement_stream.parquet`
- `_normalized/painmonit/clinical/labels.parquet`
- `_normalized/painmonit/clinical/subjects.parquet`
- `_normalized/painmonit/clinical/manifest.json`
- `_normalized/window_features/target_hz=1/window_features.parquet`
- `_normalized/window_features/target_hz=1/window_features.manifest.json`
- `_normalized/self_supervised/exploratory_1hz_30s/`
- `_normalized/self_supervised/exploratory_1hz_30s_no_metadata/`
- [pain_feeder.py](</Users/skyler/Downloads/pain datasets/pain_feeder.py:1>)
- [pain_self_supervised.py](</Users/skyler/Downloads/pain datasets/pain_self_supervised.py:1>)
- [PAIN_FEEDER_SPEC.md](</Users/skyler/Downloads/pain datasets/PAIN_FEEDER_SPEC.md:1>)
- [SELF_SUPERVISED_EXPLORATION_SUMMARY.md](</Users/skyler/Downloads/pain datasets/SELF_SUPERVISED_EXPLORATION_SUMMARY.md:1>)

RheumaPain normalized outputs:

| Output | Rows | Size |
| --- | ---: | ---: |
| `measurement_stream.parquet` | 1,387,231 | 34 MiB |
| `labels.parquet` | 42 | 12 KiB |
| `subjects.parquet` | 42 | 4 KiB |

PainMonit PMCD clinical normalized outputs:

| Output | Rows | Size |
| --- | ---: | ---: |
| `measurement_stream.parquet` | 2,969,065 | 137 MiB |
| `labels.parquet` | 90 | 14 KiB |
| `subjects.parquet` | 49 | 7 KiB |

Model feeder output:

| Output | Rows | Columns | Size |
| --- | ---: | ---: | ---: |
| `target_hz=1/window_features.parquet` | 32,981 | 201 | 11 MiB |

Feeder semantics:

- One output row per prediction anchor.
- Current cadence: 1 Hz.
- Current feature window: trailing 30 seconds.
- Features are computed from native samples before the row is emitted, rather than downsampling raw high-frequency streams to 1 Hz first.
- Baseline z-score/delta features are appended when an explicit rest/baseline condition exists; raw features are preserved.

Self-supervised exploration:

| Run | Purpose | Output |
| --- | --- | --- |
| Basic metadata | Sensor reconstruction, next-window prediction, contrastive probe with allowed metadata | `_normalized/self_supervised/exploratory_1hz_30s` |
| No metadata | Same probes with dataset/protocol metadata excluded | `_normalized/self_supervised/exploratory_1hz_30s_no_metadata` |

Key result: metadata-off contrastive results remain strongly dataset-separated (`top1_same_dataset_rate` about 0.999), so device/sensor/protocol structure itself is a dominant axis. Downstream models need dataset/session balancing plus sensor-subset evaluation.

RheumaPain normalized schema:

```text
dataset_id
source_archive
source_member
subject_id
session_id
condition
device
sample_rate_hz
sample_index
sample_offset_s
bvp
eda
acc_x
acc_y
acc_z
temperature
pain_score
pain_scale_type
diagnosis
sex
age
```

PainMonit PMCD clinical normalized schema:

```text
dataset_id
source_archive
nested_archive
source_member
subject_id
session_id
session_number
condition
record_type
device
sample_rate_hz
sample_index
sample_offset_s
bvp
eda_e4
temperature
respiration
eda_rb
bvp_rb
emg
grip
pain_rate_nrs
pain_label
pain_scale_type
no_pain_threshold
severe_pain_threshold
```

Label handling:

- Label type: `pain_wong_baker`.
- Demographics and canonical labels come from `patients.xlsx`.
- Per-sample `pain_score` remains in `measurement_stream`.
- Session-level `labels.label_value` is set only when the workbook/session has one clear value.
- Two exercise sessions have multi-value labels and are marked `ambiguous_multi_value_session`; their session-level `label_value` is null, but their per-sample `pain_score` values are preserved.

RheumaPain label policy counts:

| Policy | Sessions |
| --- | ---: |
| `single_workbook_value` | 40 |
| `ambiguous_multi_value_session` | 2 |

Subject metadata:

- 42 subjects.
- Sex from workbook: 31 female, 11 male.
- Age range: 5-18.
- Top diagnoses: JIA, rheumatoid arthritis, scoliosis, oligoarticular JIA.

PainMonit label handling:

- Label type: `pain_nrs_timeseries`.
- Per-sample `pain_rate_nrs` and `pain_label` remain in `measurement_stream`.
- Session-level `labels` rows summarize observed pain-rate range, non-null label count, observed categorical labels, and subject-specific no-pain/severe-pain thresholds from the text files.
- PMCD clinical main files are normalized now. PMCD run-up files and PMED experimental heat-pain files remain unnormalized for the next pass.

## Gateway Status

The web gateway is running locally at:

```text
http://127.0.0.1:8767
```

Ports `8765` and `8766` may still have older gateway processes; use `8767` for the current table set.

The gateway exposes normalized RheumaPain and PainMonit tables:

```text
rheumapain_64hz
rheumapain_labels
rheumapain_subjects
painmonit_clinical
painmonit_labels
painmonit_subjects
pain_windows_1hz_30s
```

Current verified gateway counts:

```text
tables: 16
archives: 12
members: 4632
```

Example queries:

```bash
curl 'http://127.0.0.1:8767/api/preview/rheumapain_64hz?subject_id=s001&limit=3'
curl 'http://127.0.0.1:8767/api/preview/rheumapain_labels?limit=5'
curl 'http://127.0.0.1:8767/api/preview/painmonit_clinical?subject_id=p01&limit=3'
curl 'http://127.0.0.1:8767/api/preview/painmonit_labels?limit=5'
curl 'http://127.0.0.1:8767/api/preview/pain_windows_1hz_30s?dataset_id=painmonit&limit=5'
```

## PainMonit Findings

`PainMonit.zip` contains:

```text
painmonit_dua.pdf
PMCD.zip
PMED.zip
```

PMED:

- 52 synchronized experimental CSVs.
- About 3.1 GiB uncompressed CSV payload.
- About 19.1M rows estimated.
- Columns:
  - `Seconds`
  - `Bvp`
  - `Eda_E4`
  - `Tmp`
  - `Ibi`
  - `Hr`
  - `Resp`
  - `Eda_RB`
  - `Ecg`
  - `Emg`
  - `Heater [C]`
  - `COVAS`
  - `Heater_cleaned`

PMCD:

- 90 clinical main CSVs and 90 run-up CSVs.
- 49 participants observed by participant prefix.
- About 288 MiB uncompressed CSV payload.
- About 3.8M rows estimated.
- Columns:
  - `Seconds`
  - `Bvp`
  - `Eda_E4`
  - `Tmp`
  - `Resp`
  - `Eda_RB`
  - `Bvp_RB`
  - `Emg`
  - `Grip`
  - `Pain rates`
  - `Pain labels`

PainMonit parsing requirements:

- Semicolon delimiter.
- Decimal comma.
- Nested zip streaming.
- Preserve both continuous pain rates and categorical pain labels.
- PMCD clinical main CSVs are now normalized; run-up CSVs are intentionally deferred.

## PhysioPain Findings

PhysioPain has multiple duplicate processed frequencies. Do not ingest all copies first.

Recommended first-pass choices:

- Watch: `combined_all_data/all_watch_data_64hz.csv` for best BVP fidelity, or 16 Hz if disk pressure becomes more important than pulse morphology.
- EEG: merged processed EEG at 4 Hz after watch data is stable.
- Survey workbook: normalize into subject/label covariate table.

Observed processed watch combined products:

| Frequency | Files | Estimated rows | Payload |
| ---: | ---: | ---: | ---: |
| 4 Hz | 8 | 1.47M | 130 MiB |
| 8 Hz | 8 | 2.98M | 261 MiB |
| 16 Hz | 8 | 5.91M | 521 MiB |
| 32 Hz | 8 | 11.70M | 582 MiB |
| 64 Hz | 8 | 24.25M | 2.04 GiB |

Representative processed watch columns:

```text
bvp, eda, x, y, z, temperature, pain_scale, pain_type, person_id
```

Representative processed EEG columns:

```text
Delta, Theta, Alpha1, Alpha2, Beta1, Beta2, Gamma1, Gamma2,
Attention, Meditation, pain_version, pain_intensity, person_id
```

Survey workbook:

- 99 rows.
- 108 columns.
- Contains demographic fields, pain type, and many pain severity questions.

## Next Work

1. Add `normalize-physiopain-watch` command:
   - Default to 64 Hz if disk allows.
   - Add `--frequency` option.
   - Normalize survey workbook into subject labels/covariates.
2. Add feeder reconstruction products for a light self-supervised phase:
   - Sensor-block dropout.
   - Per-sensor reconstruction targets.
   - Residual features appended to `pain_windows_*`.
3. Add optional PainMonit PMED normalization:
   - Experimental heat-pain stream.
   - Preserve `COVAS`, heater temperature, ECG, IBI, HR, EDA, BVP, respiration, EMG.
4. Add optional PainMonit PMCD run-up normalization if baseline windows are useful.
