---
type: dataset
status: active
updated: 2026-06-08
tags: [direct-pain, labels]
source_files:
  - docs/LABELED_DATASET_INSTANCE_ANALYSIS.md
  - src/painwatchstandard/routing.py
---

# Direct Pain Datasets

Rule:

```yaml
direct_pain_rows_train_pain_heads: true
auxiliary_rows_train_pain_heads: false
```

Direct pain sources:

```yaml
painmonit:
  branch: PMCD clinical
  strengths:
    - clinical direct pain labels
    - paired runup baselines now included
  risks:
    - sparse pain points
    - protocol/device signatures
    - runup baseline may still be clinical-context, not healthy baseline

painmonit_pmed:
  branch: experimental heat
  strengths:
    - induced heat pain
    - COVAS-derived pain target
    - rich BVP/EDA/temp/IBI/resp/ecg/emg where available
  risks:
    - experimental heat pain may differ from clinical pain

rheumapain:
  strengths:
    - rest/exercise pain context
    - workbook pain and diagnosis context joined
  risks:
    - mostly low/moderate pain
    - session label copied over many samples

physiopain_watch:
  strengths:
    - watch-like BVP/EDA/temp/ACC
    - pain types and no-pain rows
  risks:
    - scale semantics still need validation
    - overlap with multimodal source

multimodal_pain_watch:
  strengths:
    - same useful watch-like pain rows as PhysioPain branch
  risks:
    - possible duplicate/overlap with physiopain_watch

silver_pain:
  strengths:
    - pain labels across young/older cohorts
    - HR/BVP/EDA/temp watch-like coverage
  risks:
    - sparse labels relative to streams
    - scale semantics need readme validation
```

Do not treat as pain truth:

```yaml
not_pain_truth:
  - catsa
  - wesad
  - wesad_respiban
  - induced_stress_exercise
  - wearable_sports_health
  - apple_health_export
```

