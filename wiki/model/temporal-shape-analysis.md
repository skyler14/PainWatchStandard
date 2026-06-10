---
type: model
status: active
updated: 2026-06-09
tags: [time-series, shape, dynamics, python, r]
source_files:
  - src/painwatchstandard/sensors.py
  - src/painwatchstandard/windowing.py
  - docs/STATE_NORMALIZATION_AND_R_FINDINGS.md
external_sources:
  - https://tsfresh.readthedocs.io/en/latest/text/list_of_features.html
  - https://www.aeon-toolkit.org/en/stable/examples/transformations/catch22.html
  - https://www.aeon-toolkit.org/en/stable/examples/classification/classification.html
  - https://cran.r-project.org/web/packages/theft/refman/theft.html
  - https://cran.r-project.org/package=nonlinearTseries
  - https://doi.org/10.32614/rj-2019-023
  - https://jmlr.org/papers/v21/19-047.html
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC7710683/
  - https://www.centropiaggio.unipi.it/sites/default/files/greco2015cvxeda.pdf
---

# Temporal Shape Analysis

Actual multiscale experiment results: [[model/temporal-shape-results]].

## Current Reality

Runs remain full-length normalized streams.

Current master emits:

```yaml
cadence: one row each second
memory: trailing 30 seconds
window_overlap: 29 seconds between adjacent rows
```

Current features preserve limited shape:

```yaml
present:
  - mean
  - standard deviation
  - minimum
  - maximum
  - last value
  - linear slope
  - simple peak count
  - valid fraction
  - acceleration stillness
  - IBI RMSSD
  - IBI SDNN

missing:
  - autocorrelation shape
  - spectral/frequency shape
  - nonlinear complexity
  - waveform motifs
  - change points
  - cross-sensor lag/coupling
  - within-window early-vs-late response
```

Thus current table does not fully exploit 30-second sensor shape.

## Priority 1: Cheap, Interpretable Shape Features

Add manually in Python first. No large dependency required.

```yaml
distribution_shape:
  - median
  - mad
  - q10
  - q25
  - q75
  - q90
  - iqr
  - skewness
  - kurtosis
  - rms

temporal_shape:
  - first_half_mean
  - second_half_mean
  - late_minus_early
  - first_value
  - last_minus_first
  - max_time_fraction
  - min_time_fraction
  - longest_above_median_run
  - longest_below_median_run
  - zero_crossing_or_median_crossing_count

dependence:
  - autocorrelation_lag_1
  - autocorrelation_lag_2
  - autocorrelation_lag_5
  - partial_autocorrelation_small_lags

change:
  - max_absolute_first_difference
  - mean_absolute_first_difference
  - first_difference_std
  - second_difference_energy
  - largest_mean_shift_split

spectral:
  - dominant_frequency
  - spectral_centroid
  - spectral_entropy
  - low_band_power
  - mid_band_power
  - high_band_power
  - low_high_power_ratio
```

Why first:

```yaml
benefits:
  - interpretable
  - streamable
  - cheap enough for 1Hz live inference
  - exposes actual waveform dynamics
  - easy to test against shuffled-time controls
```

## Priority 2: Sensor-Specific Physiology

### EDA

Raw EDA mixes slow tonic level and fast phasic responses.

```yaml
recommended:
  - tonic_level
  - tonic_slope
  - phasic_driver_area
  - phasic_peak_count
  - phasic_peak_amplitude_mean
  - phasic_peak_rise_time
  - phasic_peak_recovery_time
  - phasic_activity_fraction
```

Research method: cvxEDA decomposes skin conductance into tonic and phasic components.

Live caution:

```yaml
full_cvxeda_each_tick: likely too expensive
better:
  - offline exploratory benchmark
  - causal approximation for deployment
  - compare decomposition features against simple EDA differences
```

### IBI / HRV

Current RMSSD and SDNN useful, but duration matters.

```yaml
30_second_window:
  RMSSD: plausible ultra-short feature, validate per context
  SDNN: minimum commonly studied duration around 30s
  frequency_domain_HRV: generally too fragile for moving 30s windows
  nonlinear_HRV: likely unstable with sparse beats
```

