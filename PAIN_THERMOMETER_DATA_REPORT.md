# Pain Thermometer Data Readiness Report

Date: 2026-04-29
Root path: `/Users/skyler/Downloads/pain datasets`
Gateway: `pain_gateway_server.py`

## 1. Executive Finding

The files are strong for building a multi-device physiological arousal and stress representation, but they are not yet sufficient to train a true supervised pain score by themselves. Across the local datasets, the available targets are mostly task state, emotion state, activity state, stress self-report, and valence/arousal/dominance surveys. I did not find a direct pain intensity label such as VAS, NRS 0-10, pain/no-pain event, medication response, or clinician annotation in the inspected files.

That means the correct path is:

1. Use these datasets to normalize sensors, learn robust per-person baselines, learn device-invariant physiology features, and pretrain a state representation.
2. Treat stress, emotion, exercise, and task labels as proxy/auxiliary objectives, not as pain labels.
3. Add or connect a pain-labeled dataset before calling the output a pain thermometer.
4. Train the final pain score with missing-modality support so a device with only EDA+HR, HR+ACC, ECG+respiration, or just HR can still produce a calibrated lower-confidence score.

The best first product is a "physiological distress / autonomic activation score" with a pain-label-ready schema. It can become a pain thermometer once pain labels are attached.

## 2. Queries and Local Checks Run

The gateway was used for live row access from compressed files:

```text
GET /api/tables
GET /api/members?limit=20
GET /api/preview/catsa?subject_id=Sub1&condition=Baseline&sensor=EDA&limit=3
GET /api/preview/wesad?subject_id=S10&sensor=EDA&limit=5
POST /api/query {"sql":"select * from wearable_sports_health limit 2"}
```

Archive-aware Python scans were also run directly against zip central directories and streamed file members. No archives were extracted. The direct scans produced:

- Dataset, subject, condition, device, and sensor coverage.
- Estimated row counts by sensor group.
- Label distribution for `merged_wearable_stress`.
- Activity distribution for `wearable_sports_health`.
- Stress-level summaries for the induced stress/exercise dataset.
- SAM label summaries for EPM-E4.
- WESAD questionnaire and RespiBAN header inspection.

## 3. High-Level Dataset Comparison

| Dataset/table | Subjects | Main devices | Main sensors | State/label type | Pain-label readiness |
| --- | ---: | --- | --- | --- | --- |
| `catsa` | 50 | Empatica-like wrist | ACC, BVP, EDA, HR, TEMP | Baseline, Logic, Stroop, Sudoku | Proxy only |
| `epm_e4` | 47 raw, 45 clean preprocessed | Empatica E4, Muse | ACC, BVP, EDA, HR, IBI, TEMP, EEG/bands | Fear, anger, sadness, happiness, neutral, SAM valence/arousal | Proxy only |
| `wesad` | 15 | Empatica E4, RespiBAN | ACC, BVP, EDA, HR, IBI, TEMP, ECG, EMG, respiration, chest motion | Protocol stages in questionnaire/PKL, event tags | Strong physiology, no direct pain |
| `merged_wearable_stress` | 15 IDs | likely E4-derived | ACC XYZ, EDA, HR, TEMP | Numeric label 0/1/2 | Proxy only unless label mapping is pain, not shown |
| `induced_stress_exercise` | 41 IDs total, 100 sessions | Empatica E4 | ACC, BVP, EDA, HR, IBI, TEMP | Activity protocol and self-reported stress | Proxy only |
| `sample_27_9vuw` | 1 | E4, BH3, back/front/water IMUs | ACC, gyro, BVP, EDA, HR, IBI, skin temp, ECG, respiration | Markers, surveys, valence/arousal/dominance | Useful schema prototype, too few subjects |
| `wearable_sports_health` | synthetic-looking athlete IDs | generic wearable | HR, body temp, BP, SpO2, steps, location | Activity status | Weak for pain |
| `subject_info_catsa` | 50 | metadata | demographics | demographics | Useful for covariates |
| `questionnaire` | 49 | metadata | demographics/lifestyle | questionnaire context | Useful for covariates |

