---
type: model
status: draft
updated: 2026-06-10
tags: [functional-pain, ternary, sympathetic, parasympathetic, homeostasis]
source_files:
  - src/painwatchstandard/functional_pain_v1.py
  - tests/test_functional_pain_v1.py
related:
  - wiki/model/autonomic-space-model.md
---

# Functional Pain V1

Autonomic-space details and derivative score plan: [[model/autonomic-space-model]].

Goal: show pain-relevant physiology as recoverable state, not one overconfident pain number.

## Ternary State

```yaml
vertices:
  sympathetic:
    meaning: arousal, threat, nociceptive load, stress, sweat/HR shift
    examples:
      - EDA high or rising
      - HR high or rising
      - HRV low
      - skin temperature dropping
      - baseline departure high

  parasympathetic:
    meaning: vagal/recovery response
    examples:
      - RMSSD high
      - SDNN high when enough beats
      - HR falling
      - EDA falling
      - respiration regular if present

  homeostasis:
    meaning: near personal/context baseline
    examples:
      - baseline distance low
      - arousal low
      - motion low
      - HR/EDA stable
```

Output coordinates:

```yaml
sympathetic: 0..1
parasympathetic: 0..1
homeostasis: 0..1
sum: 1
ternary_x: 0..1
ternary_y: 0..0.866
```

Plot vertices:

```yaml
sympathetic: [0.0, 0.0]
parasympathetic: [1.0, 0.0]
homeostasis: [0.5, 0.866]
```

## Functional Scores

```yaml
functional_pain_0_1:
  formula_shape: sympathetic * (1 - homeostasis) with activity penalty
  meaning: pain-like unresolved autonomic load
  not: clinical pain diagnosis

recovery_0_1:
  formula_shape: 0.65 * parasympathetic + 0.35 * homeostasis
  meaning: return-to-baseline or parasympathetic response
```

Use:

```yaml
intervention_tracking:
  desired_movement:
    - away from sympathetic corner
    - toward parasympathetic edge during active calming
    - toward homeostasis corner after pain/stress source removed

pain_relief_pattern:
  immediate: parasympathetic rises
  later: homeostasis rises
  bad: sympathetic stays high and homeostasis stays low
```

## Data Contract

Input may be any standard window row. Best current features:

```yaml
sympathetic_inputs:
  - eda__mean
  - eda__slope_per_s
  - eda__peak_count
  - hr__mean
  - hr__slope_per_s
  - bvp__std
  - temperature__slope_per_s
  - baseline_distance_l1

parasympathetic_inputs:
  - ibi__rmssd_ms
  - ibi__sdnn_ms
  - hr__slope_per_s
  - eda__slope_per_s
  - respiration__std

homeostasis_inputs:
  - baseline_distance_l1
  - acc__mag__std
  - hr__std
  - eda__std
```

Missing sensors lower quality and add notes. Missing sensors do not become evidence for or against a state.

## Needed Improvements

```yaml
needed_next:
  - rebuild master after PMED fixes
  - add 5s, 10s, 30s standard window histories
  - add compact temporal features from temporal-shape exploration
  - add HRV quality gates for beat count and duration
  - add baseline archetypes: sleep/rest/walk/workout/recovery
  - calibrate thresholds per device/user context
```

No new raw data structure required. Need richer derived features and better baselines.
