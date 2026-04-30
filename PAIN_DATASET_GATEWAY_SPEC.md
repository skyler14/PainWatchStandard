# Pain Dataset Local Gateway Specification

Status: active local implementation
Date: 2026-04-29
Root path: `/Users/skyler/Downloads/pain datasets`

## 1. Goal

Expose the local pain, stress, wearable, and physiology datasets through a temporary SQL gateway without creating a dedicated database file and without expanding the archives onto disk.

For the first version, "normalization" means each dataset can be exposed as its own logical table. We are not yet forcing all datasets into one universal physiology schema. The gateway should preserve enough metadata to make later cross-dataset normalization possible.

The current connector is a localhost HTTP/Web gateway because the immediate need is browser/web access to local compressed files. A PostgreSQL-compatible adapter remains a reasonable follow-on if the external tool requires PostgreSQL wire protocol. The storage layer remains local files, zip streams, and optional compressed Parquet/ZSTD cache partitions.

## 2. Hard Constraints

- Do not unzip archives into full expanded folders.
- Do not create a persistent database file as the system of record.
- Do not ingest all rows into PostgreSQL unless explicitly requested for a small table.
- Keep original files immutable and mounted/read in place.
- Any generated derived data must be compressed and bounded by a configured cache limit.
- Prefer streaming readers over extraction.
- If a format cannot be queried efficiently in place, stream it directly into compressed Parquet/ZSTD with the same logical hierarchy.
- Delete temporary scratch files at gateway shutdown unless the user explicitly asks for a reusable cache.

## 3. Gateway Choice

Chosen current connector: localhost HTTP/Web gateway.

Rationale:

- The current web gateway is running at `http://127.0.0.1:8767` and exposes JSON preview, NDJSON streaming, and a narrow SQL-like endpoint.
- MySQL and MariaDB are workable only if we run a real server and load tables, which pushes us toward disk-heavy ingestion.
- Snowflake and BigQuery would require uploading local files or derived data to cloud storage. That violates the local temporary goal for now.
- Weaviate is not a row-oriented analytic gateway.
- KX is strong for time-series, but it adds a specialized runtime and is not necessary for the first file-backed pass.
- PostgreSQL is still the best future fit among the picker options if a strict SQL connector is required.

Current endpoint contract:

- Base URL: `http://127.0.0.1:8767`
- Access: read-only
- CORS: enabled
- Lifecycle: started on demand, stopped when the temporary share is done

Future PostgreSQL endpoint contract, if needed:

- Host: `127.0.0.1`
- Port: `15432`
- Database: `pain_files`
- User: `pain_reader`
- SSL: disabled for local-only use

The server should bind to localhost by default. If the gateway must be shared to another machine, use an authenticated tunnel instead of binding directly to all interfaces.

## 4. Physical Inventory

The root folder is flat. It now contains ten zip archives, two top-level CSV files, generated docs/scripts, and compressed normalized outputs under `_normalized`.

| File | Compressed size | Observed contents | Notes |
| --- | ---: | --- | --- |
| `CATSA.zip` | 6.52 MiB | 1000 CSV files, 1 PDF | Clean hierarchy, no nested zips |
| `EPM-E4.zip` | 595.72 MiB | 2750 archive entries, 1246 useful clean files after skipping macOS metadata | Large raw and preprocessed Empatica/Muse dataset |
| `WESAD.zip` | 2145.24 MiB | 76 files, including 15 large PKL files and 15 nested E4 zips | Biggest expansion risk |
| `archive(1).zip` | 0.01 MiB | 1 CSV | Small sports health table |
| `archive(2).zip` | 76.18 MiB | 1 CSV | 11,509,051 data rows |
| `sample(1).zip` | 648.24 MiB | 25 normalized CSVs, 5 nested raw zips, 4 MAT files, 1 DB file | One subject/session package |
| `wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip` | 69.73 MiB | 704 E4 CSV files plus metadata/readme files | Clean Empatica-style hierarchy |
| `PainMonit.zip` | 923.5 MiB | Nested `PMCD.zip` and `PMED.zip`; semicolon/decimal-comma synchronized CSVs | PMCD clinical main normalized |
| `PhysioPain Dataset.zip` | 1.2 GiB | E4 raw zips, processed watch data at 4/8/16/32/64 Hz, EEG, survey workbook | Next direct-pain target |
| `RheumaPain Dataset.zip` | 53.2 MiB | Processed E4-like CSVs at 4/8/16/32/64 Hz plus demographic workbook | 64 Hz normalized |
| `Subject_info_CATSA.csv` | 1.2 KiB | 50 data rows | CATSA demographic metadata |
| `questionnaire.csv` | 7.7 KiB | 49 data rows | Questionnaire metadata, likely paired with `sample(1).zip` |

Approximate archive payload if recursively expanded: well over 35 GiB. The full expanded footprint is dominated by `WESAD.zip`, `EPM-E4.zip`, `sample(1).zip`, `PainMonit.zip`, and `PhysioPain Dataset.zip`, so full extraction should not be part of the gateway design.

## 5. Logical Tables for First Version

Expose these tables through the PostgreSQL gateway:

