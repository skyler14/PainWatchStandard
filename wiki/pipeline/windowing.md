---
type: pipeline
status: active
updated: 2026-06-08
tags: [windowing, live-inference]
source_files:
  - src/painwatchstandard/windowing.py
  - src/painwatchstandard/build_windows.py
---

# Windowing

Current default:

```yaml
target_hz: 1
step_seconds: 1
window_seconds: 30
include_partial_windows: false
min_window_rows: 2
```

Plain meaning:

```yaml
target_hz: how often output rows happen
window_seconds: how far each row looks backward
```

Important correction:

```yaml
wrong: one row covers 0-30s, next row covers 30-60s
right: one row every second, each row sees trailing 30s
```

Example:

```yaml
row_at_30s: uses 0s..30s
row_at_31s: uses 1s..31s
row_at_32s: uses 2s..32s
row_at_33s: uses 3s..33s
```

So a 5-minute run is roughly:

```yaml
duration_s: 300
first_full_window_s: 30
cadence: 1 row/s
rows: about 270
```

Live inference implication:

```yaml
current_master:
  works_for: one score per second using 30s recent memory
  not: non-overlapping coarse study segments

possible_future:
  target_hz: 2
  step_seconds: 0.5
  window_seconds: 30
  meaning: one score every half-second using 30s memory
```

Implementation:

```yaml
anchor_generation: make_window_anchors()
session_sort: sample_offset_s ascending
window_slice: searchsorted over sample_offset_s
features: sensor_block_features() per sensor block
target: pain labels aggregated inside trailing window
```

