# PainWatchStandard Architecture

## Goal

Rebuild the Phase 3 pain thermometer core without mobile/UI coupling.

Current repo starts with these verified contracts:

- compressed source archives remain outside package code
- normalized streams become causal trailing windows
- direct pain rows train pain heads
- stress/context/activity rows train auxiliary heads only
- raw features are preserved; baseline-relative features are appended
- deployment scores must expose quality and missing sensor blocks
- watch-derived archetypes are context/calibration features, not pain labels

## Current Modules

```text
src/painwatchstandard/normalizers/painmonit.py
src/painwatchstandard/routing.py
src/painwatchstandard/sensors.py
src/painwatchstandard/windowing.py
src/painwatchstandard/baseline.py
src/painwatchstandard/features.py
src/painwatchstandard/inference.py
```

## Implemented First

- PainMonit column and session parsing helpers
- Phase 3 label family routing
- ordinal pain binning
- sensor block summary features
- causal 1-10 Hz trailing window builder
- subject context profile with robust median/MAD-derived features
- strict feature-set selection that excludes IDs, targets, and leaky protocol fields
- pain-training row filter that admits only `label_family=direct_pain` rows with non-null pain targets
- inference helpers for sensor-used/missing summaries, quality, and probability-derived confidence

## Next Work

1. Add `schema.py` dataclasses for normalized streams, window rows, baseline profile manifests, and inference output.
2. Port PainMonit and RheumaPain normalizers behind a streaming API.
3. Add PhysioPain watch normalizer after confirming `pain_scale` semantics.
4. Add Phase 3 builder that joins all-window table, stress rows, and baseline profiles.
5. Add context/calibration model training with group holdout, leave-dataset-out, and no-auxiliary-into-pain assertions.
6. Add inference wrapper with:
   - pain likelihood
   - pain NRS estimate
   - stress likelihood
   - low-exertion/context match
   - activity likelihood
   - quality and confidence

## Data Locations

Parent workspace keeps source and derived data:

```text
../PainMonit.zip
../RheumaPain Dataset.zip
../PhysioPain Dataset.zip
../_normalized/
../_normalized/phase3/target_hz=1/window_features.parquet
```

This cleanroom repo should not own large data files.

## Test Policy

Run:

```bash
python -m pytest
```

Every new behavior starts with a focused fixture test. Prefer tiny synthetic streams over real data for unit tests; use real Parquet only for explicit integration checks.
