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

functional_pain_v2:
  lesson: GAM improved SNS AUC to 0.653, but dataset identity alone reached 0.699 and unseen-dataset median fell to 0.492
  rule: nonlinear improvement is irrelevant when protocol controls remain stronger

pns_proxy_circularity:
  lesson: random forest reached 0.849 on a PNS proxy partly derived from related physiological inputs
  rule: call this proxy reconstruction until validated against synchronized respiration/RSA or another independent vagal marker

wesad_pns_protocol_validation:
  lesson: PNS-proxy learners trained without WESAD scored only 0.458-0.465 AUC on WESAD meditation versus TSST stress
  rule: current output must not be named parasympathetic activation; retrain against protocol and RSA labels before deployment

professional_method_proxies:
  lesson: broad autonomic-space, WESAD, and pain arms collapsed to the same available feature set, while cvxEDA and RSA could only be approximated
  rule: do not claim reproduction of a literature method unless its defining raw marker and protocol are present

homeostasis_labels:
  lesson: stacked homeostasis AUC 0.672 lost to dataset identity at 0.680 and transferred at median 0.533
  rule: acquire explicit archetype-specific rest, recovery, posture, and activity labels before further model tuning
```
