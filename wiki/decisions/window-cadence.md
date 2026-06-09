---
type: decision
status: active
updated: 2026-06-08
tags: [windowing, cadence]
---

# Window Cadence

Decision:

```yaml
current_master:
  target_hz: 1
  window_seconds: 30
  keep_for_now: true
```

Clarification:

```yaml
target_hz_1: one output row per second
window_seconds_30: each row sees trailing 30 seconds
not: non-overlapping 30-second bins
```

Reason to keep:

```yaml
1Hz:
  - already built
  - parquet valid
  - enough for first training/debugging
  - closer to live scoring than coarse segment bins

2Hz_future:
  - possible
  - larger artifact
  - should wait until wiki/model rules stable
```

