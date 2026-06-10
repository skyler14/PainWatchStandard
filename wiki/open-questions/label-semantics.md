---
type: open_question
status: active
updated: 2026-06-09
tags: [labels, pain-scale]
---

# Label Semantics

Question:

```yaml
which pain scales are exactly comparable across datasets: unknown
```

Need validate:

```yaml
physiopain:
  field: pain_scale
  issue: values 1-5, no_pain scale_1 semantics need source confirmation

silver_pain:
  field: PainLevel
  issue: scale mapping and cohort semantics need readme/source validation

painmonit:
  fields: PMCD pain rates, PMED COVAS
  confirmed: PMED COVAS is 0-100 and must be divided by 10
  issue: clinical vs induced heat must stay separable

rheumapain:
  fields: rest/exercise workbook pain
  issue: weak session-level labels, limited high pain
```

Current policy:

```yaml
use_as_direct_pain: yes, but preserve dataset/context fields
collapse_to_universal_truth_without_checks: no
```

PMED ingest now preserves raw `source_pain_covas_0_100` and emits corrected `target_pain_nrs_0_10`.
