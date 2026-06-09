---
type: dataset
status: active
updated: 2026-06-08
tags: [stress, activity, context]
source_files:
  - docs/INGEST_PIPELINE.md
  - docs/STATE_NORMALIZATION_AND_R_FINDINGS.md
---

# Context And Auxiliary Datasets

Purpose:

```yaml
train:
  - stress heads
  - cognitive load/context heads
  - exercise/activity context heads
  - baseline/context recognition

do_not_train:
  - direct pain head
```

Datasets:

```yaml
catsa:
  role: cognitive_load_proxy, baseline_context
  risk: protocol signatures may dominate

wesad:
  role: stress_proxy from E4 wrist stream
  labels: protocol stress segments joined
  risk: stress protocols not same as pain/stress in wild

wesad_respiban:
  role: stress_proxy from chest Respiban
  sensors: ECG, EDA, EMG, temp, ACC, respiration
  rate: decimated from 700Hz to about 63.636Hz
  risk: chest lab sensor pack not watch-like

induced_stress_exercise:
  role: stress/exercise auxiliary
  labels: stress-level CSVs joined
  includes: IBI
  risk: activity target currently weak/one-class in places

wearable_sports_health:
  role: future sports/activity context
  current_state: normalized but not final-window useful
```

Main lesson:

```yaml
stress_or_activity_signal:
  useful_as: competing context/state evidence
  dangerous_as: direct pain proxy
```

