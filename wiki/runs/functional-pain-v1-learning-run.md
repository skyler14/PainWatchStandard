---
type: run
status: complete
updated: 2026-06-10
tags: [functional-pain-v1, autonomic-space, learner, on-device, export]
source_files:
  - scripts/train_functional_pain_v1.py
  - outputs/functional_pain_v1_run/
  - wiki/model/functional-pain-v1.md
  - wiki/model/autonomic-space-model.md
---

# Functional Pain V1 Learning Run

Purpose: turn current aggressive temporal features into an on-device-friendly autonomic state learner.

## Goal

Train weak but useful state heads:

```yaml
states:
  sympathetic_activation:
    role: arousal / threat / pain-stress load
    labels:
      - WESAD stress
      - induced stress
      - cognitive load
      - direct pain high as weak positive

  parasympathetic_recovery_proxy:
    role: vagal/recovery movement
    labels:
      - bootstrapped high-IBI, low-HR, low-EDA, low-motion homeostatic windows
    warning: weakest label; no direct RSA/PEP truth yet

  homeostasis:
    role: near baseline / low departure
    labels:
      - WESAD baseline
      - CATSA baseline
      - direct pain low/no-pain except PMED heat controls

controls:
  activity_control: exercise/light activity context
  dataset_only: protocol shortcut probe
  quality_only: sensor availability shortcut probe
```

## Feature Sweep

Inputs come from prior 5s, 10s, and 30s temporal-shape extraction:

```yaml
feature_families:
  - base summaries
  - robust distribution
  - temporal shape
  - autocorrelation
  - spectral shape
  - wavelet energy
  - cross-sensor coupling
  - quality / coverage controls

histories:
  - 5s
  - 10s
  - 30s
```

## Learners

```yaml
portable_baseline:
  model: logistic regression
  reason:
    - exports cleanly as JSON
    - easy ONNX/CoreML equivalent later
    - small enough for watch/runtime inference

nonlinear_candidates:
  - HistGradientBoostingClassifier
  - ExtraTreesClassifier
  reason:
    - compare against portable model
    - discover nonlinear interactions
    - feature importance triage

future_if_installed:
  - LightGBM
  - XGBoost
  - ONNX export via skl2onnx
  - CoreML export via coremltools
```

## Export Rule

Use one unified training table. Exportable model must be generated from the same feature list and labels as the evaluation model.

```yaml
current_export:
  portable_json:
    includes:
      - feature names
      - median imputer values
      - standard scaler means
      - standard scaler scales
      - logistic coefficients
      - intercepts
    runtime: median-impute -> scale -> sigmoid per state -> ternary normalize

blocked_exports:
  onnx: environment missing skl2onnx
  coreml: environment missing coremltools
```

## Expected Review Questions

```yaml
validity:
  - Does main model beat dataset-only?
  - Does main model beat quality-only?
  - Does leave-dataset-out survive?
  - Do nonlinear learners beat portable logistic by enough to justify complexity?
  - Does parasympathetic proxy learn physiology or dataset artifact?

device:
  - Can same feature subset run on watch?
  - Which features require EDA or respiration and should be optional?
  - What happens under walking/light activity?
```

## End-Of-Run Summary

Completed local run.

```yaml
rows: 10580
feature_sets:
  portable_base_shape: 86
  aggressive_shape: 542
  quality_only: 27
  dataset_only: 2

exported:
  - outputs/functional_pain_v1_run/functional_pain_v1_portable_logistic.json
  - outputs/functional_pain_v1_run/metrics.csv
  - outputs/functional_pain_v1_run/feature_importance.csv
  - outputs/functional_pain_v1_run/FUNCTIONAL_PAIN_V1_RUN_REPORT.md
```

Label coverage:

```yaml
sympathetic_activation:
  rows: 9590
  prevalence: 0.468

parasympathetic_recovery_proxy:
  rows: 5802
  prevalence: 0.176

homeostasis:
  rows: 8636
  prevalence: 0.480

activity_control:
  rows: 10040
  prevalence: 0.099
```

## Main Results

Group-subject CV:

```yaml
activity_control:
  best: dataset_only logistic AUC 1.000
  sensor_models:
    extra_trees_portable: AUC 0.995
    hist_gradient_boosting_portable: AUC 0.995
    portable_logistic: AUC 0.973
  interpretation: exercise/activity rows are protocol-identifiable; useful as control, dangerous as shortcut

parasympathetic_recovery_proxy:
  aggressive_logistic: AUC 0.828
  portable_logistic: AUC 0.779
  extra_trees_portable: AUC 0.765
  hist_gradient_boosting_portable: AUC 0.757
  dataset_only: AUC 0.709
  quality_only: AUC about 0.66
  interpretation: model finds real-ish low-arousal/recovery physiology, but label is partly bootstrapped from same markers

homeostasis:
  portable_logistic: AUC 0.677
  extra_trees_portable: AUC 0.672
  dataset_only: AUC 0.671
  quality_only: AUC 0.652-0.668
  interpretation: weak; protocol and sensor coverage explain nearly as much as physiology

sympathetic_activation:
  best_control: quality_only_extra_trees AUC 0.700
  dataset_only: AUC 0.693
  aggressive_logistic: AUC 0.680
  hist_gradient_boosting_portable: AUC 0.671
  portable_logistic: AUC 0.638
  interpretation: current weak SNS label is too broad and shortcut-prone
```

