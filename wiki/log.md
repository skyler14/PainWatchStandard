---
type: log
status: active
updated: 2026-06-08
---

# Wiki Log

## [2026-06-10] design | Functional Pain V1

Added `functional_pain_v1` as a simple ternary display layer:

- sympathetic activation
- parasympathetic recovery
- homeostasis / return to baseline

This is not trained pain truth. It is an interpretable physiology tracker for intervention response and baseline return.

Touched pages:

- [[model/functional-pain-v1]]
- [[model/inference-contract]]

## [2026-06-09] analysis | Multiscale Temporal Shape Results

Ran Python and R exploration over 5, 10, and 30 second histories with subject-grouped validation, leave-dataset-out pain tests, time-shuffle controls, quality-only controls, and dataset-only controls.

Confirmed:

- selected within-source temporal shape signal exists
- pooled pain transfer remains near chance
- dataset identity alone predicts pooled pain at about AUC 0.74
- PMED COVAS was mis-scaled from 0-100
- PMED protocol gaps created false full-window coverage and inflated AUC
- broad feature banks are highly redundant

Added PMED scale correction, window continuity rejection, reproducible summary outputs, and detailed result page.

Touched pages:

- [[model/temporal-shape-results]]
- [[model/temporal-shape-analysis]]
- [[pipeline/windowing]]
- [[open-questions/label-semantics]]

## [2026-06-09] query | Temporal Shape Analysis

Confirmed current master uses full runs to emit one row per second from trailing 30-second windows. Audited current feature extractor: useful summaries exist, but rich temporal shape is mostly absent.

Added broad Python/R method survey and prioritized experiment plan:

- compact custom dynamics and spectral features
- sensor-specific EDA/HRV/BVP/ECG/respiration/ACC features
- cross-sensor lag and coupling
- catch22, tsfresh, TSFEL, aeon, Kymatio
- R theft, nonlinearTseries, dtwclust, and functional data analysis
- shapelets, MiniROCKET, causal TCN, and later self-supervised learning
- time-shuffle, reverse-time, phase-randomization, presence-only, and dataset-only controls

Touched page:

- [[model/temporal-shape-analysis]]

## [2026-06-08] ingest | Initial Wiki Build

Created project wiki from current `PainWatchStandard` code, docs, built artifacts, and user corrections.

Key corrections filed:

- `window_seconds=30` is trailing memory length, not non-overlapping row size.
- `target_hz=1` means one output prediction row per second.
- keep current master at 1Hz for now.
- focus wiki on clean/reworked code, not mobile app or old-phase baggage.

Touched pages:

- [[overview]]
- [[pipeline/master-dataset]]
- [[pipeline/windowing]]
- [[pipeline/ingest]]
- [[pipeline/schema]]
- [[datasets/coverage]]
- [[datasets/direct-pain]]
- [[datasets/context-and-auxiliary]]
- [[datasets/apple-health-archetypes]]
- [[model/feature-standardization]]
- [[model/baselines-and-archetypes]]
- [[model/state-normalization]]
- [[model/inference-contract]]
- [[model/training-rules]]
- [[decisions/clean-room-scope]]
- [[decisions/presence-flags]]
- [[decisions/window-cadence]]
- [[open-questions/label-semantics]]
- [[open-questions/activity-head]]
- [[open-questions/calibration-validation]]
