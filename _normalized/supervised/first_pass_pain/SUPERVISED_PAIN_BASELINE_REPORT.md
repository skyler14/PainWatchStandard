# Supervised Pain Baseline Report

Date: 2026-04-29

Input: `_normalized/window_features_all/target_hz=1/window_features.parquet`

Rows with direct pain targets: 41520

## Label Coverage

| dataset_id       |   rows |   subjects |   sessions |   mean_pain |   min_pain |   max_pain |   high_pain_rate |   nonzero_pain_rate |   mean_weight |   weight_sum |
|:-----------------|-------:|-----------:|-----------:|------------:|-----------:|-----------:|-----------------:|--------------------:|--------------:|-------------:|
| painmonit        |   9156 |         49 |         90 |     4.52197 |          1 |         10 |        0.596439  |            1        |      1.79003  |     16389.5  |
| physiopain_watch |   8600 |         86 |         86 |     2.67442 |          1 |          5 |        0.22093   |            1        |      2.0328   |     17482.1  |
| rheumapain       |  23764 |         42 |         83 |     1.35662 |          0 |          4 |        0.0440582 |            0.666597 |      0.321849 |      7648.42 |

## Important Interpretation Limits

- This is a first-pass predictive-power check, not a deployable pain model.
- Label scales differ by dataset. PainMonit is broad NRS-like, RheumaPain is weak/session-level and low-range in these windows, and PhysioPain watch is 1-5.
- Pooled results can show signal, but leave-dataset-out and within-dataset subject holdout are the integrity checks.
- `metadata_probe` and `sensors_plus_metadata` are leakage diagnostics, not the preferred model for deployment.

## Pooled Subject-Holdout Regression

| feature_set           |   test_rows |   features |     mae |   baseline_mae |   mae_improvement_vs_train_mean |   weighted_mae |   weighted_baseline_mae |   weighted_mae_improvement_vs_train_mean |          r2 |   pearson |
|:----------------------|------------:|-----------:|--------:|---------------:|--------------------------------:|---------------:|------------------------:|-----------------------------------------:|------------:|----------:|
| sensors_only          |       10773 |        206 | 1.63471 |        1.56194 |                     -0.0465919  |        1.63807 |                 2.03628 |                                 0.195557 | -0.106579   |  0.572172 |
| sensors_plus_state    |       10773 |        214 | 1.49606 |        1.56194 |                      0.0421793  |        1.52211 |                 2.03628 |                                 0.252506 |  0.00541907 |  0.573178 |
| e4_like               |       10773 |        116 | 1.54217 |        1.56194 |                      0.0126583  |        1.63994 |                 2.03628 |                                 0.19464  | -0.0869778  |  0.486761 |
| apple_watch_like      |       10773 |        111 | 1.50696 |        1.56194 |                      0.0352031  |        1.53482 |                 2.03628 |                                 0.246263 | -0.0100486  |  0.537904 |
| autonomic_core        |       10773 |         69 | 1.56869 |        1.56194 |                     -0.00432171 |        1.67203 |                 2.03628 |                                 0.178883 | -0.117848   |  0.454904 |
| motion_only           |       10773 |         74 | 1.52624 |        1.56194 |                      0.0228542  |        1.48545 |                 2.03628 |                                 0.270507 |  0.0248467  |  0.591072 |
| metadata_probe        |       10773 |         20 | 1.35795 |        1.56194 |                      0.130602   |        1.41018 |                 2.03628 |                                 0.307474 |  0.207692   |  0.557048 |
| sensors_plus_metadata |       10773 |        226 | 1.43446 |        1.56194 |                      0.081615   |        1.46346 |                 2.03628 |                                 0.281308 |  0.0924243  |  0.584906 |

## Pooled Subject-Holdout High-Pain Classification

