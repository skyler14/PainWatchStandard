# Full Stress Reference Report

Date: 2026-04-29

## What Was Rerun

The `xalentis/Stress` repo is an R project for stress prediction from wearable HR and EDA features. The original scripts are not a single clean package entrypoint; they are paper experiment scripts that depend on raw public datasets, a local R helper package, and heavier R/Python-backed modeling packages such as `caret`, `xgboost`, `randomForest`, and `keras`.

The included repo zips are enough for derived feature analysis:

- `StressData.zip`: 251,490 real merged rows, 99 subjects.
- `SynthesizedStressData.zip`: 256,800 synthetic rows, 200 synthetic subjects.

They are not enough to regenerate the raw feature tables from scratch, because the raw WESAD, SWELL, NEURO, UBFC-Phys, EXAM, Toadstool, and AffectiveROAD-style inputs are not bundled. We can still infer real-source provenance from subject prefixes: `N` = NEURO, `S` = SWELL, `U` = UBFC, `W` = WESAD. Synthetic rows use `X`.

Global Homebrew `Rscript` was still unavailable during this pass. Homebrew reported `r` as not installed and started compiling GCC as a dependency, which did not complete in time for the analysis. I created a local conda R environment at `.conda-r/` and ran R 4.6.0 from there.

## Original Repo Tricks

The reference project does not rely on raw HR/EDA samples directly. Its first trick is aggressive feature compression. The helper package computes rolling features over EDA and HR: means, medians, standard deviations, variances, minima, maxima, skew/kurtosis, ranges, and HR/EDA covariance. The final packaged feature tables keep 10 features: `hrrange`, `hrvar`, `hrstd`, `hrmin`, `edarange`, `edastd`, `edavar`, `hrkurt`, `edamin`, and `hrmax`.

The second trick is source harmonization. The project maps several public datasets into a common binary `metric` target for stress versus non-stress. That makes a single lightweight supervised task possible even though the source protocols differ substantially. This is directly relevant to pain, but also dangerous: harmonizing labels creates a usable training table, but it can hide protocol leakage if validation is not blocked by subject and source.

The third trick is synthetic subject construction. The synthetic generator splits real subjects by stress state, cuts the streams into 180-row state-pure blocks, then creates 200 synthetic subjects by concatenating four non-stress blocks followed by four stress blocks. In plain terms, it manufactures many balanced pseudo-sessions from real physiological fragments. It also removes HR and EDA outliers using an IQR filter before feature extraction.

The fourth trick is model diversity plus weighting. The original experiment scripts train XGBoost with logistic objective, class balancing, subsampling, feature-column sampling, and early stopping. They also train a small neural network over scaled features, then blend XGBoost and ANN scores with fixed weights such as `0.45/0.55` or `0.5/0.5`. The neural output is min-max normalized before blending. The ensemble is simple, but it attacks two different error profiles: boosted trees for nonlinear threshold/interactions, and a small ANN for smoother feature combinations.

The fifth trick is transfer-focused validation. The repo repeatedly asks whether a model trained on one or more sources works on a held-out source or unseen stream. That is the right instinct for us. Within-dataset subject holdout is not enough for a pain thermometer; source/protocol holdout is the integrity test.

## Our Python Reference Run

I first ran a Python/sklearn equivalent over the bundled zips because R was not available at the time. It used two lightweight nonlinear models: `HistGradientBoostingClassifier` and `RandomForestClassifier`. It evaluated subject holdout and source transfer.

Subject-holdout results were strong:

| Table | Model | ROC-AUC |
|---|---:|---:|
| StressData | HistGradientBoosting | 0.864 |
| StressData | RandomForest | 0.851 |
| SynthesizedStressData | HistGradientBoosting | 0.945 |
| SynthesizedStressData | RandomForest | 0.946 |

Synthetic-only training improved held-out real-source ROC-AUC over real-other-source training in every Python transfer run:

| Held-out source | Model | Real-other AUC | Synthetic AUC | Synthetic lift |
|---|---|---:|---:|---:|
| NEURO | HistGradientBoosting | 0.522 | 0.706 | +0.184 |
| SWELL | HistGradientBoosting | 0.599 | 0.919 | +0.320 |
| UBFC | HistGradientBoosting | 0.588 | 0.620 | +0.032 |
| WESAD | HistGradientBoosting | 0.406 | 0.658 | +0.252 |
| NEURO | RandomForest | 0.537 | 0.733 | +0.196 |
| SWELL | RandomForest | 0.643 | 0.943 | +0.300 |
| UBFC | RandomForest | 0.580 | 0.659 | +0.079 |
| WESAD | RandomForest | 0.438 | 0.682 | +0.244 |