## 4. Sensor Coverage Matrix

| Sensor family | Signals seen | Datasets | Pain-thermometer utility |
| --- | --- | --- | --- |
| Cardiac rate | HR | CATSA, EPM-E4, WESAD, induced stress/exercise, sample, sports | Core feature, but not pain-specific alone |
| Pulse waveform | BVP/PPG | CATSA, EPM-E4, WESAD, induced stress/exercise, sample | Core for HRV/pulse amplitude if quality is sufficient |
| Beat intervals | IBI, RR | EPM-E4, WESAD, induced stress/exercise, sample | Strong for HRV; best cardiac feature family |
| Electrical cardiac | ECG | WESAD RespiBAN, sample BH3 | Strong for HRV and artifact-resistant cardiac metrics |
| Electrodermal | EDA | CATSA, EPM-E4, WESAD, induced stress/exercise, sample | Strong autonomic arousal signal; useful for pain proxy |
| Temperature | TEMP, SKT, body temp | CATSA, EPM-E4, WESAD, induced stress/exercise, sample, sports | Useful as slow autonomic/peripheral response |
| Motion | ACC, gyro, steps, activity | all major signal datasets | Required confounder control; movement can mimic pain physiology |
| Respiration | RESP/RSP/BR | WESAD RespiBAN, sample BH3 | Very useful for distress and pain coping patterns |
| Muscle | EMG | WESAD RespiBAN | Potentially useful for guarding/tension |
| EEG | Muse bands/raw | EPM-E4 | Useful experimentally; not required for first wearable model |
| Blood oxygen/BP | SpO2, BP | sports CSV only | Potentially useful, but dataset is weak and likely synthetic |

Minimum useful device packs:

| Device pack | Expected score quality |
| --- | --- |
| EDA + HR/BVP + ACC + TEMP | Best common wrist configuration |
| HR/IBI + ACC | Usable low-confidence score |
| ECG + respiration + ACC | Strong chest-band configuration |
| EDA only | Weak, high false positives from stress/heat |
| HR only | Weak, should output low confidence |
| ACC only | Not a pain score; only context/activity gating |

## 5. Dataset Profiles

### 5.1 CATSA

Structure:

```text
CATSA/{subject_id}/{condition}/{sensor}.csv
```

Coverage:

- Subjects: 50.
- Conditions: `Baseline`, `Logic`, `Stroop`, `Sudoku`.
- Sensor files: 200 files each for ACC, BVP, EDA, HR, TEMP.
- Timestamp style: relative offset only, no absolute start time.

Estimated rows by sensor:

| Sensor | Estimated rows |
| --- | ---: |
| ACC | 1,152,000 |
| BVP | 2,304,000 |
| EDA | 144,000 |
| HR | 35,977 |
| TEMP | 144,000 |

Model value:

- Good for baseline-normalization and cognitive-stress discrimination.
- Strong because each subject has a baseline plus multiple task states.
- Weak for pain because labels are cognitive tasks, not pain.

Recommended use:

- Build baseline-relative features per subject.
- Treat `Baseline` as within-subject rest reference.
- Treat `Logic`, `Stroop`, and `Sudoku` as non-pain cognitive/autonomic activation states.

### 5.2 EPM-E4

Structure:

```text
EPM-E4/key_moments/{emotion}.csv
EPM-E4/questionnaires/{raw,preprocessed}/...
EPM-E4/empatica_wearable_data/raw/{subject}/empatica/{sensor}.csv
EPM-E4/empatica_wearable_data/raw/{subject}/muse/{emotion}_mindMonitor_*.csv
EPM-E4/empatica_wearable_data/preprocessed/{clean,unclean}/empatica_slices/.../{subject}/{condition}.csv
```

Coverage:

