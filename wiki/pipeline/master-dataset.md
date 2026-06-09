---
type: pipeline
status: active
updated: 2026-06-08
tags: [artifact, parquet, coverage]
source_files:
  - _normalized/full_enriched4/summary.json
  - _normalized/phase3_enriched/target_hz=1/window_features.parquet
---

# Master Dataset

Current ready artifact:

```yaml
path: _normalized/phase3_enriched/target_hz=1/window_features.parquet
size: 243MB
rows: 1655772
columns: 220
row_groups: 1016
target_hz: 1
window_seconds: 30
status: parquet footer readable, tests passed
```

Normalized source:

```yaml
path: _normalized/full_enriched4
summary: _normalized/full_enriched4/summary.json
status: full enriched ingest complete
```

Window rows by dataset:

```yaml
catsa: 774126
multimodal_pain_eeg: 113339
physiopain_eeg: 113339
multimodal_pain_watch: 107609
physiopain_watch: 107609
wesad: 106504
wesad_respiban: 89467
induced_stress_exercise: 80249
painmonit_pmed: 74810
silver_pain: 54861
rheumapain: 23764
painmonit: 10095
```

Label-family window coverage:

```yaml
cognitive_load_proxy: 449131
direct_pain: 313869
pain_context_unlabeled: 226678
stress_proxy: 225920
unlabeled: 202888
baseline_context: 186986
exercise_context: 50300
```

Known gap:

```yaml
wearable_sports_health:
  normalized: true
  stream_rows: 500
  final_windows: 0
  reason: too tiny/short for current Phase 3 windowing
```

Do not confuse:

```yaml
low_window_count: may still mean useful dataset after downsampling/windowing
zero_window_count: means not represented in final master rows
```

