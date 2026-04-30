# Pain Dataset Expansion Recommendations

Date: 2026-04-29

This addendum ranks candidate public pain datasets for the "pain thermometer" project. The ranking is based on direct pain-label value, modality overlap with our existing compressed-file gateway, likely integration cost, and access friction.

## 1. Short Answer

Add these first:

1. PainMonit Dataset (PMD)
2. RheumaPain Dataset
3. PhysioPain Dataset
4. BioVid Heat Pain Database
5. SenseEmotion, if the physiological streams are accessible

Add later or as optional branches:

6. EmoPain@Home / EmoPain
7. UNBC-McMaster Shoulder Pain Expression Archive
8. MIntPAIN

The first five give us direct pain labels or controlled pain intensity labels with usable physiology. Wrist/body temperature is in scope and desirable. Thermal video is out of scope for now, alongside depth/RGB video-first branches.

## 2. Candidate Ranking

| Priority | Dataset | Why it matters | Main friction | Fit |
| ---: | --- | --- | --- | --- |
| 1 | PainMonit Dataset | Direct NRS 0-10 pain rates, no/moderate/severe labels, clinical + experimental parts, E4 + chest sensors | Data use agreement, semicolon/comma-decimal parsing | Excellent |
| 2 | RheumaPain | Empatica E4, rest/exercise, pediatric rheumatology patients, Wong-Baker pain labels | New 2026 dataset; inspect structure after download | Excellent |
| 3 | PhysioPain | 99 participants, 93 with physiology, pain types + McGill questionnaire, E4 + EEG | Pain labels are pain type/severity rather than dense time labels | Excellent |
| 4 | BioVid Heat Pain | Mature controlled heat-pain benchmark with pain intensity classes and biosignals | Non-commercial research agreement; official page says no EEG available | Very good |
| 5 | SenseEmotion | Heat pain + emotion context, SCL/ECG/EMG/respiration physiology | Access unclear; must confirm downloadable physiology streams | Good if physiology accessible |
| 6 | EmoPain@Home / EmoPain | Chronic pain in real movement; pain/protective behavior labels | Request by email; movement/body-first | Good |
| 7 | UNBC-McMaster | Strong facial pain labels, PSPI/FACS, clinical shoulder pain | Video/facial branch, not time-series physiology | Optional |
| 8 | MIntPAIN | RGB/depth/thermal-video electrical-stimulation pain levels | Visual-only; small sample size; EULA | Optional |

## 3. Dataset Notes

### 3.1 PainMonit Dataset

Best role:

- Primary supervised pain model seed.
- Bridge between controlled heat pain and naturalistic clinical physiotherapy pain.

Relevant structure:

- Two parts:
  - PMED: experimental heat-based pain.
  - PMCD: clinical physiotherapy pain.
- Time series are CSV streams.
- Signals are synchronized/resampled to 250 Hz.
- Experimental streams include timestamp, BVP from E4, EDA from E4, EDA from RespiBAN, skin temperature, IBI, HR, respiration, ECG, EMG, thermode temperature, and CoVAS.
- Clinical streams include timestamp, BVP, EDA, skin temperature, respiration, EMG, grip data, pain rates, and pain labels.
- Pain rates are NRS 0-10 values at timestamps.
- Pain labels are no pain, moderate pain, and severe pain classes.

Adapter impact:

- Add `PainMonitAdapter`.
- Parse semicolon-separated CSV with decimal comma.
- Preserve raw `pain_rate_nrs`.
- Preserve `pain_label_class` as 0/1/2.
- Build 4-second windows with 50% overlap to match the published clinical baseline.

Schema fit:

```text
dataset_id = painmonit
subject_id
session_id
source_part = PMED | PMCD
sample_time
sensor values: bvp_e4, eda_e4, eda_rb, temp, ibi, hr, resp, ecg, emg, grip
stimulus_temperature
covas
pain_rate_nrs
pain_label
```

Why it is first:

- It has exactly what the current local files lack: direct pain labels aligned to physiological streams.

### 3.2 RheumaPain Dataset

