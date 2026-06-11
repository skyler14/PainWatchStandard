---
type: log
status: active
updated: 2026-06-11
---

# Wiki Log

## [2026-06-11] design | Functional Pain V2 Professional Benchmark

Specified proposed v2 run without starting training:

- realistic watch/device hydration variants
- autonomic-space, phase-two stress, WESAD, cvxEDA, HRV-biofeedback, and multimodal-pain method arms
- unified learner benchmark
- source/device/activity holdouts
- portable JSON, ONNX, and CoreML parity requirements
- one-sentence learner explanations

Touched pages:

- [[runs/functional-pain-v2-professional-benchmark]]
- [[lessons]]

## [2026-06-10] run | Functional Pain V1 Learning Run

Started siloed learning run for Functional Pain V1:

- aggressive 5s/10s/30s temporal feature table
- weak three-state autonomic labels
- activity, dataset-only, and quality-only controls
- portable logistic export path
- nonlinear learner comparison

Touched pages:

- [[runs/functional-pain-v1-learning-run]]
- [[lessons]]

## [2026-06-10] run-result | Functional Pain V1 Learning Run

Completed run over 10,580 rows from 5s/10s/30s temporal feature tables.

Main findings:

- PNS/recovery proxy was strongest: portable logistic AUC 0.779, aggressive logistic AUC 0.828.
- SNS weak label failed controls: quality-only AUC 0.700 and dataset-only AUC 0.693 beat main portable logistic AUC 0.638.
- Homeostasis was weak: portable logistic AUC 0.677, dataset-only AUC 0.671.
- Activity control was trivial/protocol-identifiable: dataset-only AUC 1.000.
- Leave-dataset-out showed PNS proxy had some transfer-like behavior; SNS and homeostasis were unstable.
- ONNX/CoreML not exported because converters unavailable; portable logistic JSON was exported.

Updated:

- [[runs/functional-pain-v1-learning-run]]
- [[lessons]]

## [2026-06-10] research | Autonomic Space Model

Added autonomic-space model page covering:

- RSA as cardiac vagal/PNS axis
- PEP as lab cardiac SNS axis
- CAB and CAR derivative scores
- reciprocal, uncoupled, coactivation, and coinhibition modes
- what can be derived from current PainWatchStandard data
- what requires new hardware or protocols

Touched pages:

- [[model/autonomic-space-model]]
- [[model/functional-pain-v1]]
- [[index]]

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
