# PainWatchStandard

Cleanroom core for the Phase 3 pain thermometer pipeline.

This repo intentionally starts with non-mobile data and inference code only. Source archives remain immutable outside the repo; normalized Parquet outputs are rebuildable artifacts.

## First Contracts

- one row = one trailing prediction window
- default cadence = 1 Hz
- default window = trailing 30 seconds
- direct pain rows are the only rows allowed to train pain heads
- stress, emotion, cognitive load, exercise, and baseline rows train auxiliary state heads only
- raw window features stay intact; baseline-relative features are appended
- deployment score must include confidence, quality, missing sensors, stress context, exertion context, and calibration context
- Apple Watch archetypes are context/calibration only; they are not pain or no-pain labels

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Ingest

See [docs/INGEST_PIPELINE.md](docs/INGEST_PIPELINE.md).

Smoke:

```bash
python scripts/ingest_datasets.py --source-root /Users/skyler/Downloads/PainDatasets --output-root _normalized/smoke --chunksize 5000 normalize-all --max-sessions 1 --max-chunks 1
```

Full:

```bash
python scripts/ingest_datasets.py --source-root /Users/skyler/Downloads/PainDatasets --output-root _normalized/full --chunksize 100000 normalize-all
```