- Raw subjects: 47.
- Raw Empatica subjects: 47.
- Raw Muse subjects: 47.
- Clean preprocessed Empatica subjects: 45.
- Unclean preprocessed Empatica subjects: 33.
- Emotion conditions: `FEAR`, `ANGER`, `SADNESS`, `HAPPINESS`.
- Neutral windows: `NEUTRAL_FEAR`, `NEUTRAL_ANGER`, `NEUTRAL_SADNESS`, `NEUTRAL_HAPPINESS`.

Estimated rows by group:

| Group | Files | Estimated rows |
| --- | ---: | ---: |
| Raw Muse EEG | 188 | 13,809,431 |
| Raw BVP | 47 | 4,944,010 |
| Raw ACC | 47 | 2,481,599 |
| Raw EDA | 47 | 309,810 |
| Raw TEMP | 47 | 309,744 |
| Raw HR | 47 | 77,015 |
| Raw IBI | 47 | 75,912 |
| Clean preprocessed Empatica 128 Hz | 356 | 6,279,402 |
| Unclean preprocessed Empatica 128 Hz | 264 | 4,719,053 |

Observed labels:

- SAM preprocessed rows: 188.
- Emotions: 47 each for `ANGER`, `FEAR`, `HAPPINESS`, `SADNESS`.
- VALENCE range: 1 to 9, mean 3.37.
- AROUSAL range: 1 to 9, mean 6.29.
- Video order patterns: 24 subjects `HAPPINESS,SADNESS,ANGER,FEAR`; 23 subjects `FEAR,SADNESS,ANGER,HAPPINESS`.

Model value:

- Very useful for learning high-arousal emotional physiology.
- Useful for learning neutral-vs-elicited state contrast.
- Muse EEG can be an optional high-dimensional branch, not a core dependency.

Pain risk:

- Fear/anger/sadness arousal can look physiologically similar to pain.
- Training directly on these as "pain" would create a stress/emotion detector, not a pain detector.

Recommended use:

- Auxiliary training task: classify emotion/neutral state.
- Pretrain robust EDA/BVP/HR/TEMP features.
- Use SAM arousal as a continuous auxiliary target.

### 5.3 WESAD

Structure:

```text
WESAD/{subject}/{subject}.pkl
WESAD/{subject}/{subject}_E4_Data.zip
WESAD/{subject}/{subject}_quest.csv
WESAD/{subject}/{subject}_readme.txt
WESAD/{subject}/{subject}_respiban.txt
```

Coverage:

- Subjects: 15.
- Nested E4 zip sensors: ACC, BVP, EDA, HR, IBI, TEMP, tags.
- RespiBAN text files: 15.
- RespiBAN uncompressed payload: about 3.47 GiB.
- RespiBAN estimated rows: about 66.1M.
- PKL payload: about 12.88 GiB uncompressed.

Nested E4 estimated rows:

| Sensor | Files | Estimated rows |
| --- | ---: | ---: |
| ACC | 15 | 3,400,474 |
| BVP | 15 | 6,865,709 |
| EDA | 15 | 427,764 |
| HR | 15 | 106,804 |
| IBI | 15 | 47,100 |
| TEMP | 15 | 427,736 |

RespiBAN header shows:

```text
ECG, EDA, EMG, TEMP, XYZ, XYZ, XYZ, RESPIRATION
sampling rate: 700 Hz
```

Questionnaire files include protocol timing rows:

```text
# ORDER;Base;Fun;Medi 1;TSST;Medi 2;...
# START;...
# END;...
```

Model value:

- Best dataset here for chest-band physiology.
- RespiBAN adds ECG, respiration, EMG, and chest motion, which are all useful for pain-adjacent physiology.
- Protocol has baseline, amusement, stress, meditation, and reading stages.

Pain risk:

- Still no direct pain label.
- The PKL likely contains synchronized labels, but the gateway currently avoids PKL internals because they are huge.

Recommended use:

- Parse `*_quest.csv` timing rows and join them to E4/RespiBAN streams.
- Stream RespiBAN text into compressed Parquet partitions.
- Leave PKL parsing as optional, one subject at a time.

### 5.4 Merged Wearable Stress

Source:

