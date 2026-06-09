---
type: dataset
status: active
updated: 2026-06-08
tags: [coverage, datasets]
source_files:
  - _normalized/full_enriched4/summary.json
  - _normalized/phase3_enriched/target_hz=1/window_features.parquet
---

# Dataset Coverage

All main `/Users/skyler/Downloads/PainDatasets` archives are represented in normalized ingest.

Source archives:

```yaml
main_archives:
  - CATSA.zip
  - Multimodal Pain Dataset.zip
  - PainMonit Database.zip
  - PhysioPain Dataset.zip
  - RheumaPain Dataset.zip
  - SILVER-Pain Dataset.zip
  - WESAD.zip
  - Wearable Sports Health Monitoring Dataset.zip
  - wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1.zip
```

Final window representation:

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

Present normalized, not final-window meaningful:

```yaml
wearable_sports_health:
  stream_rows: 500
  final_windows: 0
  reason: too few rows for current window policy
```

Not merged into master training windows:

```yaml
apple_health_export:
  role: personal archetype/baseline exploration
  pain_truth: never
  current_master_rows: 0

raw_sidecars:
  role: provenance/readme/context
  training_rows: only if joined into normalized context fields

duplicate_downsampled_files:
  role: avoid duplicate leakage/bloat
```

