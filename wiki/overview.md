---
type: overview
status: active
updated: 2026-06-08
tags: [phase3, clean-room, master-dataset]
source_files:
  - README.md
  - docs/ARCHITECTURE.md
  - docs/INGEST_PIPELINE.md
---

# Overview

`PainWatchStandard` is clean-room core for Phase 3 pain/stress/context modeling.

Current scope:

```yaml
in_scope:
  - normalized dataset ingest
  - causal trailing-window features
  - direct pain vs auxiliary state routing
  - baseline/context archetypes
  - inference contracts
  - tests for feature/inference/schema behavior

out_of_scope:
  - mobile app
  - old UI code
  - raw archive ownership inside repo
  - Apple Watch as pain-label source
```

Current master artifact:

```yaml
normalized_source: _normalized/full_enriched4
phase3_windows: _normalized/phase3_enriched/target_hz=1/window_features.parquet
rows: 1655772
columns: 220
size: 243MB
target_hz: 1
window_seconds: 30
tests: 21 passed
```

Core contract:

```yaml
one_row: one live-style prediction tick
cadence: 1 row per second
memory: trailing 30 seconds
pain_training: only explicit direct-pain rows
aux_training: stress/activity/context rows train auxiliary heads only
baseline: context-aware calibration, not pain truth
sensor_presence: quality/device/mask information, not state evidence
```

Main linked topics:

- [[pipeline/master-dataset]]
- [[pipeline/windowing]]
- [[datasets/coverage]]
- [[model/state-normalization]]
- [[model/baselines-and-archetypes]]

