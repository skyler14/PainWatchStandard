---
type: pipeline
status: active
updated: 2026-06-08
tags: [ingest, normalized, parquet]
source_files:
  - src/painwatchstandard/ingest.py
  - scripts/ingest_datasets.py
  - docs/INGEST_PIPELINE.md
---

# Ingest

Source archives:

```yaml
location: /Users/skyler/Downloads/PainDatasets
rule: immutable raw sources
```

Normalized outputs:

```yaml
format: parquet
compression: zstd
layout: dataset_id / branch / measurement_stream.parquet
also_writes:
  - labels.parquet
  - subjects.parquet
  - ingest_outputs.parquet
  - summary.json
```

Current enriched source:

```yaml
path: _normalized/full_enriched4
```

Enrichment included:

```yaml
painmonit:
  clinical_main: PMCD clinical sessions
  clinical_runup_baseline: paired runup/setup files
  pmed: experimental heat pain branch

physiopain_multimodal:
  surveys_joined: true
  fields:
    - survey_age
    - survey_gender
    - survey_sleep_hours_avg
    - survey_daily_stress_ordinal
    - survey_chronic_pain_flag
    - survey_regular_medication_flag
    - survey_pain_context_score
    - survey_pain_type

rheumapain:
  workbook_joined: true
  fields:
    - workbook_age
    - workbook_sex
    - workbook_diagnosis
    - workbook_pain_rest
    - workbook_pain_exercise
    - workbook_exercise_duration_text

wesad:
  e4_wrist: included
  respiban_chest: included, decimated from 700Hz to about 63.636Hz
  protocol_labels_joined: true

induced_stress_exercise:
  stress_csvs_joined: true
  ibi_included: true
```

Command:

```bash
python scripts/ingest_datasets.py \
  --source-root /Users/skyler/Downloads/PainDatasets \
  --output-root _normalized/full_enriched4 \
  --chunksize 100000 \
  normalize-all
```

