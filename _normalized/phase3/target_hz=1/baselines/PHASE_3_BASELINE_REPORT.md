# Phase 3 Baseline Report

Input: `/Users/skyler/Downloads/pain datasets/_normalized/phase3/target_hz=1/window_features.parquet`

Rows: 611439

## Label Family Coverage

| label_family           | dataset_id                 |   rows |
|:-----------------------|:---------------------------|-------:|
| baseline_context       | catsa                      |   5000 |
| cognitive_load_proxy   | catsa                      |  15000 |
| direct_pain            | rheumapain                 |  23764 |
| direct_pain            | painmonit                  |   9156 |
| direct_pain            | physiopain_watch           |   8600 |
| emotion_proxy          | epm_e4                     |  17867 |
| exercise_context       | induced_stress_exercise    |   9901 |
| exercise_context       | wearable_sports_health     |    500 |
| pain_context_unlabeled | physiopain_eeg             |   8300 |
| stress_proxy           | stress_reference_synthetic | 256800 |
| stress_proxy           | stress_reference_real      | 251490 |
| stress_proxy           | merged_wearable_stress     |   3300 |
| stress_proxy           | wesad                      |   1500 |
| unlabeled              | sample_27_9vuw             |    200 |
| unlabeled              | painmonit                  |     61 |

## Direct Pain Group-Holdout

| feature_set        |   test_rows |   features |   prevalence |   roc_auc |   average_precision |   balanced_accuracy |       f1 |
|:-------------------|------------:|-----------:|-------------:|----------:|--------------------:|--------------------:|---------:|
| sensors_plus_state |       10773 |        215 |     0.299452 |  0.787566 |            0.614303 |            0.685612 | 0.55122  |
| apple_watch_like   |       10773 |        112 |     0.299452 |  0.779804 |            0.554026 |            0.694819 | 0.569978 |
| metadata_probe     |       10773 |         25 |     0.299452 |  0.819213 |            0.683408 |            0.778183 | 0.682084 |

## Direct Pain Regression

| feature_set        |   test_rows |   features |     mae |   baseline_mae |   mae_improvement_vs_train_mean |         r2 |
|:-------------------|------------:|-----------:|--------:|---------------:|--------------------------------:|-----------:|
| sensors_plus_state |       10773 |        215 | 1.49032 |        1.56194 |                       0.0458547 | 0.0335571  |
| apple_watch_like   |       10773 |        112 | 1.50229 |        1.56194 |                       0.0381875 | 0.00901337 |
| metadata_probe     |       10773 |         25 | 1.33989 |        1.56194 |                       0.142164  | 0.228238   |

## Leave Direct Pain Dataset Out

| heldout          | feature_set        |   test_rows |   prevalence |   roc_auc |   average_precision |   balanced_accuracy |
|:-----------------|:-------------------|------------:|-------------:|----------:|--------------------:|--------------------:|
| painmonit        | sensors_plus_state |        9156 |    0.596439  |  0.508153 |            0.612228 |            0.470934 |
| painmonit        | apple_watch_like   |        9156 |    0.596439  |  0.476638 |            0.602783 |            0.456319 |
| painmonit        | metadata_probe     |        9156 |    0.596439  |  0.494778 |            0.603854 |            0.436538 |
| physiopain_watch | sensors_plus_state |        8600 |    0.22093   |  0.61426  |            0.2582   |            0.626866 |
| physiopain_watch | apple_watch_like   |        8600 |    0.22093   |  0.673677 |            0.308135 |            0.618833 |
| physiopain_watch | metadata_probe     |        8600 |    0.22093   |  0.613505 |            0.268766 |            0.626866 |
| rheumapain       | sensors_plus_state |       23764 |    0.0440582 |  0.648042 |            0.327097 |            0.50382  |
| rheumapain       | apple_watch_like   |       23764 |    0.0440582 |  0.646527 |            0.33307  |            0.524355 |
| rheumapain       | metadata_probe     |       23764 |    0.0440582 |  0.704877 |            0.339704 |            0.648042 |

## Within-Dataset LOSO Pain High-Pain Classification

_No successful rows._

## Within-Dataset LOSO Pain Regression