Add:

```yaml
ibi:
  - median_ibi
  - pnn20
  - pnn50_when_enough_beats
  - poincare_sd1
  - poincare_sd2_with_quality_gate
  - beat_count
  - ectopic_or_outlier_fraction
```

Dynamic exercise requires stricter quality/duration rules than rest.

### BVP / ECG

```yaml
candidate_shape:
  - pulse_peak_count
  - interpeak_interval_mean
  - interpeak_interval_variation
  - pulse_amplitude_median
  - pulse_width
  - rise_time
  - decay_time
  - waveform_template_correlation
  - signal_quality_index
```

Avoid treating raw BVP mean as physiology across devices; baseline and gain vary.

### Respiration

```yaml
candidate_shape:
  - respiratory_rate
  - breath_interval_variability
  - inhale_duration
  - exhale_duration
  - inhale_exhale_ratio
  - amplitude_variability
  - irregularity
  - apnea_or_flat_fraction
```

### Acceleration

```yaml
candidate_shape:
  - vector_magnitude_area
  - jerk_mean
  - jerk_rms
  - dominant_motion_frequency
  - posture_or_orientation_change
  - periodicity
  - burst_fraction
  - still_to_motion_transition_count
```

## Priority 3: Cross-Sensor Dynamics

Single-sensor features miss coordinated physiology.

```yaml
pairs:
  - HR_vs_EDA
  - BVP_vs_EDA
  - HR_vs_respiration
  - EDA_vs_acceleration
  - temperature_vs_EDA
  - HR_vs_acceleration

features:
  - contemporaneous_correlation
  - maximum_cross_correlation
  - lag_at_max_correlation
  - rolling_slope_ratio
  - coherence_in_selected_bands
  - mutual_information_approximation
  - response_order_flag
```

Important:

```yaml
motion_artifact:
  acceleration_coupled_BVP_or_EDA_change:
    possible_meaning: artifact, not state

physiological_coupling:
  HR_and_EDA_change_without_large_motion:
    possible_meaning: autonomic arousal
```

Cross-sensor features need synchronized streams and missing-sensor masks.

## Priority 4: General Feature Libraries

### Python

```yaml
catch22:
  features: 22 compact time-order features
  strengths:
    - fast
    - interpretable
    - autocorrelation/nonlinearity/fluctuation coverage
  fit: best first broad benchmark

tsfresh:
  features: hundreds of configurable calculators
  strengths:
    - broad discovery
    - feature selection support
    - rolling time-series workflow
  risks:
    - expensive
    - massive multiple-testing/leakage risk
  fit: offline discovery on sampled folds, not automatic production

TSFEL:
  features: statistical, temporal, spectral, fractal
  strengths:
    - organized feature domains
    - explicit computational-cost metadata
  fit: useful benchmark against custom/catch22 set

aeon:
  methods:
    - catch22 transform
    - shapelet transform
    - ROCKET/MiniROCKET
    - HIVE-COTE families
  fit: raw-window classification benchmark

Kymatio:
  method: wavelet scattering
  strengths:
    - stable multi-scale shape representation
    - fixed filters, fewer learned parameters
  fit: high-rate BVP/ECG/EDA exploratory branch
```

### R

```yaml
theft:
  role: common interface over catch22, feasts, tsfeatures, tsfresh, TSFEL, others
  fit: broad feature comparison and redundancy analysis

Rcatch22:
  role: compact canonical shape features
  fit: direct Python/R reproducibility check

nonlinearTseries:
  methods:
    - sample entropy
    - detrended fluctuation analysis
    - recurrence quantification analysis
    - correlation dimension
    - Lyapunov estimates
    - surrogate tests
  fit: exploratory nonlinear analysis
  caution: many methods need longer, clean, stationary series than 30s

dtwclust:
  method: dynamic-time-warping clustering
  fit:
    - discover repeated response shapes
    - compare pain/stress/exercise trajectories
    - cluster whole runs or event-aligned segments

feasts_and_tsfeatures:
  role: autocorrelation, entropy, trend, seasonal/spectral summaries
  fit: compact exploratory comparison

functional_data_analysis:
  packages:
    - fda
    - refund
    - fda.usc
  methods:
    - smooth each run as curve
    - functional PCA
    - scalar-on-function regression
    - curve clustering/classification
  fit: whole-run and event-aligned morphology, not live per-tick first pass
```

