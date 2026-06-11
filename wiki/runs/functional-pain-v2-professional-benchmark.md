---
type: run
status: completed
updated: 2026-06-11
tags: [functional-pain-v2, hydration, professional-references, benchmark, export]
source_files:
  - config/functional_pain_v2.yaml
  - wiki/runs/functional-pain-v1-learning-run.md
  - wiki/model/autonomic-space-model.md
---

# Functional Pain V2 Professional Benchmark

Bounded benchmark completed June 11, 2026. It tested 10,580 rows, five
sensor projections, six literature-inspired feature arms, ten learners, and
leave-one-dataset-out transfer. Results are exploratory because PNS truth is a
physiology-derived proxy rather than independently measured RSA or PEP.

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

## Run Coverage

```yaml
rows: 10580
targets:
  - sympathetic_activation
  - parasympathetic_recovery_proxy
  - homeostasis
sensor_profiles:
  - native_full
  - watch_core
  - watch_plus_eda
  - watch_plus_respiration
  - chest_reference
not_run:
  watch_guided_breath: no inhale/exhale phase in current feature tables
  true_rsa: no sufficiently synchronized breath and beat waveform coverage
  true_pep: no impedance-cardiography PEP
  true_cvxeda: benchmark has derived EDA shapes, not raw decomposition
  temporal_filter: ordered session reconstruction was outside this bounded run
comparisons:
  literature_arm_screen: 84
  learner_benchmarks: 90
  leave_dataset_out: 57
  controls: 9
```

## Main Results

| Head | Best model/profile | Grouped AUC | Dataset-only AUC | Leave-dataset median | Interpretation |
|---|---|---:|---:|---:|---|
| SNS | GAM spline, watch core | 0.653 | 0.699 | 0.492 | Fails dataset control and transfers poorly; not usable evidence of generalized SNS separation. |
| PNS proxy | Random forest, chest reference | 0.849 | 0.721 | 0.822 | Strongest result, but partly circular because target was bootstrapped from related HRV/physiology inputs. |
| Homeostasis | Stacked vote, chest reference | 0.672 | 0.680 | 0.533 | Near controls and unstable across datasets; needs direct rest/recovery/archetype labels. |

Watch-only PNS was weaker: portable logistic reached AUC 0.735, only 0.014
above dataset identity and 0.022 above activity alone. Chest/native nonlinear
models gained roughly 0.11 AUC, indicating that richer physiology carries
recoverable structure, but this run cannot prove that structure is true vagal
activation.

SNS watch GAM improved substantially over its elastic-net literature screen
(0.653 versus 0.603), yet still lost to dataset identity (0.699). Its
leave-dataset AUC ranged from 0.468 to 0.657, with median 0.492. Treat this as
protocol learning, not a sympathetic score.

## Literature Variations In One Sentence Each

- **Autonomic-space proxy:** independent SNS/PNS feature families gave the strongest broad linear screen (SNS 0.615, PNS 0.788, homeostasis 0.665), but without PEP/RSA they remain correlated watch/chest proxies rather than clean branch isolation.
- **Phase-two stress ensemble:** classic HR/EDA range, variance, extrema, temperature, activity, and IBI features reached PNS AUC 0.769 but only SNS 0.586, showing better recovery-proxy reconstruction than generalized stress transfer.
- **WESAD multimodal proxy:** its broad HR/EDA/motion/temperature representation tied the autonomic-space arm because the 72-feature coverage cap selected the same available columns, so this run found no separable WESAD-specific advantage.
- **cvxEDA proxy:** cheap EDA level/slope/shape features reached PNS AUC 0.748 but SNS 0.516 and homeostasis 0.522; proper tonic/phasic decomposition needs raw EDA and could not be tested here.
- **HRV-biofeedback proxy:** interval variability and recovery-shape features reached PNS AUC 0.684, weaker than broad multimodal features, because most rows lack breath phase needed to isolate RSA.
- **Multimodal-pain proxy:** it tied broad autonomic/WESAD arms because no independent pain-residual layer was trained; current evidence supports autonomic context modeling, not direct universal pain inference.
- **Hydrated watch-core:** realistic HR/IBI, motion, and temperature preserved modest PNS information (best AUC 0.735) but did not isolate SNS from dataset context.
- **Hydrated EDA/respiration/chest:** richer projections improved nonlinear PNS reconstruction to 0.849, while SNS and homeostasis remained weak, so extra sensors alone do not repair target validity.

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

## Learners In One Sentence Each

- **Portable logistic regression:** best watch PNS result was 0.735 and it remains the easiest deployment baseline, but its small edge over controls is not enough for a validated PNS claim.
- **Elastic-net logistic regression:** useful for literature-arm screening and redundant features, but nonlinear learners beat it by about 0.06 AUC on the PNS proxy.
- **GAM spline:** best SNS learner at 0.653 by fitting smooth nonlinear marker effects, yet failed dataset-only control and leave-dataset transfer.
- **Linear discriminant analysis:** cheap covariance-based baseline produced no winning head and is retained mainly as a linear sanity check.
- **RBF SVM:** nonlinear kernel boundaries produced no exceptional result here and add deployment/calibration cost without measured benefit.
- **Random forest:** best overall PNS-proxy result at 0.849 and best Brier score at 0.125, but likely learned nonlinear pieces of the proxy-label recipe.
- **Extra Trees:** useful interaction probe, but did not beat random forest/boosting for PNS or GAM for SNS.
- **Gradient boosting:** nearly tied random forest on PNS (0.847 chest, 0.844 native), confirming nonlinear multimodal structure while sharing the same circular-label warning.
- **Small MLP:** competitive for SNS at 0.650 but failed controls, so added neural complexity did not produce trustworthy branch separation.
- **Stacked vote:** best homeostasis AUC at 0.672 and good SNS calibration, but neither head beat dataset identity.
- **Temporal state filter:** not tested in this run; it may stabilize display output, but cannot create physiological validity missing from window scores.

## Decision

Do not ship current SNS or homeostasis heads as physiological measurements.
Keep portable watch PNS as an experimental trend score and nonlinear
chest/native models as discovery tools only.

```yaml
next_validation:
  - collect paced-breath phase plus beat timestamps for RSA
  - collect independent rest/recovery labels
  - preserve raw EDA for tonic/phasic decomposition
  - evaluate within-dataset subject holdout and unseen-device holdout separately
  - require each head to beat dataset, quality, activity, reversed-time, and shuffled-time controls
  - calibrate outputs only after target validity passes
```