Best role:

- Primary real clinical wearable pain dataset once downloaded.
- Strong match to our existing E4 parser.

Relevant structure from the public description:

- Published 2026 on Mendeley Data.
- Pediatric rheumatology patients during treatment sessions.
- Empatica E4 signals: BVP, EDA, HR, IBI, TEMP, ACC.
- Rest and exercise conditions.
- Wong-Baker Faces Pain Rating Scale labels for both phases.
- Raw biosignal files plus processed/synchronized unified data.
- Demographic and clinical information included.

Adapter impact:

- Likely small incremental work because the source is E4-like.
- Add `RheumaPainAdapter`.
- Treat Wong-Baker labels as direct pain intensity labels, not proxies.
- Preserve phase: rest/exercise.

Schema fit:

```text
dataset_id = rheumapain
condition = rest | exercise
pain_scale_type = wong_baker_faces
pain_score
sensors = ACC, BVP, EDA, HR, IBI, TEMP
```

Why it is high priority:

- It is clinically grounded, directly labeled, and uses the same wrist sensors as much of our current data.

### 3.3 PhysioPain Dataset

Best role:

- Broad pain-type classifier and subject-level pain phenotype dataset.
- Good for pain vs no-pain and pain-type conditioning.

Relevant structure:

- 99 participants; 93 contributed real-time physiological data.
- Pain types: headache, menstrual pain, back/neck/waist pain, no pain.
- Devices: Empatica E4 wristband and NeuroSky MindWave Mobile EEG.
- Signals: EEG, EDA, BVP, HR, ACC, skin temperature.
- Includes McGill Pain Questionnaire and custom survey questions.
- Raw and processed data.
- Processed watch data are resampled into 4, 8, 16, 32, and 64 Hz variants.
- Data availability is Mendeley Data, DOI `10.17632/mf2cgph9cy.4`, CC BY 4.0.

Adapter impact:

- Add `PhysioPainAdapter`.
- Reuse E4 signal parsing for raw watch zips.
- Prefer processed combined files for first pass.
- Use `pain_type` and `pain_scale` as labels.
- Add survey/McGill responses into a subject-level label/covariate table.

Schema fit:

```text
dataset_id = physiopain
pain_type = no_pain | headache | menstrual_pain | back_neck_waist_pain
pain_scale
sensors = EEG, EDA, BVP, HR, ACC, TEMP
frequency_variant = 4 | 8 | 16 | 32 | 64
```

Limitation:

- This appears more subject/session-level than dense moment-by-moment pain. It should complement PainMonit, not replace it.

### 3.4 BioVid Heat Pain Database

Best role:

- Controlled pain-intensity benchmark.
- Excellent for pain/no-pain and pain-intensity class discrimination under experimental heat stimuli.

Important correction:

- The official BioVid page says EEG is not available. It lists GSR/EDA, ECG, and EMG plus frontal video. Do not plan an EEG branch around BioVid.

Relevant structure:

- Part A: 87 subjects, 5 classes, 20 samples per class/subject, 5.5-second windows, GSR/ECG/EMG and frontal video.
- Part B: 86 subjects, adds facial EMG.
- Part C: longer sequences with pain stimulus labels.
- Part D: posed pain and basic emotions.
- Part E: emotion elicitation.
- Official recommendation: leave-one-subject-out cross-validation.

Adapter impact:

- Access first; non-commercial research agreement required.
- Add `BioVidAdapter`.
- Treat stimulus classes T0-T4 as controlled pain-intensity labels.
- Use Part A/Part C first for physiology.

Schema fit:

```text
dataset_id = biovid
part = A | B | C | D | E
pain_stimulus_class = T0 | T1 | T2 | T3 | T4
sensors = GSR/EDA, ECG, EMG
window_duration_s = 5.5
```

Why it is not first:

- Access friction is higher than open Mendeley/Figshare-style datasets.

### 3.5 SenseEmotion

Best role:

- Pain vs emotion disambiguation using physiological streams.
- Important because the current local data has many stress/emotion proxies.