| feature_set           |   test_rows |   features |   prevalence |   roc_auc |   average_precision |   balanced_accuracy |   weighted_roc_auc |   weighted_average_precision |   weighted_balanced_accuracy |
|:----------------------|------------:|-----------:|-------------:|----------:|--------------------:|--------------------:|-------------------:|-----------------------------:|-----------------------------:|
| sensors_only          |       10773 |        206 |     0.299452 |  0.778975 |            0.644671 |            0.616418 |           0.750518 |                     0.709796 |                     0.619347 |
| sensors_plus_state    |       10773 |        214 |     0.299452 |  0.783954 |            0.625977 |            0.600941 |           0.732617 |                     0.678245 |                     0.588722 |
| e4_like               |       10773 |        116 |     0.299452 |  0.765788 |            0.541561 |            0.598723 |           0.699839 |                     0.583103 |                     0.568338 |
| apple_watch_like      |       10773 |        111 |     0.299452 |  0.787082 |            0.609233 |            0.626157 |           0.727751 |                     0.659177 |                     0.614068 |
| autonomic_core        |       10773 |         69 |     0.299452 |  0.740129 |            0.575975 |            0.592562 |           0.697684 |                     0.635079 |                     0.575726 |
| motion_only           |       10773 |         74 |     0.299452 |  0.805738 |            0.654546 |            0.750082 |           0.793072 |                     0.739931 |                     0.761405 |
| metadata_probe        |       10773 |         20 |     0.299452 |  0.819283 |            0.683522 |            0.731383 |           0.83868  |                     0.778371 |                     0.742689 |
| sensors_plus_metadata |       10773 |        226 |     0.299452 |  0.750368 |            0.616332 |            0.599687 |           0.738726 |                     0.680287 |                     0.583181 |

## Within-Dataset Subject-Holdout Regression

