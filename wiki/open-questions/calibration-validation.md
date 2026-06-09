---
type: open_question
status: active
updated: 2026-06-08
tags: [calibration, confidence]
---

# Calibration Validation

Problem:

```yaml
old_auc_looked_ok_but_irl_readings_absurd: true
```

Need prove:

```yaml
confidence:
  - calibrated by sensor signature
  - respects state competition
  - lower under missing/dropout states
  - not inflated by source/protocol leakage

pain_score:
  - stable across subjects
  - stable across datasets
  - not just stress/activity proxy
  - not boosted by watch wear context alone
```

Validation ideas:

```yaml
required:
  - calibration plots by dataset
  - calibration plots by sensor signature
  - leave-dataset-out tests
  - no-pain false positive audits
  - high-HR walking/workout examples
  - missing sensor dropout simulations
```

