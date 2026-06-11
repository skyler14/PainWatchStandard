---
type: lessons
status: active
updated: 2026-06-11
tags: [lessons, mistakes, modeling]
---

# Lessons

## Modeling

```yaml
presence_flags:
  lesson: sensor presence can become protocol label
  rule: use for quality/gating only, not state evidence

dataset_identity:
  lesson: pooled pain labels are strongly dataset/protocol separable
  rule: always run dataset-only and leave-dataset-out controls

high_auc:
  lesson: high AUC can mean protocol gap or target-scale bug
  rule: inspect temporal continuity, label units, and quality-only probes

parasympathetic_state:
  lesson: RMSSD/SDNN are proxies, not direct RSA
  rule: mark PNS labels weak unless respiration-linked RSA or lab markers exist

functional_pain_v1_run:
  lesson: weak SNS and homeostasis labels can be matched by dataset-only or quality-only controls
  rule: do not promote weak autonomic heads to truth until they beat controls under leave-dataset validation

activity_context:
  lesson: activity detection is easy and protocol-identifiable
  rule: use activity as first-class context/gate before pain or stress interpretation

portable_export:
  lesson: logistic JSON gives exact, small, watch-friendly baseline
  rule: use tree/boosting models for discovery unless ONNX/CoreML parity is verified

data_hydration:
  lesson: filling missing physiological sensors creates fake certainty and device shortcuts
  rule: hydrate by projection, short-gap interpolation, feature derivation, masking, and uncertainty; never invent absent sensor truth
```
