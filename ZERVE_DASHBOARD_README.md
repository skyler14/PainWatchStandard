# PainWatchStandard Zerve Dashboard Branch

This branch is the Git upload vehicle for the Zerve dashboard flow. It is
curated separately from the local working dataset folder so the dashboard sees
only the files needed to restore/query data, run Phase 1-3 scripts, and serve
the frozen Phase 3 inference model.

## Primary Dashboard Upload

Upload or restore the full PostgreSQL dump:

```bash
gunzip -c _exports/pain_demo_postgres_phase3_all_datasets.sql.gz | psql "$DATABASE_URL"
```

Expected schema:

```text
pain_demo_phase3
```

The full dump is the primary dashboard artifact. The small sample dump exists
only for fast smoke tests:

```bash
gunzip -c _exports/pain_demo_postgres_phase3_small_sample.sql.gz | psql "$DATABASE_URL"
```

## Frozen Inference Model

Production inference should use only this alias:

```text
pain-thermometer-phase3-final-v1
```

Model artifact:

```text
zerve_flow/models/pain-thermometer-phase3-final-v1/model.joblib
```

Manifest:

```text
zerve_flow/models/pain-thermometer-phase3-final-v1/manifest.json
```

Dashboard training jobs must create candidate aliases such as
`pain-thermometer-phase3-candidate-{timestamp}`. They must not overwrite the
`final` alias.

## Run Order

Phase 1, from repo root:

```bash
python3 pain_normalizer.py
python3 pain_feeder.py build-windows --dataset all --target-hz 1 --window-seconds 30
python3 pain_all_dataset_feeder.py
python3 pain_self_supervised.py
python3 pain_supervised_baseline.py
```

Phase 2, from repo root:

```bash
/opt/anaconda3/envs/thepipe/bin/python pain-thermometer-exploration/phase_2/analysis/stress_reference_analysis.py
/opt/anaconda3/envs/thepipe/bin/python pain-thermometer-exploration/src/stress_reference_feeder_adapter.py
pain-thermometer-exploration/.conda-r/bin/Rscript pain-thermometer-exploration/phase_2/analysis/stress_reference_r_analysis.R
```

Phase 3, from repo root:

```bash
/opt/anaconda3/envs/thepipe/bin/python pain-thermometer-exploration/phase_3/analysis/phase3_prepare_dataset.py
/opt/anaconda3/envs/thepipe/bin/python pain-thermometer-exploration/phase_3/analysis/phase3_multitask_baseline.py --model-iterations 60 --max-aux-rows 60000 --max-loso-subjects 2 --feature-mode fast
/opt/anaconda3/envs/thepipe/bin/python zerve_flow/train_final_model.py
```

Regenerate the full dashboard dump:

```bash
/opt/anaconda3/envs/thepipe/bin/python postgres_demo_export.py --output _exports/pain_demo_postgres_phase3_all_datasets.sql.gz --schema-name pain_demo_phase3 --batch-size 50000
```

Regenerate the small sample:

```bash
/opt/anaconda3/envs/thepipe/bin/python postgres_demo_export.py --output _exports/pain_demo_postgres_phase3_small_sample.sql.gz --schema-name pain_demo_phase3_sample --batch-size 25000 --small-sample
```

Run the dashboard flow smoke test:

```bash
/opt/anaconda3/envs/thepipe/bin/python zerve_flow/smoke_test.py
```

The smoke test verifies Phase 1/2/3 artifacts, checks the full dashboard dump,
regenerates a compact PostgreSQL dump, loads the frozen model, and emits a
score response with 10 `pain_blocks_10` entries.

## Zerve Contracts

- `PainThermometer/Docs/ZERVE_DASHBOARD_UPLOAD_RECORD.json`
- `PainThermometer/Docs/ZERVE_INFERENCE_CONTRACT.md`
- `PainThermometer/Docs/ZERVE_ENDPOINT_SPEC.md`
- `PAIN_FEEDER_SPEC.md`
- `pain-thermometer-exploration/phase_3/PHASE_3_PIPELINE_SPEC.md`

The watch live UI should consume `pain_blocks_10` as the 10-box rolling pain
likelihood strip.
