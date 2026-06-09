---
type: log
status: active
updated: 2026-06-08
---

# Wiki Log

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