Relevant structure:

- 45 healthy subjects.
- About 30 minutes multimodal data per subject.
- Heat pain and affective image/sound emotion elicitation.
- Modalities include biopotentials, facial camera images, and audio.
- Physiological measures include SCL, ECG, EMG, and respiration.

Adapter impact:

- Access route must be confirmed.
- Add physiology parser if data files are available.
- Ignore camera/audio streams in the first pass unless we explicitly open a multimodal branch.
- Use as confounder dataset for distinguishing pain from emotional arousal.

Why it is now first-wave conditional:

- Its physiological channels are relevant to the pain thermometer and help separate pain from emotion/stress. It should move up if the downloadable files expose SCL/ECG/EMG/respiration cleanly.

### 3.6 EmoPain and EmoPain@Home

Best role:

- Chronic pain movement behavior.
- Protective behavior and function during real movement.
- Good for movement/body branch, not just autonomic physiology.

Relevant structure:

- EmoPain lab dataset includes people living with chronic pain and healthy controls.
- Body movement data from 18 IMUs.
- Four wireless sEMG sensors on upper/lower back.
- Expert annotations for protective behavior.
- EmoPain@Home includes pain, worry, and confidence labels during everyday home activities.

Adapter impact:

- Access request by email.
- Add movement-specific adapter.
- Align IMU/body windows with pain/protective behavior labels.

Why later:

- It is highly relevant clinically, but less aligned with the wrist physiological stack.

### 3.7 UNBC-McMaster Shoulder Pain Expression Archive

Best role:

- Facial pain branch.
- Model calibration against observed pain expressions.

Relevant structure:

- Publicly distributed portion has 200 video sequences from 25 subjects.
- 48,398 FACS-coded frames.
- Frame-level PSPI pain scores.
- Sequence-level self-report and observer measures.
- 66-point facial landmarks.

Adapter impact:

- Add only after deciding to support video/facial modalities.
- This does not plug into the current E4/physiology time-series gateway as cleanly.

Why optional:

- Excellent pain labels, but different sensor family.

### 3.8 MIntPAIN

Best role:

- Visual pain intensity branch.
- Electrical-stimulation controlled pain benchmark.

Relevant structure from available public descriptions:

- 20 subjects.
- RGB, depth, and thermal facial video.
- Pain levels 0-4.
- Electrical stimulation.

Adapter impact:

- Requires EULA/access handling.
- Add only if image/depth/thermal-video modeling becomes part of scope.

Why optional:

- Visual-only relative to the current physiological sensor goal. This is thermal video, not wrist/body temperature.

## 4. Integration Order

### Step 1: Add PainMonit

Reason:

- Direct NRS pain labels and clinical pain labels.
- Closest to the final supervised target.

Work:

- Download after accepting the data use agreement.
- Add semicolon/comma-decimal CSV parser.
- Build `painmonit_measurement_stream`.
- Build `painmonit_window_features`.
- Train first real pain classifier/regressor.

### Step 2: Add RheumaPain

Reason:

- Same E4 modality stack as current data.
- Direct pediatric clinical pain labels.

Work:

- Download from Mendeley.
- Inspect raw/processed structure.
- Reuse E4 parser.
- Add Wong-Baker labels to the `labels` table.

### Step 3: Add PhysioPain

Reason:

- Broad pain phenotype coverage and McGill survey labels.
- Good for pain type and severity conditioning.

Work:

- Download from Mendeley.
- Prefer processed 4/8/16/32/64 Hz CSVs for first pass.
- Add raw E4 and EEG branches later.

### Step 4: Add BioVid

Reason:

- Mature benchmark with controlled intensity labels.

Work:

- Complete access agreement.
- Use Part A or C first.
- Treat T0-T4 as controlled stimulus labels.

### Step 5: Add SenseEmotion if physiology files are obtainable

Reason:

- It provides heat pain under emotional context, which directly helps prevent the model from confusing pain with general affective arousal.
- Its SCL/ECG/EMG/respiration channels fit the physiological time-series stack.