| Table | Source | First-pass shape |
| --- | --- | --- |
| `subject_info_catsa` | `Subject_info_CATSA.csv` | Headered CSV table |
| `questionnaire` | `questionnaire.csv` | Headered CSV table |
| `catsa` | `CATSA.zip` | One long-form dataset table over subject/task/sensor CSV members |
| `epm_e4` | `EPM-E4.zip` | One long-form dataset table over raw, preprocessed, questionnaire, and key-moment members |
| `wesad` | `WESAD.zip` | One long-form dataset table over nested E4 CSVs, questionnaires, readme metadata, and optional PKL-derived partitions |
| `wearable_sports_health` | `archive(1).zip` | Headered CSV table |
| `merged_wearable_stress` | `archive(2).zip` | Headered CSV table |
| `sample_27_9vuw` | `sample(1).zip` | One long-form dataset table over normalized CSV members |
| `induced_stress_exercise` | `wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip` | One long-form dataset table over activity/subject/sensor CSV members |
| `rheumapain_64hz` | `_normalized/rheumapain/frequency_hz=64/measurement_stream.parquet` | Direct-pain E4-like per-sample table |
| `rheumapain_labels` | `_normalized/rheumapain/frequency_hz=64/labels.parquet` | RheumaPain session labels |
| `rheumapain_subjects` | `_normalized/rheumapain/frequency_hz=64/subjects.parquet` | RheumaPain subject metadata |
| `painmonit_clinical` | `_normalized/painmonit/clinical/measurement_stream.parquet` | PainMonit PMCD clinical per-sample physiology and pain-rate table |
| `painmonit_labels` | `_normalized/painmonit/clinical/labels.parquet` | PainMonit PMCD session label summaries and thresholds |
| `painmonit_subjects` | `_normalized/painmonit/clinical/subjects.parquet` | PainMonit PMCD subject summaries |
| `pain_windows_1hz_30s` | `_normalized/window_features/target_hz=1/window_features.parquet` | Generalized model feeder table: 1 Hz prediction anchors over 30-second trailing native-sample windows |

The gateway should also expose metadata views:

| View | Purpose |
| --- | --- |
| `gateway_archives` | One row per top-level file/archive |
| `gateway_members` | One row per zip member or plain file |
| `gateway_tables` | Logical table names, source patterns, parser type, and cache status |
| `gateway_parse_errors` | Nonfatal parser issues, skipped files, malformed rows, unsupported payloads |

## 6. Common Metadata Columns

Every dataset table should include these columns where meaningful:

| Column | Type | Purpose |
| --- | --- | --- |
| `dataset_id` | text | Stable dataset key, for example `catsa`, `wesad` |
| `source_archive` | text | Top-level archive or CSV filename |
| `source_member` | text | Zip member path or plain filename |
| `source_crc32` | text | Zip central-directory CRC when available |
| `source_compressed_bytes` | bigint | Compressed member size |
| `source_uncompressed_bytes` | bigint | Uncompressed member size |
| `source_row_number` | bigint | Row number in the source member after metadata/header handling |
| `subject_id` | text | Subject identifier parsed from path/content |
| `session_id` | text | Session identifier when present |
| `condition` | text | Task, activity, emotion, or protocol condition |
| `device` | text | Device family, for example `empatica`, `muse`, `bh3`, `back`, `front`, `water` |
| `sensor` | text | Sensor/signal name, for example `ACC`, `EDA`, `BVP`, `HR`, `TEMP`, `IBI` |
| `sample_index` | bigint | Zero-based sample index within a signal stream |
| `sample_rate_hz` | double precision | Sampling frequency when known |
| `sample_offset_s` | double precision | Seconds since stream start when derivable |
| `sample_time_utc` | timestamp | Absolute timestamp when source gives one or it can be derived |
| `value` | double precision | Single numeric value when the source row has one primary value |
| `x` | double precision | X axis when applicable |
| `y` | double precision | Y axis when applicable |
| `z` | double precision | Z axis when applicable |
| `payload_json` | jsonb | All remaining source columns or irregular row content |

This lets every dataset table be queryable immediately while preserving original detail for later schema refinement.

## 7. Parser Types

### 7.1 Headered CSV

Used for ordinary CSV files with a header row.

Examples:

- `Subject_info_CATSA.csv`
- `questionnaire.csv`
- `archive(1).zip/wearable_sports_health_dataset.csv`
- `archive(2).zip/merged_data.csv`
- `sample(1).zip/csv/27-9VUW/*.csv`
- EPM Muse MindMonitor CSVs
- EPM preprocessed Empatica CSVs

Behavior:

1. Open the file or zip member as a stream.
2. Read the first row as headers.
3. Normalize header names to snake case for generated columns when the table is narrow and stable.
4. Preserve raw header names inside `payload_json`.
5. Add metadata columns from the archive path.

### 7.2 Empatica E4 Two-Line CSV

Used by raw Empatica E4 exports.

Format:

- Row 1: initial time of session.
- Row 2: sampling frequency in Hz.
- Rows 3 and later: samples.

Special cases:

- `ACC.csv`: row 1 and row 2 repeat across three columns; data rows are x, y, z.
- `BVP.csv`, `EDA.csv`, `HR.csv`, `TEMP.csv`: one value per sample row.
- `IBI.csv`: first row is start time plus `IBI`; no sample-rate row; data rows are offset seconds and interval duration seconds.
- `tags.csv`: event timestamps, often one per line or empty.

Timestamp derivation:

- If row 1 is a Unix timestamp, `sample_time_utc = to_timestamp(start_unix + sample_index / sample_rate_hz)`.
- If row 1 is an ISO-like UTC timestamp, parse it as UTC and add `sample_index / sample_rate_hz`.
- For `IBI.csv`, `sample_offset_s = first_column`, `value = second_column`, and `sample_time_utc = start_time + first_column`.
- For `tags.csv`, `sample_time_utc = parsed row timestamp`, `sensor = 'tags'`.

### 7.3 Headerless CATSA Signal CSV

CATSA signal CSVs have normal headers, but no absolute start time in the file.

Sampling rates from the CATSA README:

| Signal | Rate | File |
| --- | ---: | --- |
| `BVP` | 64 Hz | `BVP.csv` |
| `ACC` | 32 Hz | `ACC.csv` |
| `EDA` | 4 Hz | `EDA.csv` |
| `TEMP` | 4 Hz | `TEMP.csv` |
| `HR` | 1 Hz | `HR.csv` |

Timestamp behavior:

- `sample_time_utc` is null.
- `sample_index` is zero-based.
- `sample_offset_s = sample_index / sample_rate_hz`.

### 7.4 Nested Zip Member

Used by:

- `WESAD.zip/WESAD/S*/S*_E4_Data.zip`
- `sample(1).zip/raw/27-9VUW/*.zip`

Behavior:

1. Open outer zip member as a stream.
2. If the nested zip is small enough, read it into memory and open with `zipfile.ZipFile(BytesIO(...))`.
3. If it exceeds the memory threshold, stream it to a bounded temporary scratch file under `/tmp/pain_gateway` and remove it immediately after the member is processed.
4. Never extract the nested zip to a folder.

For first implementation:

- WESAD nested E4 zips are small enough to read into memory.
- `sample(1).zip` already contains normalized CSVs under `csv/27-9VUW`, so raw nested zips can be skipped until requested.

### 7.5 Pickle Blob

Used by:

- `WESAD.zip/WESAD/S*/S*.pkl`

Observed issue:

- The PKL files are very large. The largest observed uncompressed members are over 1 GiB each.
- Python pickle is not row-streamable in a useful SQL sense. It generally has to load the object graph.

First implementation behavior:

- Do not expose PKL internals by default.
- Expose PKL files as metadata rows in `gateway_members`.
- Prefer WESAD nested E4 CSVs for wrist signals.
- If chest/RespiBAN data from PKL is required, convert one subject at a time into compressed Parquet/ZSTD partitions, then query those partitions.

## 8. Dataset Architecture Details

### 8.1 `Subject_info_CATSA.csv`

Physical file:

- Path: `Subject_info_CATSA.csv`
- Lines: 51 total, 50 data rows.
- Delimiter: comma.

Columns:

- `SubjectID`
- `Gender`
- `Height`
- `Weight`
- `Age`

Gateway table:

- `subject_info_catsa`

Recommended normalized columns:

- `subject_id text`
- `gender text`
- `height_raw text`
- `weight_kg double precision`
- `age_years integer`
- `payload_json jsonb`

Height is stored in feet/inches text, for example `5'7"`, so keep the raw text and optionally add a later conversion column.

### 8.2 `questionnaire.csv`

Physical file:

- Path: `questionnaire.csv`
- Lines: 50 total, 49 data rows.
- Delimiter: comma.

Columns:

- `Code`
- `ID`
- `Age`
- `Gender`
- `Handedness`
- `Vision`
- `Vision aid`
- `Education`
- `Alcohol consumption`
- `Coffee consumption`
- `Tea consumption`
- `Tobacco consumption`
- `Other drug/medication consumption`
- `Normal hours of sleep`
- `Hours of sleep last night`
- `Level of Alertness`
- `Physical/psychiatric syndroms`

Gateway table:

- `questionnaire`

Recommended behavior:

- Preserve source spelling in `payload_json`, including the typo `syndroms`.
- Add snake-case aliases for common filters, for example `age_years`, `gender`, `handedness`, `education`, and `level_of_alertness`.

### 8.3 `CATSA.zip`

Physical archive:

- Archive size: 6.52 MiB.
- Useful files: 1000 CSV files plus `CATSA/README_CATSA.pdf`.
- Uncompressed CSV/PDF payload: 32.89 MiB.
- Top-level root: `CATSA/`.
- Subjects: 50.
- Subject IDs: `Sub1` through `Sub53` with some missing IDs.
- Tasks: `Baseline`, `Logic`, `Stroop`, `Sudoku`.
- Sensors: `ACC`, `BVP`, `EDA`, `HR`, `TEMP`.

Path pattern:

```text
CATSA/{subject_id}/{task}/{sensor}.csv
```

Examples:

```text
CATSA/Sub1/Baseline/ACC.csv
CATSA/Sub1/Logic/BVP.csv
CATSA/Sub1/Stroop/EDA.csv
CATSA/Sub1/Sudoku/TEMP.csv
```

Observed member counts:

| Dimension | Count |
| --- | ---: |
| Subjects | 50 |
| Tasks per subject | 4 |
| Sensor CSVs per task | 5 |
| Total signal CSVs | 1000 |

Observed CSV schemas:

| Sensor | Header | Value mapping |
| --- | --- | --- |
| `ACC` | `ACC_X,ACC_Y,ACC_Z` | `x`, `y`, `z` |
| `BVP` | `BVP` | `value` |
| `EDA` | `EDA` | `value` |
| `HR` | `HR` | `value` |
| `TEMP` | `TEMP` | `value` |