```text
archive(2).zip/merged_data.csv
```

Columns:

```text
X, Y, Z, EDA, HR, TEMP, id, datetime, label
```

Exact streamed count:

- Rows: 11,509,051.
- Subjects/IDs: 15.
- Labels:
  - `2.0`: 8,540,583 rows.
  - `0.0`: 2,162,246 rows.
  - `1.0`: 806,222 rows.

Model value:

- Already close to a deployable wrist-wearable feature table.
- Good candidate for first end-to-end classifier pipeline because it has aligned ACC, EDA, HR, TEMP, datetime, subject id, and label.

Pain risk:

- Label meaning is not documented in the file itself.
- It should be treated as a stress/state label until externally mapped.

Recommended use:

- Use as first benchmark for model plumbing.
- Validate label mapping before using it as target semantics.
- Use subject-wise train/test split.

### 5.5 Induced Stress and Structured Exercise

Structure:

```text
Wearable_Dataset/{AEROBIC,ANAEROBIC,STRESS}/{subject}/{ACC,BVP,EDA,HR,IBI,TEMP,tags}.csv
Stress_Level_v1.csv
Stress_Level_v2.csv
subject-info.csv
```

Coverage:

- Total subject IDs observed: 41.
- AEROBIC sessions: 31 subjects.
- ANAEROBIC sessions: 32 subjects.
- STRESS sessions: 37 subjects.
- 100 files each for ACC, BVP, EDA, HR, IBI, TEMP, tags.

Estimated rows by activity/sensor:

| Activity | ACC | BVP | EDA | HR | IBI | TEMP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AEROBIC | 2,093,976 | 4,260,312 | 263,292 | 65,546 | 25,375 | 263,360 |
| ANAEROBIC | 1,597,583 | 3,215,406 | 200,142 | 49,744 | 17,850 | 200,176 |
| STRESS | 2,962,341 | 5,942,620 | 372,096 | 92,665 | 68,122 | 372,000 |

Stress self-report summaries:

| Protocol stage | V1 mean | V2 mean | Interpretation |
| --- | ---: | ---: | --- |
| Baseline | 3.44 | 3.28 | Rest reference |
| TMCT | 5.08 | 6.39 | Strong stress target |
| First Rest | 3.22 | 2.61 | Recovery/reference |
| Real Opinion | 4.14 | 3.56 | Moderate stress |
| Opposite Opinion | 4.31 | 4.17 | Moderate stress |
| Subtract | 4.53 | 4.56 | Stress target |

Model value:

- Excellent for separating exercise physiology from stress physiology.
- Important negative control: pain score must not simply become "heart rate went up because exercise."

Recommended use:

- Train activity-aware nuisance/confounder branch.
- Use stress self-report as continuous auxiliary target.
- Include aerobic/anaerobic as hard negatives for pain-distress modeling.

### 5.6 Sample 27-9VUW

Coverage:

- Subjects: 1.
- Devices: back, front, water, E4, BH3.
- Sensors: ACC, gyro, BVP, EDA, HR, IBI, skin temp, ECG, respiration, breath rate, RR, HR confidence.
- Survey rows: 38.
- Marker rows: 49.

Estimated rows by major signal group:

| Group | Estimated rows |
| --- | ---: |
| front_acc | 8,109,901 |
| front_gyro | 7,564,607 |
| back_acc | 6,553,148 |
| water_acc | 6,449,442 |
| water_gyro | 5,825,542 |
| back_gyro | 5,363,803 |
| bh3_ecg | 1,604,373 |
| bh3_acc | 721,625 |
| e4_bvp | 415,895 |
| e4_acc | 211,172 |
| bh3_rsp | 174,827 |
| e4_eda | 26,091 |
| e4_skt | 26,056 |
| e4_hr | 6,423 |

Model value:

- Useful for schema design and multi-device alignment.
- Not enough subjects for generalization.
- Strong prototype for multimodal windows and survey alignment.

Pain risk:

- No direct pain label.
- Single subject can badly overfit.

