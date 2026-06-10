---
type: model
status: active
updated: 2026-06-09
tags: [time-series, shape, validation, leakage, pain, stress]
source_files:
  - scripts/explore_temporal_shape.py
  - scripts/r_temporal_shape_exploration.R
  - outputs/temporal_shape_summary/within_dataset_scorecard.csv
  - outputs/temporal_shape_summary/pain_leave_dataset_out.csv
  - outputs/temporal_shape_r/R_TEMPORAL_SHAPE_REPORT.md
---

# Temporal Shape Results

## Experiment

Raw normalized streams were sampled at 5, 10, and 30 second trailing histories. Each history was resampled to a common analysis grid, then evaluated with:

```yaml
feature_families:
  - robust level and distribution
  - temporal order and autocorrelation
  - spectral and wavelet shape
  - cross-sensor coupling
  - data quality and coverage

controls:
  - within-window time shuffle
  - reversed time
  - quality-only
  - dataset-only

validation:
  within_dataset: subject-grouped cross-validation
  pain_transfer: leave-one-dataset-out
  models:
    - regularized logistic regression
    - Extra Trees
```

This is exploratory evidence, not a clinical performance claim.

## Main Finding

Temporal shape contains useful information, but no portable universal pain signature is established.

```yaml
supported:
  - selected source-specific pain dynamics
  - stress versus exercise
  - WESAD stress
  - activity and motion context

not_supported:
  - one pooled pain model trusted across datasets
  - treating every generated time-series feature as useful
  - interpreting high PMED AUC as physiological pain detection
```

## Pain Results

Selected logistic AUC:

| Dataset | Window | Robust levels | Temporal | Shuffled temporal | Interpretation |
|---|---:|---:|---:|---:|---|
| PainMonit clinical | 30s | 0.584 | 0.619 | 0.505 | modest real order signal |
| PMED heat | 10s | 0.654 | 0.774 | 0.627 | order signal mixed with protocol quality |
| PMED heat | 30s | 0.818 | 0.855 | 0.775 | largely protocol-gap leakage |
| SILVER-Pain | 30s | 0.555 | 0.641 | 0.505 | useful within-source order signal |

Pain leave-dataset-out temporal AUC:

```yaml
painmonit: {5s: 0.474, 10s: 0.509, 30s: 0.411}
painmonit_pmed: {5s: 0.399, 10s: 0.302, 30s: 0.173}
physiopain_watch: {5s: 0.443, 10s: 0.477, 30s: 0.457}
rheumapain: {5s: 0.507, 10s: 0.515, 30s: 0.506}
silver_pain: {5s: 0.578, 10s: 0.569, 30s: 0.468}
```

Most results are near chance or worse. Source-specific gains do not transfer.

Dataset identity alone predicts pooled high-pain labels:

```yaml
dataset_only_auc:
  5s: 0.745
  10s: 0.745
  30s: 0.737
```

This is direct evidence of dataset/protocol shortcuts.

## PMED Defects

Two confirmed defects inflated PMED results:

```yaml
label_scale:
  source: COVAS 0-100
  old_ingest: named and stored as 0-10
  correction: divide by 10 and retain raw COVAS

timeline:
  observed_gap: roughly 66-86 seconds per run
  location: protocol transition into heating
  failure: post-gap rows were called full 30s windows despite only a few seconds of samples
  consequence: source row count and coverage predict pain phase
```

Pipeline now rejects windows whose observed samples do not cover the requested history within configured continuity tolerance.

## Other States

```yaml
stress_vs_exercise:
  temporal_auc: 0.955-0.987
  meaning: strong separability, mainly motion and cardiac context
  time_order_gain_over_shuffle: about 0.02-0.04

wesad_stress:
  best_region: about 10 seconds
  temporal_auc: 0.715 logistic, about 0.740 Extra Trees
  meaning: useful but levels and IBI/HR dominate

cognitive_load:
  auc: about 0.50-0.58 compact temporal
  meaning: current shape set adds little beyond BVP level/spread
```

Stress-versus-exercise is an activity/context classifier, not proof of subtle stress recognition.

## Features Worth Keeping

R and Python agree broad feature dumps are redundant. Among top 30 shape features, many tasks had 8-27 pairs with absolute correlation at least 0.95.

Keep compact sensor-specific candidates:

```yaml
bvp:
  - autocorrelation at 0.5s, 1s, and 2s
  - selected band power
  - spectral entropy
  - median-crossing count

eda:
  - late-minus-early level
  - autocorrelation
  - spectral centroid
  - compact wavelet energy
  - response timing

ibi_hr:
  - median IBI and HR
  - beat count and outlier fraction
  - RMSSD with duration and beat-count gate
  - SDNN only with stricter duration gate

respiration:
  - short-lag autocorrelation
  - dominant frequency
  - crossing and run structure

acceleration:
  - magnitude and jerk
  - autocorrelation
  - dominant frequency
  - crossing and run structure
```

Simple cross-sensor correlation and lag features usually added nothing. SILVER at 10 seconds showed a small exception; coupling remains experimental.

## Architecture Decision

Use one prediction each second with parallel trailing histories:

```yaml
cadence_hz: 1
histories_s: [5, 10, 30]
fusion:
  - each sensor encoder receives available histories
  - missing sensor/history is gated out
  - quality controls eligibility, not state score
  - state heads consume selected physiological features
```

Feature admission rule:

```yaml
required:
  - subject-grouped improvement
  - improvement over same calculator after time shuffle
  - stable direction across folds
  - acceptable calibration
  - no dependence on dataset, device, presence, or coverage shortcut
```

Pain heads should remain dataset/context aware until cross-dataset transfer exceeds chance.

## Artifacts

```yaml
python:
  - outputs/temporal_shape_exploration_5s/
  - outputs/temporal_shape_exploration_10s/
  - outputs/temporal_shape_exploration/

r:
  - outputs/temporal_shape_r/R_TEMPORAL_SHAPE_REPORT.md
  - outputs/temporal_shape_r/top_features_by_task.csv
  - outputs/temporal_shape_r/shape_vs_shuffle.csv
  - outputs/temporal_shape_r/subject_fixed_effect_summary.csv

compact:
  - outputs/temporal_shape_summary/multiscale_model_comparison.csv
  - outputs/temporal_shape_summary/within_dataset_scorecard.csv
  - outputs/temporal_shape_summary/pain_leave_dataset_out.csv
  - outputs/temporal_shape_summary/pain_dataset_only_control.csv
```