## Priority 5: Shape-Learning Models

### Shapelets

Shapelets are short subsequences whose presence/absence distinguishes states.

```yaml
good_for:
  - interpretable waveform motifs
  - finding EDA rise patterns
  - pulse morphology changes
  - short transition signatures

risks:
  - expensive search
  - can learn dataset/protocol artifacts
  - raw sampling rates differ
```

Use randomized shapelet transform, not exhaustive enumeration.

### ROCKET / MiniROCKET

Random convolutions convert raw windows into many shape-sensitive features.

```yaml
good_for:
  - strong raw-window baseline
  - fast compared with deep networks
  - captures local patterns at many scales

risks:
  - less interpretable than hand features
  - fixed-length aligned input required
  - missing sensors/device packs need separate channels/masks
```

### Temporal CNN / TCN

```yaml
good_for:
  - causal deployment
  - multi-scale receptive fields
  - raw or lightly processed sensor channels

risks:
  - leakage and overconfidence
  - sensor-pack mismatch
  - needs stronger validation than tabular models
```

### Self-Supervised / Contrastive

Potential later:

```yaml
goal: learn common representations from unlabeled full runs
benefit: labels are sparse and datasets heterogeneous
required:
  - channel-aware missingness
  - dataset-balanced sampling
  - augmentations that preserve physiology
  - downstream leave-dataset-out validation
```

Do not start here. First establish feature-based benchmark and leakage controls.

## Definitive-Trend Test

Every candidate feature must beat these controls:

```yaml
controls:
  time_shuffle:
    purpose: does ordering matter?

within_window_reverse:
    purpose: does direction matter?

phase_randomization:
    purpose: does exact waveform matter beyond spectrum?

sensor_permutation:
    purpose: is cross-sensor coupling real?

dataset_only_model:
    purpose: could source identity explain result?

presence_only_model:
    purpose: are sensor masks driving state?

simple_summary_model:
    purpose: does complex shape improve beyond current mean/std/slope?
```

Required evaluation:

```yaml
splits:
  - group by subject
  - leave dataset out
  - separate clinical pain from experimental heat
  - stratify sensor signature

metrics:
  - AUC
  - precision_recall
  - Brier score
  - calibration error
  - false-positive rate in explicit no-pain
  - performance under plausible sensor dropout

selection:
  feature_selection_inside_training_fold: mandatory
```

## Recommended Experiment Order

```yaml
phase_A:
  - add compact custom shape features
  - add catch22 benchmark
  - test shuffled-time controls

phase_B:
  - add sensor-specific EDA, IBI, BVP/ECG, respiration, ACC features
  - add cross-sensor lag/correlation
  - compare against current summaries

phase_C:
  - run R theft feature comparison on sampled balanced windows
  - use nonlinearTseries only where duration/sample count supports it
  - use dtwclust/FDA on whole runs or event-aligned segments

phase_D:
  - benchmark MiniROCKET and randomized shapelets on fixed raw windows
  - require leave-dataset improvement and calibrated confidence

phase_E:
  - only then test causal TCN or self-supervised representation learning
```

## Main Recommendation

Do not replace current features wholesale.

Build layered feature sets:

```yaml
core:
  current summaries + robust quantiles + differences + autocorrelation

physiology:
  sensor-specific pulse/EDA/HRV/respiration/motion features

coupling:
  cross-sensor timing and motion-artifact controls

experimental:
  catch22, wavelet scattering, shapelets, MiniROCKET
```

Promote features only when they improve subject/dataset-held-out performance and calibration beyond current summaries.
