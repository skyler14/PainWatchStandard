---
type: decision
status: active
updated: 2026-06-08
tags: [presence, sensors, leakage]
---

# Presence Flags

Decision:

```yaml
presence_flags_are:
  - sensor availability
  - data quality
  - device/source signature
  - calibration mask

presence_flags_are_not:
  - pain evidence
  - stress evidence
  - activity evidence
```

Reason:

```yaml
old_issue: presence flags massively affected scores
cause: datasets have different sensor packs and labels
danger: model learns source identity instead of physiology
```

Implementation direction:

```yaml
train_time:
  - use masks to know which features valid
  - regularize or constrain presence effect
  - calibrate per sensor signature
  - simulate plausible device dropout

inference_time:
  - report missing sensors
  - reduce/omit ineligible heads
  - never boost pain because a sensor exists
```