| split                                           | feature_set           |   test_rows |      mae |   baseline_mae |   mae_improvement_vs_train_mean |   weighted_mae_improvement_vs_train_mean |         r2 |    pearson |
|:------------------------------------------------|:----------------------|------------:|---------:|---------------:|--------------------------------:|-----------------------------------------:|-----------:|-----------:|
| within_dataset_subject_holdout:painmonit        | sensors_only          |        2687 | 1.86455  |        1.54517 |                     -0.20669    |                              -0.20669    | -0.521374  | -0.0368692 |
| within_dataset_subject_holdout:painmonit        | sensors_plus_state    |        2687 | 1.89073  |        1.54517 |                     -0.223633   |                              -0.223633   | -0.543747  | -0.0444581 |
| within_dataset_subject_holdout:painmonit        | e4_like               |        2687 | 1.91995  |        1.54517 |                     -0.242543   |                              -0.242543   | -0.800459  | -0.199286  |
| within_dataset_subject_holdout:painmonit        | apple_watch_like      |        2687 | 1.879    |        1.54517 |                     -0.216047   |                              -0.216047   | -0.732186  | -0.180824  |
| within_dataset_subject_holdout:painmonit        | autonomic_core        |        2687 | 2.23096  |        1.54517 |                     -0.443823   |                              -0.443823   | -1.27385   | -0.351794  |
| within_dataset_subject_holdout:painmonit        | motion_only           |        2687 | 1.55379  |        1.54517 |                     -0.00557494 |                              -0.00557494 | -0.0925924 | -0.0219674 |
| within_dataset_subject_holdout:painmonit        | metadata_probe        |        2687 | 1.55379  |        1.54517 |                     -0.00557494 |                              -0.00557494 | -0.0925924 | -0.0219674 |
| within_dataset_subject_holdout:painmonit        | sensors_plus_metadata |        2687 | 1.89073  |        1.54517 |                     -0.223633   |                              -0.223633   | -0.543747  | -0.0444581 |
| within_dataset_subject_holdout:physiopain_watch | sensors_only          |        2200 | 1.17091  |        1.02841 |                     -0.138564   |                              -0.138564   | -0.369486  |  0.02561   |
| within_dataset_subject_holdout:physiopain_watch | sensors_plus_state    |        2200 | 0.816065 |        1.02841 |                      0.206478   |                               0.206478   |  0.171141  |  0.509294  |
| within_dataset_subject_holdout:physiopain_watch | e4_like               |        2200 | 0.816065 |        1.02841 |                      0.206478   |                               0.206478   |  0.171141  |  0.509294  |
| within_dataset_subject_holdout:physiopain_watch | apple_watch_like      |        2200 | 0.756437 |        1.02841 |                      0.264459   |                               0.264459   |  0.23491   |  0.543967  |
| within_dataset_subject_holdout:physiopain_watch | autonomic_core        |        2200 | 0.617998 |        1.02841 |                      0.399074   |                               0.399074   |  0.498949  |  0.709755  |
| within_dataset_subject_holdout:physiopain_watch | motion_only           |        2200 | 0.777644 |        1.02841 |                      0.243838   |                               0.243838   |  0.207419  |  0.550674  |
| within_dataset_subject_holdout:physiopain_watch | metadata_probe        |        2200 | 0.595751 |        1.02841 |                      0.420706   |                               0.420706   |  0.56694   |  0.753363  |
| within_dataset_subject_holdout:physiopain_watch | sensors_plus_metadata |        2200 | 0.71299  |        1.02841 |                      0.306706   |                               0.306706   |  0.401257  |  0.653904  |
| within_dataset_subject_holdout:rheumapain       | sensors_only          |        6690 | 0.965666 |        1.12162 |                      0.139046   |                               0.139046   | -1.85373   | -0.0821414 |
| within_dataset_subject_holdout:rheumapain       | sensors_plus_state    |        6690 | 0.965285 |        1.12162 |                      0.139386   |                               0.139386   | -1.84868   | -0.0798076 |
| within_dataset_subject_holdout:rheumapain       | e4_like               |        6690 | 0.965285 |        1.12162 |                      0.139386   |                               0.139386   | -1.84868   | -0.0798076 |
| within_dataset_subject_holdout:rheumapain       | apple_watch_like      |        6690 | 1.04751  |        1.12162 |                      0.066077   |                               0.066077   | -2.0732    | -0.160164  |
| within_dataset_subject_holdout:rheumapain       | autonomic_core        |        6690 | 0.98855  |        1.12162 |                      0.118644   |                               0.118644   | -2.13471   |  0.326246  |
| within_dataset_subject_holdout:rheumapain       | motion_only           |        6690 | 1.28379  |        1.12162 |                     -0.144578   |                              -0.144578   | -3.60035   | -0.126529  |
| within_dataset_subject_holdout:rheumapain       | metadata_probe        |        6690 | 0.980168 |        1.12162 |                      0.126117   |                               0.126117   | -1.69375   |  0.101434  |
| within_dataset_subject_holdout:rheumapain       | sensors_plus_metadata |        6690 | 1.05128  |        1.12162 |                      0.062715   |                               0.062715   | -2.91655   |  0.101797  |

## Leave-Dataset-Out Regression

