# Phase 2 Reference Analysis And Refined Approach

Date: 2026-04-29

## Reference Repo

The reference repo is cloned here:

```text
phase_2/reference/Stress
```

Upstream:

```text
https://github.com/xalentis/Stress
```

The README identifies the project as code for "Ensemble Machine Learning Model Trained on a New Synthesized Dataset Generalizes Well for Stress Prediction Using Wearable Devices" by Gideon Vos, Kelly Trinh, Zoltan Sarnyai, and Mostafa Rahimi Azghadi. The paper is associated with Journal of Biomedical Informatics DOI `10.1016/j.jbi.2023.104556` and arXiv `2209.15146`. The arXiv abstract says the authors evaluate generalization from small single-protocol datasets, merge public datasets, synthesize a larger training dataset, and combine gradient boosting with an artificial neural network. It reports 85% predictive accuracy on new validation data and a 25% performance improvement over single models trained on small datasets.

The repo includes R scripts and an R helper package. Global Homebrew `Rscript` was still unavailable during this pass, so I created a local conda R 4.6.0 environment at `.conda-r/`. I used `thepipe` to map the repo structure, wrote a Python/sklearn equivalent over the bundled derived CSVs, and added an R validation script that avoids the heavy `caret`/`xgboost`/`keras` dependency stack. The scaffold notes are saved in `phase_2/reference/STRESS_SCAFFOLDING.md`, and the full report is saved in `phase_2/FULL_STRESS_REFERENCE_REPORT.md`. The original R scripts depend on `stresshelpers`, `caret`, `xgboost`, `randomForest`, `keras`, and raw datasets when regenerating the CSVs from scratch.

## Included Data Versus Extra Downloads

The cloned repo includes:

```text
StressData.zip
SynthesizedStressData.zip
```

Each zip contains one derived feature CSV. `StressData.csv` has 251,490 rows, 99 subjects, and 10 engineered HR/EDA features plus a binary stress metric. `SynthesizedStressData.csv` has 256,800 rows, 200 synthetic subjects, and the same feature schema.

The included zips are sufficient to run the reference feature-level stress analysis. They do not contain the original raw datasets. To regenerate the CSVs from raw signals, we would need the raw sources referenced in the R scripts: WESAD, SWELL, NEURO/Non-EEG neurological status, UBFC-Phys, EXAM, and optional sources used by other scripts such as Toadstool and AffectiveROAD. We can infer which source a row came from in `StressData.csv` by subject prefix: `N` = NEURO, `S` = SWELL, `W` = WESAD, `U` = UBFC. Synthetic rows use `X` subjects and do not retain row-level raw-source provenance after synthesis.

## Reference Analysis Procedure

I added:

```text
phase_2/analysis/stress_reference_analysis.py
```

This script reads the bundled `StressData.zip` and `SynthesizedStressData.zip`, trains two lightweight classifiers over the 10 engineered HR/EDA features, and evaluates three conditions. First, subject-holdout within real StressData and within SynthesizedStressData. Second, source-transfer from the real datasets: train on three real sources and test on the held-out fourth source. Third, synthetic transfer: train on synthetic-only or real-other-plus-synthetic and test on the held-out real source.

This is not an exact reproduction of the paper's R ensemble because R is unavailable here and the original scripts use xgboost plus neural network ensembles. It is still a useful integrity check because it asks the same practical question: does a synthesized multi-source stress training set improve transfer to unseen wearable stress data?

## Reference Results

Subject-holdout results were strong. On `StressData`, gradient boosting reached ROC-AUC `0.864`; random forest reached `0.851`. On `SynthesizedStressData`, gradient boosting reached ROC-AUC `0.945`; random forest reached `0.946`. This indicates that the packaged feature data has strong internal stress classification signal.

Cross-source transfer is the more relevant result. Training on other real sources alone transferred poorly to several held-out sources. Synthetic-only training improved ROC-AUC over real-other-source training on every held-out real source in this run:

| Held-out source | Model | Real-other AUC | Synthetic AUC | Synthetic AUC lift |
|---|---|---:|---:|---:|
| NEURO | HistGradientBoosting | 0.522 | 0.706 | +0.184 |
| SWELL | HistGradientBoosting | 0.599 | 0.919 | +0.320 |
| UBFC | HistGradientBoosting | 0.588 | 0.620 | +0.032 |
| WESAD | HistGradientBoosting | 0.406 | 0.658 | +0.252 |
| NEURO | RandomForest | 0.537 | 0.733 | +0.196 |
| SWELL | RandomForest | 0.643 | 0.943 | +0.300 |
| UBFC | RandomForest | 0.580 | 0.659 | +0.079 |
| WESAD | RandomForest | 0.438 | 0.682 | +0.244 |