Gateway table:

- `catsa`

Recommended columns:

- Common metadata columns from Section 6.
- `task text` alias of `condition`.
- `acc_x double precision`
- `acc_y double precision`
- `acc_z double precision`
- `bvp double precision`
- `eda double precision`
- `hr double precision`
- `temp double precision`

Because CATSA files have no absolute start time, `sample_time_utc` should be null and `sample_offset_s` should be generated from the known sensor rate.

Example query:

```sql
select subject_id, condition, sensor, sample_offset_s, x, y, z
from catsa
where subject_id = 'Sub1'
  and condition = 'Baseline'
  and sensor = 'ACC'
limit 1000;
```

### 8.4 `EPM-E4.zip`

Physical archive:

- Archive size: 595.72 MiB.
- Original entries: 2750.
- Clean useful files after skipping `__MACOSX`, `._*`, and `.DS_Store`: 1246.
- Uncompressed useful payload: about 8130.6 MiB.
- Major folders:
  - `EPM-E4/readme.txt`
  - `EPM-E4/key_moments/`
  - `EPM-E4/questionnaires/`
  - `EPM-E4/empatica_wearable_data/raw/`
  - `EPM-E4/empatica_wearable_data/preprocessed/`

Skip rules:

- Ignore every member under `__MACOSX/`.
- Ignore every filename beginning with `._`.
- Ignore `.DS_Store`.

#### 8.4.1 Key Moments

Path pattern:

```text
EPM-E4/key_moments/{EMOTION}.csv
```

Files:

- `FEAR.csv`
- `ANGER.csv`
- `SADNESS.csv`
- `HAPPINESS.csv`

Schema:

- `timestamp`
- `emotion`

Gateway behavior:

- Add rows to `epm_e4` with `record_type = 'key_moment'`.
- `condition = source emotion filename`.
- `sample_time_utc = to_timestamp(timestamp)` if Unix timestamp is numeric.
- Preserve `emotion` in both `condition` and `payload_json`.

#### 8.4.2 Questionnaires

Folders:

```text
EPM-E4/questionnaires/raw/
EPM-E4/questionnaires/preprocessed/
```

Observed preprocessed files include:

- `Ficha_Evaluacion_Participante_Refactored.csv`
- `Ficha_Evaluacion_Participante_SAM_Refactored.csv`

Sample schema:

- `Ficha_Evaluacion_Participante_Refactored.csv`: 48 columns, Spanish questionnaire fields.
- `Ficha_Evaluacion_Participante_SAM_Refactored.csv`: `ID`, `VALENCE`, `AROUSAL`, `EMOTION`.

Gateway behavior:

- Add rows to `epm_e4` with `record_type = 'questionnaire'`.
- `subject_id` comes from `ID` when present.
- `condition` comes from `EMOTION` when present.
- Store all fields in `payload_json`.

#### 8.4.3 Raw Empatica and Muse Data

Raw path root:

```text
EPM-E4/empatica_wearable_data/raw/{subject_id}/
```

Observed raw structure per subject:

```text
{subject_id}/order.txt
{subject_id}/empatica/ACC.csv
{subject_id}/empatica/BVP.csv
{subject_id}/empatica/EDA.csv
{subject_id}/empatica/HR.csv
{subject_id}/empatica/IBI.csv
{subject_id}/empatica/TEMP.csv
{subject_id}/empatica/info.txt
{subject_id}/empatica/tags.csv
{subject_id}/muse/{EMOTION}_mindMonitor_{date}.csv
```

Observed raw counts:

| Item | Count |
| --- | ---: |
| Raw files | 611 |
| Raw subjects | 47 |
| Empatica files per subject | 8 |
| Muse CSVs per subject | 4 |
| Emotions | `FEAR`, `ANGER`, `SADNESS`, `HAPPINESS` |

Empatica raw CSVs use the two-line E4 format from Section 7.2.

Muse MindMonitor schema:

- Headered CSV.
- First column: `TimeStamp`.
- Observed total columns: 39.
- Columns include EEG bands at `TP9`, `AF7`, `AF8`, `TP10`, raw channels, accelerometer, gyro, headband status, HSI values, battery, and elements.

Gateway behavior:

- Add raw Empatica signal rows to `epm_e4` with `record_type = 'raw_empatica'`.
- Add raw Muse rows to `epm_e4` with `record_type = 'raw_muse'`.
- Parse Muse `TimeStamp` into `sample_time_utc` when possible.
- Put all Muse columns into `payload_json`, and optionally expose commonly used columns later.

#### 8.4.4 Preprocessed Empatica Slices

Preprocessed roots:

```text
EPM-E4/empatica_wearable_data/preprocessed/unclean-signals/empatica_slices/0.0078125/{subject_id}/{condition}.csv
EPM-E4/empatica_wearable_data/preprocessed/clean-signals copia/empatica_slices/0.0078125S/{subject_id}/{condition}.csv
```

Observed preprocessed counts:

| Branch | Files | Subjects | Uncompressed payload |
| --- | ---: | ---: | ---: |
| `unclean-signals` | 264 | 33 | 387.4 MiB |
| `clean-signals copia` | 356 | 45 | 516.6 MiB |

Observed condition filenames:

- `FEAR.csv`
- `ANGER.csv`
- `SADNESS.csv`
- `HAPPINESS.csv`
- `NEUTRAL_FEAR.csv`
- `NEUTRAL_ANGER.csv`
- `NEUTRAL_SADNESS.csv`
- `NEUTRAL_HAPPINESS.csv`

Observed schema:

```text
TimeStamp,
empatica.acc.x,
empatica.acc.y,
empatica.acc.z,
empatica.hr,
empatica.bvp,
empatica.eda,
empatica.temp
```

Sampling interval:

- Folder name `0.0078125` implies 0.0078125 seconds per sample, equivalent to 128 Hz.

Gateway behavior:

- Add rows to `epm_e4` with `record_type = 'preprocessed_empatica'`.
- `condition` comes from the filename.
- `quality_stage` should be `clean` or `unclean`.
- `sample_time_utc` comes from `TimeStamp`.
- Expose typed columns for accelerometer, heart rate, BVP, EDA, and temperature.

### 8.5 `WESAD.zip`

Physical archive:

- Archive size: 2145.24 MiB.
- Files: 76.
- Uncompressed payload: 16763.98 MiB.
- Subjects: 15.
- Subject IDs: `S2`, `S3`, `S4`, `S5`, `S6`, `S7`, `S8`, `S9`, `S10`, `S11`, `S13`, `S14`, `S15`, `S16`, `S17`.

Per-subject files:

```text
WESAD/{subject_id}/{subject_id}.pkl
WESAD/{subject_id}/{subject_id}_E4_Data.zip
WESAD/{subject_id}/{subject_id}_quest.csv
WESAD/{subject_id}/{subject_id}_readme.txt
WESAD/{subject_id}/{subject_id}_respiban.txt
```

Nested E4 zip contents:

```text
ACC.csv
EDA.csv
BVP.csv
TEMP.csv
IBI.csv
HR.csv
info.txt
tags.csv
```

Nested E4 CSV format:

- Same Empatica two-line format from Section 7.2.
- `ACC.csv`: start Unix timestamp repeated in 3 columns, rate repeated in 3 columns, then x/y/z samples.
- `BVP.csv`: start Unix timestamp, rate 64 Hz, then samples.
- `EDA.csv`: start Unix timestamp, rate 4 Hz, then samples.
- `TEMP.csv`: start Unix timestamp, rate 4 Hz, then samples.
- `HR.csv`: start Unix timestamp, rate 1 Hz, then samples.
- `IBI.csv`: start Unix timestamp plus `IBI`, then offset/duration rows.
- `tags.csv`: event timestamps.

Questionnaire files:

- Semicolon-delimited.
- First rows begin with metadata markers like `# Subj` and `# ORDER`.
- First-pass parser should keep questionnaire rows in `payload_json` with `record_type = 'questionnaire'`.

Readme files:

- Per-subject personal and prerequisite metadata.
- Include age, height, weight, gender, dominant hand, coffee/sports/smoking/illness flags, and additional notes.

PKL files:

- 15 files.
- Very large uncompressed members.
- Largest observed uncompressed PKL files:
  - `WESAD/S6/S6.pkl`: 1123292444 bytes
  - `WESAD/S4/S4.pkl`: 1034344388 bytes
  - `WESAD/S3/S3.pkl`: 1031507132 bytes
  - `WESAD/S5/S5.pkl`: 993435543 bytes
  - `WESAD/S2/S2.pkl`: 975117737 bytes

Gateway table:

- `wesad`

First implementation behavior:

- Include nested E4 CSV data.
- Include questionnaire and readme metadata.
- Include PKL file metadata only.
- Do not parse PKL internals unless a WESAD-PKL Parquet conversion job is requested.

Optional PKL conversion behavior:

- Process one subject at a time.
- Load the PKL object in a bounded worker process.
- Convert each signal group into compressed Parquet partitioned by `subject_id`, `device`, and `sensor`.
- Delete the in-memory object and temporary spool before moving to the next subject.
- Never materialize all PKL files at once.

### 8.6 `archive(1).zip`

Physical archive:

- Archive size: 0.01 MiB.
- File: `wearable_sports_health_dataset.csv`.
- Uncompressed size: 42481 bytes.
- Lines: 501 total, 500 data rows.

Schema:

```text
Record_ID,
Athlete_ID,
Timestamp,
Heart_Rate,
Body_Temperature,
Blood_Pressure,
Blood_Oxygen,
Step_Count,
Activity_Status,
Latitude,
Longitude,
Secure_Transmission_Status
```

Gateway table:

- `wearable_sports_health`

Recommended typed columns:

- `record_id text`
- `athlete_id text`
- `sample_time_utc timestamp`
- `heart_rate double precision`
- `body_temperature double precision`
- `blood_pressure text`
- `blood_oxygen double precision`
- `step_count bigint`
- `activity_status text`
- `latitude double precision`
- `longitude double precision`
- `secure_transmission_status integer`

### 8.7 `archive(2).zip`

Physical archive:

- Archive size: 76.18 MiB.
- File: `merged_data.csv`.
- Uncompressed size: 861071702 bytes.
- Lines: 11,509,052 total, 11,509,051 data rows.

Schema:

```text
X,
Y,
Z,
EDA,
HR,
TEMP,
id,
datetime,
label
```

Gateway table:

- `merged_wearable_stress`

Recommended typed columns:

- `x double precision`
- `y double precision`
- `z double precision`
- `eda double precision`
- `hr double precision`
- `temp double precision`
- `subject_id text`
- `sample_time_utc timestamp`
- `label double precision`

Storage note:

- This is a single compressed CSV with 11.5M rows. Direct zip streaming is fine for small filtered previews, but repeated full scans should trigger the Parquet/ZSTD cache.

Example query:

```sql
select subject_id, label, count(*) as rows
from merged_wearable_stress
group by subject_id, label
order by subject_id, label;
```

### 8.8 `sample(1).zip`

Physical archive:

- Archive size: 648.24 MiB.
- Files: 35.
- Uncompressed payload: 1797.46 MiB.
- Primary subject/session ID: `27-9VUW`.
- Roots:
  - `csv/`
  - `raw/`
  - `mat/`

Normalized CSV paths:

```text
csv/27-9VUW/markers-phase1.csv
csv/27-9VUW/markers-phase2.csv
csv/27-9VUW/markers-unique.csv
csv/27-9VUW/params.csv
csv/27-9VUW/signals-back-acc.csv
csv/27-9VUW/signals-back-gyro.csv
csv/27-9VUW/signals-bh3-acc.csv
csv/27-9VUW/signals-bh3-bb.csv
csv/27-9VUW/signals-bh3-br.csv
csv/27-9VUW/signals-bh3-ecg.csv
csv/27-9VUW/signals-bh3-hr.csv
csv/27-9VUW/signals-bh3-hr_confidence.csv
csv/27-9VUW/signals-bh3-rr.csv
csv/27-9VUW/signals-bh3-rsp.csv
csv/27-9VUW/signals-e4-acc.csv
csv/27-9VUW/signals-e4-bvp.csv
csv/27-9VUW/signals-e4-eda.csv
csv/27-9VUW/signals-e4-hr.csv
csv/27-9VUW/signals-e4-ibi.csv
csv/27-9VUW/signals-e4-skt.csv
csv/27-9VUW/signals-front-acc.csv
csv/27-9VUW/signals-front-gyro.csv
csv/27-9VUW/signals-water-acc.csv
csv/27-9VUW/signals-water-gyro.csv
csv/27-9VUW/surveys.csv
```

Raw nested zips:

```text
raw/27-9VUW/back.zip
raw/27-9VUW/bh3.zip
raw/27-9VUW/e4.zip
raw/27-9VUW/front.zip
raw/27-9VUW/water.zip
```

Other binary formats:

- Four MAT files under `mat/`.
- One DB file under `raw/`.

Largest normalized CSV members:

| File | Uncompressed size |
| --- | ---: |
| `signals-front-acc.csv` | 357364635 bytes |
| `signals-water-acc.csv` | 302501850 bytes |
| `signals-back-acc.csv` | 281848827 bytes |
| `signals-front-gyro.csv` | 150513589 bytes |
| `signals-water-gyro.csv` | 114934226 bytes |
| `signals-back-gyro.csv` | 105912106 bytes |

Gateway table:

- `sample_27_9vuw`

First implementation behavior:

- Prefer `csv/27-9VUW/*.csv`, because those are already normalized.
- Do not parse `raw/*.zip`, `mat/*.mat`, or embedded DB by default.
- Expose raw/MAT/DB files in `gateway_members`.
- Add rows from markers, params, surveys, and signals into one table using `record_type`.

Recommended `record_type` values:

- `marker_phase1`
- `marker_phase2`
- `marker_unique`
- `param`
- `survey`
- `signal`

Signal filename mapping:

```text
signals-{device}-{signal}.csv
```

Examples:

- `signals-back-acc.csv`: `device = 'back'`, `sensor = 'acc'`
- `signals-bh3-ecg.csv`: `device = 'bh3'`, `sensor = 'ecg'`
- `signals-e4-eda.csv`: `device = 'e4'`, `sensor = 'eda'`
- `signals-front-gyro.csv`: `device = 'front'`, `sensor = 'gyro'`

Timestamps:

- Signal CSVs have a `timestamp` column that appears to be relative seconds.
- Set `sample_offset_s = timestamp`.
- Leave `sample_time_utc` null unless a session start time is discovered later.

### 8.9 `wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip`

Physical archive:

- Archive size: 69.73 MiB.
- Files: 709.
- CSV files: 704.
- Uncompressed payload: 247.36 MiB.
- Root: `wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1/`.

Top-level metadata files:

```text
Data_Dictionary.csv
LICENSE.txt
README.txt
SHA256SUMS.txt
Stress_Level_v1.csv
Stress_Level_v2.csv
Wearable_Dataset.ipynb
subject-info.csv
```

Main data path pattern:

```text
Wearable_Dataset/{activity}/{subject_id}/{sensor}.csv
```

Activities:

| Activity | Subjects |
| --- | ---: |
| `AEROBIC` | 31 |
| `ANAEROBIC` | 32 |
| `STRESS` | 37 |

Signals:

| Sensor file | Count |
| --- | ---: |
| `ACC.csv` | 100 |
| `BVP.csv` | 100 |
| `EDA.csv` | 100 |
| `HR.csv` | 100 |
| `IBI.csv` | 100 |
| `TEMP.csv` | 100 |
| `tags.csv` | 100 |

Data dictionary rates and units:

| Code | Rate | Units |
| --- | ---: | --- |
| `EDA` | 4 Hz | microsiemens, `uS` |
| `TEMP` | 4 Hz | deg C |
| `BVP` | 64 Hz | source unit unspecified |
| `HR` | 1 Hz | beats per minute |
| `IBI` | variable | seconds |
| `ACC` | 32 Hz | 1/64g |
| `tags` | event marks | timestamps |

Gateway table:

- `induced_stress_exercise`

First implementation behavior:

- Parse `subject-info.csv` with `record_type = 'subject_info'`.
- Parse `Stress_Level_v1.csv` and `Stress_Level_v2.csv` with `record_type = 'stress_level'`.
- Parse `Wearable_Dataset/{activity}/{subject}/{sensor}.csv` with `record_type = 'signal'`.
- Use Empatica E4 two-line parser for signal files.

Note:

- The README says Empatica files are already converted to UTC. The first row may be a UTC timestamp string instead of a Unix timestamp. The parser must detect both.

## 9. Server Architecture

The gateway has five layers:

1. Source registry.
2. Manifest/index builder.
3. Dataset adapters.
4. Query engine/cache layer.
5. PostgreSQL-compatible endpoint.

### 9.1 Source Registry

Hard-code or configure the root folder:

```text
/Users/skyler/Downloads/pain datasets
```

Source registry entries:

```json
{
  "dataset_id": "catsa",
  "source_path": "CATSA.zip",
  "source_type": "zip",
  "table": "catsa",
  "adapter": "catsa_adapter",
  "cache_policy": "on_repeated_scan"
}
```

### 9.2 Manifest Builder

On startup:

1. Scan root directory.
2. For each plain CSV, record path, size, header, delimiter, line count if small.
3. For each zip, read only the central directory first.
4. Skip macOS sidecar entries.
5. Record member path, CRC32, compressed size, uncompressed size, extension, and parser guess.
6. Read small header samples from CSV members.
7. Build `gateway_archives` and `gateway_members`.

The manifest itself can live in memory. If persisted, it should be a small JSON file under `_gateway_cache/manifest.json`, not a database.

### 9.3 Dataset Adapters

Each logical table has an adapter:

| Adapter | Responsibilities |
| --- | --- |
| `PlainCsvAdapter` | Top-level CSV and single-member zip CSV tables |
| `CatsaAdapter` | Parse `CATSA/{subject}/{task}/{sensor}.csv`, derive sample offsets |
| `EpmE4Adapter` | Parse raw Empatica, raw Muse, preprocessed Empatica, questionnaires, key moments |
| `WesadAdapter` | Parse nested E4 zips, quest CSVs, readmes, PKL metadata |
| `Sample27Adapter` | Parse normalized CSVs under `csv/27-9VUW` |
| `InducedStressExerciseAdapter` | Parse activity/subject/sensor E4 files plus metadata |

Adapter output should be Arrow record batches where possible. This makes it easy to stream to:

- PostgreSQL protocol result rows.
- DuckDB in-memory relations.
- Compressed Parquet files.

### 9.4 Query Engine and Cache Layer

Direct zip streaming is acceptable for:

- Listing tables.
- Preview queries with `limit`.
- Small metadata tables.
- Single-subject, single-sensor scans.

Compressed Parquet cache is recommended for:

- `archive(2).zip/merged_data.csv` after repeated full scans.
- EPM raw Muse CSVs if repeatedly queried.
- EPM preprocessed signal files if repeatedly queried.
- `sample(1).zip` large accelerometer and gyroscope files.
- WESAD PKL-derived data if PKLs are enabled.

Cache format:

- Parquet.
- Compression: ZSTD.
- Row group size: 64 MiB target.
- Dictionary encoding enabled for string columns.
- Partition by high-selectivity metadata:
  - `dataset_id`
  - `subject_id`
  - `condition`
  - `device`
  - `sensor`

Default cache root:

```text
/tmp/pain_gateway/parquet_cache
```

Optional reusable cache root:

```text
/Users/skyler/Downloads/pain datasets/_gateway_cache/parquet
```

Disk guardrails:

- Default mode: no persistent cache.
- Optional persistent mode: require an explicit `CACHE_MAX_GB`.
- Before writing a partition, estimate the output and check free disk.
- Write to a temp file, close it, then atomically rename into the cache.
- Keep a `cache_index.json` with source CRC32 and source size so stale partitions are invalidated.

### 9.5 PostgreSQL-Compatible Endpoint

The endpoint needs to satisfy common connector behavior:

- Accept a username/password.
- Implement read-only `SELECT`.
- Support metadata introspection against `information_schema.tables`, `information_schema.columns`, and PostgreSQL catalog queries commonly used by BI tools.
- Support `limit`, projection, simple predicates, grouping, and count queries.

Minimum SQL support:

- `select * from table limit N`
- `select columns from table where simple_predicates limit N`
- `select count(*) from table`
- `select group_cols, count(*) from table group by group_cols`
- `select min(col), max(col) from table`

Predicate pushdown priorities:

- `dataset_id`
- `subject_id`
- `condition`
- `device`
- `sensor`
- `source_member`
- `sample_time_utc` range
- `sample_offset_s` range

Unsupported SQL should return a clear read-only gateway error instead of silently scanning everything.

## 10. Compression-First Transcode Plan

When direct zip access is too slow or structurally awkward, transcode directly into compressed Parquet:

```text
_gateway_cache/parquet/
  catsa/
    subject_id=Sub1/
      condition=Baseline/
        sensor=ACC/
          part-00000.parquet
  epm_e4/
    record_type=preprocessed_empatica/
      quality_stage=clean/
        subject_id=92/
          condition=FEAR/
            part-00000.parquet
  wesad/
    source=e4/
      subject_id=S10/
        sensor=EDA/
          part-00000.parquet
  merged_wearable_stress/
    id=15/
      label=2.0/
        part-00000.parquet
```

Rules:

- Read from zip member stream.
- Convert rows in chunks.
- Write Parquet row groups.
- Never write uncompressed CSV to disk.
- Never extract whole archive directories.
- For nested zip, use memory or bounded scratch file only for the nested zip container, not extracted members.
- For PKL, process one subject at a time and write one signal group at a time.

## 11. Query Examples

CATSA EDA for one subject/task:

```sql
select subject_id, condition, sample_offset_s, value as eda
from catsa
where subject_id = 'Sub1'
  and condition = 'Baseline'
  and sensor = 'EDA'
order by sample_offset_s
limit 1000;
```

Merged stress labels:

```sql
select subject_id, label, count(*) as rows
from merged_wearable_stress
group by subject_id, label
order by subject_id, label;
```

WESAD wrist BVP preview:

```sql
select subject_id, sensor, sample_time_utc, value
from wesad
where subject_id = 'S10'
  and sensor = 'BVP'
order by sample_time_utc
limit 1000;
```

EPM clean preprocessed FEAR rows:

```sql
select subject_id, sample_time_utc, x, y, z, payload_json
from epm_e4
where record_type = 'preprocessed_empatica'
  and quality_stage = 'clean'
  and condition = 'FEAR'
limit 1000;
```

Induced stress exercise by activity:

```sql
select condition as activity, sensor, count(*) as rows
from induced_stress_exercise
where sensor in ('EDA', 'HR', 'TEMP')
group by condition, sensor
order by condition, sensor;
```

## 12. Implementation Milestones

### Milestone 1: Inventory and Metadata

Deliver:

- In-memory manifest builder.
- `gateway_archives`, `gateway_members`, `gateway_tables`.
- PostgreSQL catalog/introspection responses.
- No heavy row scans.

### Milestone 2: Direct Streaming Tables

Deliver:

- `subject_info_catsa`
- `questionnaire`
- `wearable_sports_health`
- `merged_wearable_stress` preview and filtered scans
- `catsa` direct stream
- `induced_stress_exercise` direct stream

### Milestone 3: Complex Dataset Adapters

Deliver:

- `sample_27_9vuw` over normalized CSVs.
- `wesad` over nested E4 zips, readmes, questionnaires.
- `epm_e4` over key moments, questionnaires, raw Empatica, raw Muse, and preprocessed Empatica.

### Milestone 4: Compressed Cache

Deliver:

- Parquet/ZSTD cache writer.
- Cache index with source CRC invalidation.
- Query planner that uses cache when present.
- Configured cache size guardrail.

### Milestone 5: Optional WESAD PKL Conversion

Deliver:

- Subject-by-subject PKL reader.
- Signal-group Parquet writer.
- Memory-isolated worker process.
- `wesad` table rows over PKL-derived partitions.

## 13. Recommended First Build

Build the first server as a Python process with:

- `zipfile` for archive streaming.
- `csv` or `pandas.read_csv(..., chunksize=...)` for simple CSV streams.
- `pyarrow` for Arrow batches and Parquet/ZSTD cache output.
- `duckdb` in memory for local SQL over generated Arrow/Parquet batches where useful.
- A PostgreSQL-compatible endpoint layer for the datasource picker.

Do not use Spark for the first local gateway unless distributed execution becomes necessary. Spark/Hadoop are useful if the compressed Parquet lake moves to object storage or HDFS later, but they do not remove the need to map these zip-specific formats and do not directly solve the PostgreSQL connector requirement.

## 14. Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| PostgreSQL wire compatibility is more work than file parsing | Datasource connector may fail introspection | Implement catalog query responses early; test with the target UI before optimizing scanners |
| Full scans over zipped CSV are slow | Bad user experience for large tables | Add Parquet/ZSTD cache after first repeated scan |
| WESAD PKL loading uses too much memory | Process crash | Skip PKL by default; subject-by-subject worker with memory limit |
| EPM archive includes macOS metadata files | Bad schemas/noisy rows | Central skip rules for `__MACOSX`, `._*`, `.DS_Store` |
| No absolute timestamps in CATSA/sample relative signals | Cross-dataset time alignment blocked | Expose `sample_offset_s`; leave `sample_time_utc` null until trial start metadata exists |
| Mixed schema inside one dataset table | Some columns sparse | Preserve typed common columns and put irregular data in `payload_json` |
| Cache grows too large | Disk pressure | Default cache under `/tmp`, explicit max size for persistent cache, no uncompressed staging |

## 15. Acceptance Criteria

The setup is acceptable when:

- The datasource picker can connect through the PostgreSQL option.
- The connector can list all logical tables.
- `select * from each_table limit 10` works.
- `gateway_members` shows every useful zip member without extracting archives.
- The gateway can query `archive(2).zip` without creating an 861 MB decompressed CSV on disk.
- The gateway can query WESAD nested E4 CSVs without extracting `WESAD.zip`.
- No full uncompressed archive tree is created.
- Any derived cache is compressed Parquet/ZSTD and bounded by config.