## 6. Cross-Dataset Normalized Sensor Schema

The model should not train directly on raw file rows. It should train on windows. Recommended normalized tables:

### `measurement_stream`

Long-form raw/near-raw table:

```text
dataset_id
source_member
subject_id
session_id
condition
device
sensor
sample_time_utc
sample_offset_s
sample_rate_hz
x
y
z
value
quality
payload_json
```

### `window_features`

One row per subject/session/window/device availability:

```text
subject_id
session_id
window_start
window_end
condition
label_proxy
pain_label
available_modalities
missingness_mask
baseline_reference_id
features_json
```

### `labels`

Explicit target table:

```text
subject_id
session_id
label_time
label_start
label_end
label_type
label_value
label_source
confidence
```

For the final pain thermometer, `label_type` should include direct pain labels such as:

- `pain_nrs_0_10`
- `pain_vas_0_100`
- `pain_present`
- `flare_event`
- `analgesic_event`
- `clinician_observed_pain`

The current files mostly provide:

- `task_condition`
- `emotion`
- `stress_self_report`
- `activity_status`
- `valence`
- `arousal`
- `dominance`

## 7. Baseline Normalization Strategy

Pain scoring must be person-relative. Raw HR, EDA, temp, and movement differ too much across people.

Recommended baseline levels:

1. Subject baseline: median/MAD from known rest/baseline windows.
2. Session baseline: first stable rest segment when explicit baseline exists.
3. Rolling baseline: recent low-activity windows when no explicit baseline exists.
4. Population fallback: only when the user is new and no baseline exists.

Recommended transforms:

```text
robust_z = (feature - subject_baseline_median) / (1.4826 * subject_baseline_mad + epsilon)
delta = feature - subject_baseline_median
percent_delta = delta / max(abs(subject_baseline_median), epsilon)
rolling_delta = feature - rolling_15min_median
```

Baseline anchors by dataset:

| Dataset | Baseline source |
| --- | --- |
| CATSA | `Baseline` condition |
| WESAD | `Base` timing row in `*_quest.csv`; PKL labels if enabled |
| Induced stress/exercise | `Baseline` columns in stress-level files and session starts |
| EPM-E4 | neutral windows and key moments |
| sample_27_9VUW | marker files and survey phases |
| merged_wearable_stress | infer from label mapping after documentation |

## 8. Window Feature Specification

Use overlapping windows, not individual samples.

Recommended window sizes:

- 10 seconds: fast response and high-rate sensors.
- 30 seconds: primary real-time pain score window.
- 60 seconds: stable score window.
- 5 minutes: baseline and trend context.

Feature groups:

### Cardiac

- HR mean, median, slope, variability.
- IBI/RR RMSSD.
- IBI/RR SDNN.
- pNN50 when sample count supports it.
- BVP amplitude summary.
- BVP-derived pulse rate confidence when available.

### EDA

- Tonic level median.
- Tonic slope.
- Phasic peak count.
- Phasic peak amplitude.
- EDA derivative stats.
- Recovery time after peaks.

### Temperature

- Median skin temperature.
- Delta from baseline.
- Slope over 30/60/300 seconds.
- Peripheral cooling/warming trend.

Wrist, skin, and body temperature are in scope as physiological sensors. Thermal video is a separate visual modality and should stay out of first-pass ingestion.

### Motion

- ACC magnitude mean/std.
- Jerk.
- Posture/orientation proxy.
- Step/activity intensity when present.
- Gyro magnitude for sample dataset.

Motion should be a confounder control, not a direct pain feature.

### Respiration

- Respiration rate.
- Rate variability.
- Breath amplitude.
- Irregularity.
- Breath-holding or shallow breathing proxies.

### ECG

- R-peak-derived HR.
- HRV features.
- Signal quality.
- Potential EMG contamination flag.

### EEG/Muse

- Band powers by channel.
- Raw channel quality/headband status.
- Use as optional branch only.

### Out-of-Scope First-Pass Visual Modalities

- RGB facial video.
- Depth video.
- Thermal video.
- Audio.

