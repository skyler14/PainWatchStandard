---
type: run
status: proposed
updated: 2026-06-11
tags: [functional-pain-v2, hydration, professional-references, benchmark, export]
source_files:
  - config/functional_pain_v2.yaml
  - wiki/runs/functional-pain-v1-learning-run.md
  - wiki/model/autonomic-space-model.md
---

# Functional Pain V2 Professional Benchmark

No training run has started. This page defines proposed experiment for review.

## Product Goal

Functional Pain V2 supports mindfulness/rest sessions, walking, and light activity. Internal state stays expressive:

```yaml
internal:
  - sympathetic_activation
  - parasympathetic_activation_or_recovery
  - homeostasis_or_context_baseline

controls:
  - activity
  - sensor_quality
  - device_profile
  - baseline_archetype

watch_display_initial:
  x_axis: recovery / movement toward PNS and baseline
  y_axis: unresolved sympathetic load
```

Pain and stress initially belong to same SNS-response family. Pain-specific model becomes optional residual layer after autonomic/context controls.

## Data Hydration

Hydration does not mean inventing missing sensors. It means converting each source into realistic device views.

```yaml
safe_hydration:
  - canonical timestamps and units
  - short-gap interpolation only
  - derive heart intervals from high-quality ECG/BVP when valid
  - derive watch-compatible summaries from richer raw streams
  - create multiple device-profile projections
  - add dropout simulation
  - preserve masks for eligibility/quality only
  - add proxy uncertainty

unsafe_hydration:
  - generate fake EDA from HR
  - generate fake respiration waveform from respiratory rate
  - treat missing sensor as zero
  - let sensor presence become state evidence
  - calculate baselines using held-out subject test data
```

Proposed variants:

```yaml
native_full:
  meaning: all source sensors, discovery upper bound

watch_core:
  meaning: HR/IBI + ACC + temperature, optional SpO2/respiratory rate
  deployment: standard watch-like

watch_guided_breath:
  meaning: watch core plus known inhale/exhale phase from app
  deployment: mindfulness session PNS-response proxy

watch_plus_eda:
  meaning: watch core plus EDA accessory

watch_plus_respiration:
  meaning: watch core plus respiration waveform/accessory

chest_reference:
  meaning: ECG + respiration + EDA + motion, optional impedance cardiography
  deployment: validation/lab, not standard watch
```

Each native source is rerun through every compatible projection. Comparison asks whether professional-method gains survive after restriction to realistic watch sensors.

## Professional Reference Arms

### Autonomic Space

Adopt Berntson/Cacioppo/Quigley idea: model SNS and PNS independently rather than as one inverse slider.

```yaml
outputs:
  - sns_score
  - pns_score
  - cab_proxy: pns_z - sns_z
  - car_proxy: pns_z + sns_z
  - autonomic_mode

modes:
  - reciprocal_sympathetic
  - reciprocal_parasympathetic
  - coactivation
  - coinhibition
  - uncoupled_sns
  - uncoupled_pns
  - homeostatic
```

True PEP remains chest/lab-only. Watch variants use EDA/vascular/temp/HR proxies with explicit uncertainty.

### Phase-Two Stress Ensemble

Adopt Vos/Trinh/Sarnyai/Rahimi Azghadi ideas:

```yaml
features:
  - HR range/variance/std/min/max/kurtosis
  - EDA range/variance/std/min
  - expanded activity/temp/IBI features

training:
  - balanced state blocks
  - source-balanced batches
  - tree learner plus smooth learner
  - stacked probability output

guardrail:
  synthetic_blocks: allowed for SNS/context balance
  synthetic_pain_truth: forbidden
```

### WESAD Multimodal

Adopt multimodal stress/baseline/meditation/recovery protocol:

```yaml
heads:
  - stress_arousal
  - baseline
  - meditation_or_recovery
  - activity

comparison:
  - E4/watch channels
  - Respiban chest channels
  - watch-hydrated projection
```

### cvxEDA

Adopt tonic/phasic EDA split for devices carrying EDA:

```yaml
tonic:
  - level
  - slope
  - baseline_delta

phasic:
  - SCR count
  - amplitude
  - area
  - rise time
  - recovery time

comparison:
  - full cvxEDA-like decomposition
  - cheap causal approximation
  - current mean/std/slope/peak baseline
```

### HRV Biofeedback

Adopt vagal/recovery model:

```yaml
watch_core:
  - RMSSD where beat series valid
  - SDNN duration-gated
  - HR recovery slope

guided_breath:
  - heart response aligned to known breath phase
  - paced-breath response amplitude

respiration_available:
  - peak-valley RSA
  - respiratory-band HRV
  - respiration-heart coherence
```

### Multimodal Pain

Adopt BioVid/PainMonit/Werner-style direct pain learning only after autonomic/context features:

```yaml
inputs:
  - sns_score
  - pns_score
  - homeostasis_score
  - activity
  - direct sensor features

output:
  - pain_residual

rule:
  pain_residual: trains only on direct-pain datasets
  stress_proxy: never becomes pain truth
```

## Feature Strategy

Aggressive discovery phase:

```yaml
histories_s: [5, 10, 30, 60]
families:
  - robust levels and quantiles
  - temporal differences and slopes
  - autocorrelation
  - spectral entropy and selected bands
  - wavelet energy
  - sensor coupling
  - tonic/phasic EDA
  - HRV/RSA where valid
  - archetype-relative z-scores
```

