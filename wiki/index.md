---
type: index
status: active
updated: 2026-06-09
---

# PainWatchStandard Wiki Index

## Core

- [[overview]] - current project truth, artifacts, and purpose.
- [[pipeline/master-dataset]] - ready artifacts, coverage, row counts, and gaps.
- [[pipeline/windowing]] - exact row meaning for 1Hz / 30s trailing windows.
- [[pipeline/ingest]] - normalized ingest design and dataset enrichment.
- [[pipeline/schema]] - normalized stream and window table fields.

## Datasets

- [[datasets/coverage]] - what is represented, weakly represented, or absent.
- [[datasets/direct-pain]] - datasets allowed to train pain heads.
- [[datasets/context-and-auxiliary]] - stress, cognitive, exercise, and baseline sources.
- [[datasets/apple-health-archetypes]] - personal watch archetypes used for calibration/context only.

## Model

- [[model/feature-standardization]] - sensor summaries, HRV, robust normalization.
- [[model/baselines-and-archetypes]] - context-aware baselines, rejected one-score baseline.
- [[model/state-normalization]] - softmax state competition and confidence critique.
- [[model/inference-contract]] - deployment output and missing-sensor handling.
- [[model/training-rules]] - multi-head training, label gating, leakage controls.
- [[model/temporal-shape-analysis]] - Python/R methods for waveform shape, dynamics, coupling, and definitive-trend tests.
- [[model/temporal-shape-results]] - actual 5s/10s/30s experiments, controls, defects, and architecture decision.
- [[model/functional-pain-v1]] - ternary sympathetic/parasympathetic/homeostasis display method.

## Decisions

- [[decisions/clean-room-scope]] - what this repo keeps and leaves behind.
- [[decisions/presence-flags]] - presence flags as quality/control, not state evidence.
- [[decisions/window-cadence]] - why current master remains 1Hz for now.

## Open Questions

- [[open-questions/label-semantics]] - pain scales needing source-level validation.
- [[open-questions/activity-head]] - activity/exertion labels too weak today.
- [[open-questions/calibration-validation]] - how to prove confidence useful IRL.

## Logs

- [[log]] - chronological wiki maintenance log.