These can be added later, but the first pain thermometer should prioritize wearable physiology: EDA, HR/BVP/IBI/ECG, temperature, motion, respiration, and EMG.

## 9. Model Strategy

The model should be missing-modality aware from the beginning.

Recommended first architecture:

1. Build per-window feature vectors.
2. Add a binary missingness mask for each feature group.
3. Train auxiliary heads for:
   - stress/task/emotion classification,
   - activity classification,
   - arousal regression,
   - subject/session normalization.
4. Train final pain head only when direct pain labels exist.

Recommended model families:

| Stage | Model | Reason |
| --- | --- | --- |
| First benchmark | LightGBM/XGBoost/CatBoost over window features | Robust with missing values and fast iteration |
| Missing-modality production | Late-fusion MLP or tabular transformer with modality masks | Handles variable devices |
| Sequence model | Temporal CNN/TCN or transformer over window embeddings | Smooths score over time |
| Calibration | Isotonic regression or Platt scaling per output | Needed for interpretable score |

Output contract:

```text
pain_score_0_100
score_confidence_0_1
dominant_drivers
available_modalities
baseline_quality
motion_confounding_flag
stress_confounding_flag
```

## 10. The Key Scientific Risk

Pain, stress, fear, anger, exercise, caffeine, sleep loss, and motion can all push the same wearable signals in similar directions. If these datasets are naively used as pain labels, the model will learn a generic arousal detector.

The solution is not to discard the data. The solution is to use it correctly:

- Use stress/emotion/exercise datasets as representation learning and negative/auxiliary tasks.
- Use direct pain-labeled windows for the supervised pain head.
- Include activity/exercise states so the model learns not to confuse exertion with pain.
- Include subject-specific baselines so high resting HR or high tonic EDA is not treated as pain.
- Split by subject, not by row, to avoid leakage.

## 11. Recommended Build Plan

### Phase 1: Normalize Signals to Windows

Deliver:

- Parquet/ZSTD `measurement_stream`.
- Parquet/ZSTD `window_features`.
- Baseline extraction for CATSA, induced stress/exercise, WESAD, and EPM neutral windows.
- Feature extraction for EDA, HR/BVP/IBI, TEMP, ACC, ECG, respiration.

### Phase 2: Proxy Model

Deliver:

- Classifier for stress/task/emotion/activity.
- Continuous arousal regressor where labels exist.
- Missing-modality training with simulated device dropout.
- Report of feature importance and confounders.

Expected output:

- `autonomic_arousal_score_0_100`
- Not yet a validated pain score.

### Phase 3: Pain-Labeled Dataset Attachment

Deliver:

- Import direct pain labels.
- Align labels to time windows.
- Decide label target: current pain, pain change, flare risk, or pain/no pain.
- Train subject-held-out supervised pain head.

### Phase 4: Pain Thermometer

Deliver:

- Calibrated score.
- Confidence score.
- Minimum sensor fallback behavior.
- Device capability matrix.
- Prospective validation plan.

## 12. Immediate Engineering Tasks

1. Add WESAD RespiBAN streaming parser. It is too useful to leave as text metadata.
2. Parse WESAD `*_quest.csv` protocol timings into structured condition intervals.
3. Convert repeated full-scan sources into Parquet/ZSTD partitions:
   - `merged_wearable_stress`
   - WESAD RespiBAN
   - EPM preprocessed Empatica
   - sample 27-9VUW large IMU files
4. Build a window feature extractor with configurable window sizes.
5. Create a `label_dictionary.md` that records exactly what each proxy label means.
6. Do not use `label=2.0` from `merged_data.csv` as pain until the source meaning is verified.

## 13. Bottom Line

The current data is sufficient to build the infrastructure and a strong physiology representation. It is not sufficient to honestly train a final pain thermometer without direct pain labels.

The right first milestone is a baseline-normalized, missing-modality-aware physiological state model. Once direct pain labels are attached, that model can become the pain thermometer with much less data than training from scratch.