Work:

- Confirm access and file structure.
- Parse physiology first.
- Defer facial video/audio unless a separate multimodal branch is approved.

## 5. Unified Label Taxonomy

Add these direct pain labels:

```text
pain_nrs_0_10
pain_wong_baker
pain_vas_0_100
pain_stimulus_class
pain_type
pain_present
pain_label_3class
pain_label_5class
protective_behavior
```

Keep these as proxy/auxiliary labels:

```text
stress_self_report
emotion
arousal
valence
task_condition
activity_condition
exercise_condition
movement_type
```

Do not mix direct pain labels and proxy labels into one undifferentiated target column.

## 6. Gateway Changes Needed

Add source adapters:

```text
PainMonitAdapter
RheumaPainAdapter
PhysioPainAdapter
BioVidAdapter
SenseEmotionAdapter
EmoPainAdapter
UnbcPainAdapter
MIntPainAdapter
```

Add output tables:

```text
pain_labels
pain_measurement_stream
pain_window_features
pain_subjects
pain_dataset_manifest
```

Adapter priority:

1. `PainMonitAdapter`
2. `RheumaPainAdapter`
3. `PhysioPainAdapter`
4. `BioVidAdapter`
5. `SenseEmotionAdapter`, if physiology files are available

## 7. Storage Estimate

Without downloads I cannot give exact sizes for every new dataset, but the likely storage strategy remains the same:

- Keep original zips/downloads compressed.
- Stream raw source files into compressed Parquet/ZSTD partitions.
- Avoid loading into PostgreSQL row stores.
- Use PostgreSQL/API only as a query gateway.

Expected impact:

| Dataset | Expected storage after compressed Parquet conversion |
| --- | ---: |
| PainMonit | moderate; likely a few GB depending raw streams |
| RheumaPain | likely small to moderate, E4-only |
| PhysioPain | moderate, due EEG + multi-frequency processed copies |
| BioVid | large if video included; moderate if physiology only |
| SenseEmotion | moderate if physiology only; large if video/audio included |
| EmoPain | large if video/body streams included |
| UNBC | video-heavy; keep outside physiology feature lake initially |
| MIntPAIN | video/depth/thermal-video-heavy |

## 8. Recommendation

The best supervised pain-training stack is:

```text
PainMonit + RheumaPain + PhysioPain + BioVid + SenseEmotion physiology
```

Use current local datasets as auxiliary/pretraining data:

```text
WESAD + CATSA + EPM-E4 + induced stress/exercise + sample_27_9VUW
```

Use video/movement datasets after the physiology pain model works:

```text
EmoPain@Home + UNBC + MIntPAIN
```

This avoids building a face/video/motion project before we have the core pain-labeled physiological model working.

Temperature instruction:

- Keep wrist/body/skin temperature as a first-class physiological channel.
- Exclude thermal video, RGB video, depth video, and audio from first-pass adapters unless explicitly approved.

## 9. Sources Checked

- PhysioPain Dataset, Mendeley Data: `https://data.mendeley.com/datasets/mf2cgph9cy/4`
- PhysioPain Data in Brief article: `https://doi.org/10.1016/j.dib.2025.111992`
- PainMonit Scientific Data article: `https://www.nature.com/articles/s41597-024-03878-w`
- PainMonit code repository: `https://github.com/gouverneurp/PMD`
- BioVid official page: `https://www.nit.ovgu.de/BioVid.html`
- EmoPain UCL page: `https://www.ucl.ac.uk/uclic/research/affective-computing/emopain-dataset`
- EmoPain@Home UCL page: `https://www.ucl.ac.uk/uclic/research/affective-computing/emopainhome-dataset`
- SenseEmotion paper page: `https://link.springer.com/chapter/10.1007/978-3-319-59259-6_11`
- UNBC-McMaster paper/reference: `https://sites.pitt.edu/~emotion/fulltext/2011/Painful_Data.pdf`
- RheumaPain Dataset, Mendeley Data: `https://data.mendeley.com/datasets/y6pgjdj22f/3`