The main Python finding is that synthetic multi-source training can improve transfer, but not uniformly. UBFC is dominated by positive labels, so plain accuracy is misleading there. AUC and balanced accuracy are more trustworthy than accuracy for these imbalanced sources.

## Our R Validation Run

After creating the local R environment, I added and ran:

```text
phase_2/analysis/stress_reference_r_analysis.R
```

This R script intentionally avoids the full `caret`/`xgboost`/`keras` dependency stack. It reads the bundled zips directly, applies train-only feature scaling, trains logistic models with and without class-balanced weights, and computes AUC, accuracy, and Brier score. This is not a reproduction of the paper ensemble; it is an R-native sanity check over the same derived tables.

R subject-holdout results:

| Table | Model | ROC-AUC | Accuracy | Brier |
|---|---|---:|---:|---:|
| StressData | GLM unweighted | 0.853 | 0.797 | 0.159 |
| StressData | GLM balanced | 0.853 | 0.798 | 0.161 |
| SynthesizedStressData | GLM unweighted | 0.810 | 0.764 | 0.172 |
| SynthesizedStressData | GLM balanced | 0.810 | 0.767 | 0.172 |

R source-transfer lift results:

| Held-out source | Model | Real-other AUC | Synthetic AUC | Combined AUC | Synthetic lift |
|---|---|---:|---:|---:|---:|
| NEURO | GLM balanced | 0.443 | 0.539 | 0.523 | +0.096 |
| SWELL | GLM balanced | 0.396 | 0.555 | 0.411 | +0.158 |
| UBFC | GLM balanced | 0.276 | 0.416 | 0.365 | +0.140 |
| WESAD | GLM balanced | 0.577 | 0.598 | 0.610 | +0.020 |

The R result is important because it confirms the same direction of effect with a much simpler model: synthetic rows add transfer coverage. But the lift is much smaller than with boosting/RF, and absolute source-transfer AUC is often poor. That means the useful signal is nonlinear and protocol-dependent; a linear model sees some general effect, but tree/boosting methods are doing real work.

## What We Learn For Pain

The reference Stress approach supports our preference for lightweight models before transformer-style work. Feature windows plus tree/boosting methods can produce meaningful transfer lift, and the model machinery is understandable enough to debug. For our pain pipeline, this argues for a next phase based on LightGBM/XGBoost/HistGradientBoosting over rigorously defined sensor windows, with per-source weights and source-blocked validation.

The synthetic trick is useful, but it should be applied carefully. For pain, we should not manufacture "pain truth" from stress or proxy data. We can synthesize or rebalance auxiliary physiological-state sessions to improve coverage of relaxed, stressed, active, recovering, and sensor-dropout states. Direct pain heads should still train only on direct-pain sources.

The source-transfer behavior is the central lesson. Models can look strong inside one table and become weak when the protocol changes. Any pain thermometer result should be considered provisional unless it beats metadata/protocol probes under leave-subject and leave-dataset validation. Accuracy alone is not acceptable because some sources are heavily imbalanced.

The feature set is also instructive. HR range/variance/std/min/max and EDA range/std/variance/min appear sufficient to demonstrate stress-state transfer. That maps well to watch-like sensors, but it does not cover pain-specific motor guarding, skin temperature drift, BVP morphology, HRV, or motion context. For pain, these stress features should be auxiliary state inputs, not the whole signal.

## PostgreSQL Demo Export

I updated the top-level exporter so the Phase 2 dump includes the prior normalized pain tables plus the Stress reference auxiliary tables and both Python and R analysis outputs. The intended output is:

```text
../_exports/pain_demo_postgres_phase2_all_datasets_with_stress.sql.gz
```

The schema name is:

```text
pain_demo_phase2
```

The dump includes direct normalized streams, all-dataset 1 Hz/30 s windows, baseline state atlas tables, self-supervised metrics/embeddings, Stress auxiliary feeder rows, Python stress metrics/lifts, and R stress metrics/lifts. The Stress auxiliary table has 508,290 rows and should be treated as state/proxy data, not direct pain supervision.

## Next Action

Redo Phase 1 as a multi-task, source-blocked lightweight modeling pass:

1. Direct-pain ordinal head: PainMonit, RheumaPain, PhysioPain watch.
2. Auxiliary stress/state head: WESAD, EPM-E4, CATSA, induced stress/exercise, xalentis Stress rows.
3. Activity/motion head: ACC-heavy datasets and exercise protocols.
4. Baseline/state anchor head: relaxed/rest/no-pain intervals where available.
5. Dataset-balanced training batches and source-blocked validation.
6. Report models by sensor subset: Apple-Watch-like, E4-like, autonomic-core, motion-only, and full available.