Feature survival rule:

```yaml
keep_only_if:
  - improves subject holdout
  - improves leave-dataset or leave-device holdout
  - beats shuffled-time version when claiming shape
  - beats dataset/quality/presence controls
  - stable direction across folds
  - computable on target device profile
```

## Learner Benchmark

One training table feeds every learner. No separate feature-generation forks.

```yaml
learners:
  - portable logistic
  - elastic-net logistic
  - generalized additive model
  - linear discriminant analysis
  - RBF SVM
  - random forest
  - Extra Trees
  - gradient boosting
  - small MLP
  - stacked ensemble

temporal_output_filter:
  - hidden Markov model or deterministic exponential smoothing
```

Primary selection priorities:

```yaml
priority_order:
  1: leave-dataset/device reproducibility
  2: calibration
  3: activity robustness
  4: export parity
  5: size and latency
  6: within-dataset AUC
```

## Comparisons

```yaml
compare:
  v1_vs_v2:
    - original v1 portable logistic
    - v2 watch-core models
    - v2 professional-reference arms

  native_vs_hydrated:
    - native full sensors
    - watch core
    - watch plus EDA
    - watch plus respiration
    - chest reference

  feature_scope:
    - compact portable
    - aggressive discovery
    - professional-specific

  model_scope:
    - linear
    - nonlinear trees
    - kernel
    - neural
    - ensemble
```

Required controls:

```yaml
controls:
  - dataset_only
  - quality_only
  - sensor_presence_only
  - activity_only
  - shuffled_time
  - reversed_time
```

## Export And Device Plan

Preferred reference graph:

```text
canonical features
  -> median imputation
  -> scaling
  -> state logits
  -> calibration
  -> ternary normalization
  -> activity/quality gating
  -> 2D watch projection
```

All formats must receive same graph and same holdout rows:

```yaml
formats:
  - Python reference
  - portable JSON
  - ONNX
  - CoreML

parity_tolerance:
  probability_max_abs_error: 0.0001
  ternary_coordinate_max_abs_error: 0.0001
  classification_agreement: 99.99%
```

Any export exceeding tolerance is rejected, not silently accepted.

## Expected Cost

```yaml
hydration_and_feature_build: moderate
linear_models: fast
tree_models: moderate
svm: potentially slow on full rows; sample/tune first
small_mlp: moderate
export_parity: fast after converters available
full_nested_hyperparameter_search: intentionally excluded from first run
```

First run should use bounded model grids and fixed seeds. Broad exhaustive tuning comes only after integrity controls pass.

## Approval Questions

Before run:

```yaml
confirm:
  - pain and stress share initial SNS family
  - PNS remains proxy unless RSA/guided-breath evidence exists
  - homeostasis uses archetype-specific baseline
  - walking/light activity is context, not failure
  - no fake sensor synthesis
  - install ONNX/CoreML converters only when approved
  - pain residual remains optional second layer
```

## End-Of-Run Template

After execution this page will record:

```yaml
data:
  - rows per hydrated profile
  - feature coverage
  - label coverage

results:
  - learner metrics
  - professional-arm metrics
  - source/device holdouts
  - activity robustness
  - calibration

exports:
  - model sizes
  - latency
  - ONNX/CoreML/JSON parity
  - divergent rows and maximum error

lessons:
  - effective markers
  - failed markers
  - leakage
  - device-specific behavior
  - generalized changes for lessons.md
```

## Statistical Learners In One Sentence Each

- **Portable logistic regression:** weighted sensor features produce simple state logits that are transparent, tiny, and easy to reproduce across watch runtimes.
- **Elastic-net logistic regression:** logistic regression with L1/L2 penalties removes redundant features while keeping correlated physiological groups stable.
- **Generalized additive model:** learns smooth nonlinear response curves for each marker while remaining understandable as separate physiological effects.
- **Linear discriminant analysis:** finds inexpensive linear state boundaries by modeling class means and shared covariance.
- **RBF SVM:** separates states using curved similarity boundaries and can work well on small nonlinear physiological datasets, but scales poorly and is harder to explain.
- **Random forest:** averages many bootstrapped decision trees to model nonlinear thresholds and interactions with reasonable robustness.
- **Extra Trees:** uses highly randomized trees to expose feature interactions quickly and provide a strong discovery benchmark.
- **Gradient boosting:** builds trees sequentially to correct prior errors, usually giving strong tabular accuracy at cost of calibration and export complexity.
- **Small MLP:** combines multimodal features through compact neural layers that can export well but require stronger regularization and validation.
- **Stacked ensemble:** learns how to blend linear, tree, and neural probabilities so different error patterns can complement each other.
- **Hidden Markov/state filter:** applies physiological transition constraints after per-window scoring so displayed states do not jump unrealistically each second.

## Current Recommendation Before Run

Run v2 only after review. Proposed likely watch candidate:

```yaml
features:
  - watch-core compact features
  - guided-breath features when session supplies phase
  - optional EDA/respiration modules

model:
  - elastic-net or portable logistic per state
  - calibrated ternary output
  - activity and quality gates
  - deterministic temporal filter

discovery:
  - Extra Trees
  - gradient boosting
  - professional-reference feature arms
```