The most important pattern is not the exact number; it is that synthetic multi-source training generally improved transfer. This supports using stress/proxy datasets in our Phase 2 pain pipeline as auxiliary state coverage, provided we keep pain labels separate.

The R validation run confirms the direction with simpler models. Balanced logistic GLMs showed synthetic AUC lift on every held-out source: NEURO `+0.096`, SWELL `+0.158`, UBFC `+0.140`, and WESAD `+0.020`. The smaller R lift versus Python boosting/RF is useful: it says synthetic coverage helps even linearly, but the stronger transfer behavior depends on nonlinear tree/boosting interactions.

## Feeder Adjustment For Reference Stress Data

I added:

```text
src/stress_reference_feeder_adapter.py
```

It converts the repo's packaged stress feature CSVs into feeder-style Parquet rows:

```text
phase_2/analysis/outputs/stress_reference_feeder_rows.parquet
```

The adapter produced 508,290 rows across 299 subjects. These rows carry HR/EDA engineered features and `aux_stress_label`, but `target_available = 0` and no pain target. This is intentional. These rows should be used for state representation, stress/proxy discrimination, and confounder modeling, not supervised pain scoring.

## Refined Phase 2 Approach

Phase 1 should be rerun with a stricter separation between pain supervision and auxiliary state supervision. Direct-pain datasets should train pain heads only: PainMonit, RheumaPain, and PhysioPain watch. Stress/emotion/exercise datasets should train auxiliary state heads only: CATSA, EPM-E4, WESAD, induced stress/exercise, merged wearable stress, and the xalentis Stress reference rows. The model should not be allowed to learn "stress = pain"; it should learn that stress is a nearby but distinct physiological state.

The feeder should add a formal `label_family` column with values like `direct_pain`, `stress_proxy`, `emotion_proxy`, `exercise_context`, `baseline_context`, and `unlabeled`. It should also add a `source_family` or `collection_protocol` field so validation can explicitly block leakage by dataset/protocol. Training should use per-dataset, per-subject, and per-label-family weights. The reference stress results make this more important, not less: synthesized proxy data can improve transfer, but it can also dominate if it is treated as truth for the wrong target.

The next supervised pain analysis should use ordinal targets instead of raw pooled regression. PainMonit can support higher-resolution NRS bins, RheumaPain should be treated as weak/session-level ordinal supervision, and PhysioPain watch should be validated as a 1-5 source scale before mapping to 0-10. The primary metrics should be leave-subject within dataset, leave-dataset-out, and leave-label-regime-out. A deployment sensor subset should be evaluated separately: Apple-Watch-like, E4-like, autonomic-core, and motion-only.

Baseline handling should move from "best effort" to a required training object. Each dataset should expose baseline intervals where they exist, and if not, a `baseline_missing` flag should be explicit. For datasets with multiple states, Phase 2 should learn state anchors such as relaxed/baseline, stress/agitation, exercise/motion, passive pain, and recovery. Current z-score and baseline-distance features are a reasonable start, but the next pass should compare current windows to multiple anchors, not just one rest baseline.

## Practical Next Steps

1. Add the stress reference feeder rows to the all-dataset auxiliary state table, not to the direct pain table.
2. Extend `pain_all_dataset_feeder.py` with explicit `label_family` and `source_family` columns.
3. Parse WESAD protocol intervals instead of treating WESAD as one unsegmented full protocol.
4. Split PainMonit, RheumaPain, and PhysioPain watch into dataset-specific ordinal targets before pooling.
5. Rerun self-supervised/state analysis with the stress reference rows included.
6. Rerun supervised pain with multi-task outputs: pain ordinal head, stress/proxy head, activity/motion head, and baseline-state head.
7. Accept a pain model only if sensor-only or sensor-plus-state models beat metadata probes under leave-subject and leave-dataset validation.

## Sources

- Reference repo: https://github.com/xalentis/Stress
- arXiv paper page: https://arxiv.org/abs/2209.15146
- Journal DOI: https://doi.org/10.1016/j.jbi.2023.104556