| heldout_dataset   | feature_set           |   test_rows |      mae |   baseline_mae |   mae_improvement_vs_train_mean |   weighted_mae_improvement_vs_train_mean |         r2 |      pearson |
|:------------------|:----------------------|------------:|---------:|---------------:|--------------------------------:|-----------------------------------------:|-----------:|-------------:|
| painmonit         | sensors_only          |        9156 | 2.29301  |        2.88967 |                        0.206481 |                                 0.206481 | -0.900445  | -0.0944129   |
| painmonit         | sensors_plus_state    |        9156 | 1.92788  |        2.88967 |                        0.332838 |                                 0.332838 | -0.330771  | -0.00926504  |
| painmonit         | e4_like               |        9156 | 1.92788  |        2.88967 |                        0.332838 |                                 0.332838 | -0.330771  | -0.00926504  |
| painmonit         | apple_watch_like      |        9156 | 2.02946  |        2.88967 |                        0.297683 |                                 0.297683 | -0.471044  | -0.194106    |
| painmonit         | autonomic_core        |        9156 | 1.84839  |        2.88967 |                        0.360345 |                                 0.360345 | -0.1809    |  7.09428e-05 |
| painmonit         | motion_only           |        9156 | 1.91154  |        2.88967 |                        0.338492 |                                 0.338492 | -0.221883  | -0.137917    |
| painmonit         | metadata_probe        |        9156 | 2.06514  |        2.88967 |                        0.285337 |                                 0.285337 | -0.571905  |  0.124429    |
| painmonit         | sensors_plus_metadata |        9156 | 2.10668  |        2.88967 |                        0.270963 |                                 0.270963 | -0.605355  | -0.129507    |
| physiopain_watch  | sensors_only          |        8600 | 1.97035  |        1.08321 |                       -0.818994 |                                -0.818994 | -2.52586   | -0.0397034   |
| physiopain_watch  | sensors_plus_state    |        8600 | 1.46573  |        1.08321 |                       -0.353137 |                                -0.353137 | -0.939727  |  0.502666    |
| physiopain_watch  | e4_like               |        8600 | 1.54239  |        1.08321 |                       -0.423911 |                                -0.423911 | -1.24879   |  0.490391    |
| physiopain_watch  | apple_watch_like      |        8600 | 1.47572  |        1.08321 |                       -0.362362 |                                -0.362362 | -1.17      |  0.500485    |
| physiopain_watch  | autonomic_core        |        8600 | 1.32239  |        1.08321 |                       -0.220804 |                                -0.220804 | -0.866866  |  0.526375    |
| physiopain_watch  | motion_only           |        8600 | 1.22165  |        1.08321 |                       -0.127803 |                                -0.127803 | -0.245456  |  0.674092    |
| physiopain_watch  | metadata_probe        |        8600 | 1.26854  |        1.08321 |                       -0.171093 |                                -0.171093 | -0.5433    |  0.669598    |
| physiopain_watch  | sensors_plus_metadata |        8600 | 1.36495  |        1.08321 |                       -0.260096 |                                -0.260096 | -0.80805   |  0.543353    |
| rheumapain        | sensors_only          |       23764 | 1.25588  |        2.30336 |                        0.45476  |                                 0.45476  | -0.502648  |  0.0194567   |
| rheumapain        | sensors_plus_state    |       23764 | 0.995002 |        2.30336 |                        0.568022 |                                 0.568022 |  0.0209944 |  0.396774    |
| rheumapain        | e4_like               |       23764 | 0.993914 |        2.30336 |                        0.568494 |                                 0.568494 |  0.0438703 |  0.393065    |
| rheumapain        | apple_watch_like      |       23764 | 1.00881  |        2.30336 |                        0.562025 |                                 0.562025 |  0.0281802 |  0.371604    |
| rheumapain        | autonomic_core        |       23764 | 0.996001 |        2.30336 |                        0.567588 |                                 0.567588 |  0.0323979 |  0.402056    |
| rheumapain        | motion_only           |       23764 | 0.970017 |        2.30336 |                        0.578869 |                                 0.578869 |  0.0768812 |  0.411665    |
| rheumapain        | metadata_probe        |       23764 | 0.964363 |        2.30336 |                        0.581323 |                                 0.581323 |  0.122616  |  0.428294    |
| rheumapain        | sensors_plus_metadata |       23764 | 0.988452 |        2.30336 |                        0.570865 |                                 0.570865 |  0.0542601 |  0.407477    |

## Leave-Dataset-Out High-Pain Classification