| heldout                                 | feature_set        |   test_rows |       mae |   baseline_mae |   mae_improvement_vs_train_mean |         r2 |
|:----------------------------------------|:-------------------|------------:|----------:|---------------:|--------------------------------:|-----------:|
| painmonit:painmonit::p36                | sensors_plus_state |         144 | 2.27893   |        3.33954 |                       0.31759   |  -65.3446  |
| painmonit:painmonit::p36                | apple_watch_like   |         144 | 2.43258   |        3.33954 |                       0.271581  |  -71.4711  |
| painmonit:painmonit::p36                | metadata_probe     |         144 | 3.30072   |        3.33954 |                       0.0116224 | -129.158   |
| painmonit:painmonit::p09                | sensors_plus_state |         214 | 2.34365   |        3.7088  |                       0.368084  |   -6.02428 |
| painmonit:painmonit::p09                | apple_watch_like   |         214 | 3.62      |        3.7088  |                       0.0239413 |  -13.696   |
| painmonit:painmonit::p09                | metadata_probe     |         214 | 3.355     |        3.7088  |                       0.0953941 |  -11.7369  |
| physiopain_watch:physiopain_watch::S012 | sensors_plus_state |         100 | 0.0924795 |        1.69412 |                       0.945411  |  nan       |
| physiopain_watch:physiopain_watch::S012 | apple_watch_like   |         100 | 0.0924795 |        1.69412 |                       0.945411  |  nan       |
| physiopain_watch:physiopain_watch::S012 | metadata_probe     |         100 | 0.0924795 |        1.69412 |                       0.945411  |  nan       |
| physiopain_watch:physiopain_watch::S081 | sensors_plus_state |         100 | 0.555109  |        2.35294 |                       0.764079  |  nan       |
| physiopain_watch:physiopain_watch::S081 | apple_watch_like   |         100 | 1.10351   |        2.35294 |                       0.531009  |  nan       |
| physiopain_watch:physiopain_watch::S081 | metadata_probe     |         100 | 0.863617  |        2.35294 |                       0.632963  |  nan       |
| rheumapain:rheumapain::s021             | sensors_plus_state |         948 | 0.291637  |        1.41298 |                       0.793602  |  nan       |
| rheumapain:rheumapain::s021             | apple_watch_like   |         948 | 0.432079  |        1.41298 |                       0.694209  |  nan       |
| rheumapain:rheumapain::s021             | metadata_probe     |         948 | 0.123297  |        1.41298 |                       0.91274   |  nan       |
| rheumapain:rheumapain::s019             | sensors_plus_state |         310 | 1.08063   |        2.67832 |                       0.596526  |  nan       |
| rheumapain:rheumapain::s019             | apple_watch_like   |         310 | 1.08043   |        2.67832 |                       0.596602  |  nan       |
| rheumapain:rheumapain::s019             | metadata_probe     |         310 | 1.97134   |        2.67832 |                       0.263964  |  nan       |

## Stress Auxiliary Source Transfer

| heldout   | feature_set    |   test_rows |   prevalence |   roc_auc |   average_precision |   balanced_accuracy |
|:----------|:---------------|------------:|-------------:|----------:|--------------------:|--------------------:|
| NEURO     | hr_eda_stress  |       23746 |     0.547924 |  0.618957 |            0.699608 |            0.587894 |
| NEURO     | autonomic_core |       23746 |     0.547924 |  0.62274  |            0.699767 |            0.600493 |
| NEURO     | metadata_probe |       23746 |     0.547924 |  1        |            1        |            1        |
| SWELL     | hr_eda_stress  |      157625 |     0.285678 |  0.858122 |            0.704908 |            0.614603 |
| SWELL     | autonomic_core |      157625 |     0.285678 |  0.866329 |            0.72437  |            0.64857  |
| SWELL     | metadata_probe |      157625 |     0.285678 |  1        |            1        |            1        |
| SYNTHETIC | hr_eda_stress  |      256800 |     0.485713 |  0.802193 |            0.764411 |            0.646366 |
| SYNTHETIC | autonomic_core |      256800 |     0.485713 |  0.81332  |            0.781922 |            0.655898 |
| SYNTHETIC | metadata_probe |      256800 |     0.485713 |  1        |            1        |            1        |
| UBFC      | hr_eda_stress  |       38569 |     0.984418 |  0.494254 |            0.988548 |            0.482222 |
| UBFC      | autonomic_core |       38569 |     0.984418 |  0.510095 |            0.988878 |            0.481563 |
| UBFC      | metadata_probe |       38569 |     0.984418 |  1        |            1        |            1        |
| WESAD     | hr_eda_stress  |       31550 |     0.302219 |  0.466437 |            0.273354 |            0.477415 |
| WESAD     | autonomic_core |       31550 |     0.302219 |  0.50036  |            0.295199 |            0.492787 |
| WESAD     | metadata_probe |       31550 |     0.302219 |  1        |            1        |            1        |

## Baseline-State Probe

| feature_set        |   test_rows |   prevalence |   roc_auc |   average_precision |   balanced_accuracy |
|:-------------------|------------:|-------------:|----------:|--------------------:|--------------------:|
| sensors_plus_state |       15128 |      0.64179 |  0.974985 |            0.974828 |            0.94162  |
| apple_watch_like   |       15128 |      0.64179 |  0.980768 |            0.979825 |            0.940515 |
| metadata_probe     |       15128 |      0.64179 |  1        |            1        |            1        |

## Interpretation Rules

- `metadata_probe` is a leakage/protocol diagnostic, not a deployment model.
- Stress/proxy rows train only the stress/state task, never the direct pain task.
- LOSO rows are selected across each dataset's subject pain distribution to give a fast early check before a full exhaustive LOSO run.
- Leave-dataset-out direct-pain results are the primary cross-protocol integrity check.