Leave-dataset-out:

```yaml
sympathetic_activation:
  result: weak / unstable
  portable_logistic_auc_range: 0.38 to 0.56
  best_cases:
    physiopain_watch: about 0.56-0.60
    wesad: extra_trees about 0.62
  worst_cases:
    painmonit: below chance
    pmed: quality-only beats physiology
  conclusion: not portable

parasympathetic_recovery_proxy:
  result: strongest transfer-like behavior
  portable_logistic_auc_range: 0.61 to 0.87
  nonlinear_best:
    rheumapain: hist_gradient_boosting AUC 0.913
    painmonit: hist_gradient_boosting AUC 0.712
    wesad: extra_trees AUC 0.692
  conclusion: promising as recovery/low-arousal proxy, but not validated PNS/RSA truth

homeostasis:
  result: weak to modest
  portable_logistic_auc_range: 0.49 to 0.62
  best_cases:
    painmonit portable logistic AUC 0.619
    wesad extra_trees AUC 0.629
  conclusion: useful display control, not robust classifier yet
```

## Feature Findings

Top ExtraTrees features were mostly:

```yaml
dominant:
  - accelerometer mean/min/max/last
  - skin temperature mean/last/max
  - EDA mean/min/max/last
  - HR mean/last/min

less_visible_than_expected:
  - complex spectral/wavelet features
  - cross-sensor coupling
  - IBI/HRV-like features
```

Interpretation:

```yaml
activity_context: dominates many heads
temperature_and_eda: useful but confounded by device/contact/activity
aggressive_shape: helps PNS proxy, not SNS/homeostasis enough
complexity: not justified for watch v1 unless selected by stronger labels
```

## Learner Findings

```yaml
logistic:
  best_for: portable watch baseline, JSON export, easy CoreML/ONNX later
  result: competitive on PNS proxy; weak on SNS/homeostasis

hist_gradient_boosting:
  best_for: nonlinear discovery
  result: helps some leave-dataset PNS cases, not universally better

extra_trees:
  best_for: feature triage and nonlinear check
  result: strong for activity and some PNS holdouts; quality-only can beat main SNS

aggressive_shape:
  best_for: exploratory feature discovery
  result: PNS AUC improves from 0.779 to 0.828 in group CV
  cost: 542 features, less watch-friendly
```

## Export Format Notes

Actual exported model:

```yaml
format: portable JSON logistic
path: outputs/functional_pain_v1_run/functional_pain_v1_portable_logistic.json
runtime_ops:
  - median impute
  - standard scale
  - sigmoid per head
  - ternary normalize/display outside model
```

Not exported in this environment:

```yaml
onnx:
  reason: skl2onnx not installed
  expected_divergence: tiny numeric differences only if converter uses same impute/scale/sigmoid order

coreml:
  reason: coremltools not installed
  expected_divergence: tiny numeric differences only if preprocessing bundled identically

tree_models:
  export_status: not targeted for watch v1
  reason: larger, harder to keep identical across ONNX/CoreML/watch runtime
```

Holdout divergence across learner/output choice:

```yaml
portable_logistic_vs_nonlinear:
  pns_proxy: nonlinear helps in several holdouts
  sns: no stable improvement; controls often similar or better
  homeostasis: nonlinear sometimes helps WESAD, hurts SILVER/PainMonit

decision:
  keep portable logistic as watch-v1 export baseline
  use tree/boosting learners for discovery and feature selection
  do not ship SNS/homeostasis classifier as truth yet
```

## Architecture Decision From Run

Functional Pain V1 should not be a single classifier. Better structure:

```yaml
watch_v1:
  model:
    - portable logistic weak-state heads
    - deterministic functional_pain_v1 ternary display
    - activity/context gate
    - quality gate

display:
  ternary_internal: sympathetic / parasympathetic / homeostasis
  watch_2d_collapse:
    x: recovery direction, parasympathetic + homeostasis
    y: unresolved sympathetic load

training_next:
  - rebuild master after PMED fixes
  - add standard 5s/10s/30s feature table
  - create explicit low-motion rest / walking / recovery labels
  - add true RSA proxy where respiration exists
  - rerun with export converters installed
```

## Final Judgment

```yaml
ready_for_app_demo: yes, as exploratory physiology display
ready_for clinical pain inference: no
best_current_state: parasympathetic_recovery_proxy
biggest_failure: sympathetic_activation label/control leakage
main lesson: activity and sensor-quality controls must sit before pain-state interpretation
```