| heldout_dataset   | feature_set           |   test_rows |   prevalence |   roc_auc |   average_precision |   balanced_accuracy |   weighted_roc_auc |   weighted_average_precision |   weighted_balanced_accuracy |
|:------------------|:----------------------|------------:|-------------:|----------:|--------------------:|--------------------:|-------------------:|-----------------------------:|-----------------------------:|
| painmonit         | sensors_only          |        9156 |    0.596439  |  0.540017 |           0.634791  |            0.554081 |           0.540017 |                    0.634791  |                     0.554081 |
| painmonit         | sensors_plus_state    |        9156 |    0.596439  |  0.546262 |           0.620322  |            0.548138 |           0.546262 |                    0.620322  |                     0.548138 |
| painmonit         | e4_like               |        9156 |    0.596439  |  0.546262 |           0.620322  |            0.548138 |           0.546262 |                    0.620322  |                     0.548138 |
| painmonit         | apple_watch_like      |        9156 |    0.596439  |  0.502206 |           0.6375    |            0.463219 |           0.502206 |                    0.6375    |                     0.463219 |
| painmonit         | autonomic_core        |        9156 |    0.596439  |  0.538685 |           0.609201  |            0.525569 |           0.538685 |                    0.609201  |                     0.525569 |
| painmonit         | motion_only           |        9156 |    0.596439  |  0.407042 |           0.564031  |            0.5      |           0.407042 |                    0.564031  |                     0.5      |
| painmonit         | metadata_probe        |        9156 |    0.596439  |  0.378298 |           0.542817  |            0.407042 |           0.378298 |                    0.542817  |                     0.407042 |
| painmonit         | sensors_plus_metadata |        9156 |    0.596439  |  0.514376 |           0.610568  |            0.494999 |           0.514376 |                    0.610568  |                     0.494999 |
| physiopain_watch  | sensors_only          |        8600 |    0.22093   |  0.498679 |           0.218794  |            0.5      |           0.498679 |                    0.218794  |                     0.5      |
| physiopain_watch  | sensors_plus_state    |        8600 |    0.22093   |  0.635276 |           0.2834    |            0.62205  |           0.635276 |                    0.2834    |                     0.62205  |
| physiopain_watch  | e4_like               |        8600 |    0.22093   |  0.638071 |           0.2836    |            0.62097  |           0.638071 |                    0.2836    |                     0.62097  |
| physiopain_watch  | apple_watch_like      |        8600 |    0.22093   |  0.657806 |           0.30038   |            0.628071 |           0.657806 |                    0.30038   |                     0.628071 |
| physiopain_watch  | autonomic_core        |        8600 |    0.22093   |  0.647    |           0.301473  |            0.613704 |           0.647    |                    0.301473  |                     0.613704 |
| physiopain_watch  | motion_only           |        8600 |    0.22093   |  0.639107 |           0.282598  |            0.626866 |           0.639107 |                    0.282598  |                     0.626866 |
| physiopain_watch  | metadata_probe        |        8600 |    0.22093   |  0.662223 |           0.297537  |            0.619474 |           0.662223 |                    0.297537  |                     0.619474 |
| physiopain_watch  | sensors_plus_metadata |        8600 |    0.22093   |  0.635276 |           0.2834    |            0.62205  |           0.635276 |                    0.2834    |                     0.62205  |
| rheumapain        | sensors_only          |       23764 |    0.0440582 |  0.642555 |           0.0642134 |            0.495271 |           0.642555 |                    0.0642134 |                     0.495271 |
| rheumapain        | sensors_plus_state    |       23764 |    0.0440582 |  0.736868 |           0.0878818 |            0.49678  |           0.736868 |                    0.0878818 |                     0.49678  |
| rheumapain        | e4_like               |       23764 |    0.0440582 |  0.693396 |           0.0766445 |            0.493602 |           0.693396 |                    0.0766445 |                     0.493602 |
| rheumapain        | apple_watch_like      |       23764 |    0.0440582 |  0.709234 |           0.0812057 |            0.509604 |           0.709234 |                    0.0812057 |                     0.509604 |
| rheumapain        | autonomic_core        |       23764 |    0.0440582 |  0.641617 |           0.0683971 |            0.495519 |           0.641617 |                    0.0683971 |                     0.495519 |
| rheumapain        | motion_only           |       23764 |    0.0440582 |  0.666875 |           0.0998488 |            0.535585 |           0.666875 |                    0.0998488 |                     0.535585 |
| rheumapain        | metadata_probe        |       23764 |    0.0440582 |  0.586885 |           0.0529175 |            0.499934 |           0.586885 |                    0.0529175 |                     0.499934 |
| rheumapain        | sensors_plus_metadata |       23764 |    0.0440582 |  0.732329 |           0.0927571 |            0.498558 |           0.732329 |                    0.0927571 |                     0.498558 |
