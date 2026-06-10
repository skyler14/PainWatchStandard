# R Temporal Shape Exploration

Generated rows ranked: 16628
Shape-vs-shuffle comparisons: 5151
Subject-fixed significant features (FDR < .05): 490

## Shape Order Advantage

Positive value means true temporal order beats shuffled values for same feature calculator.

```
 window_s                       task              dataset_id
        5 cognitive_load_vs_baseline                   catsa
       10 cognitive_load_vs_baseline                   catsa
       30 cognitive_load_vs_baseline                   catsa
        5         stress_vs_exercise induced_stress_exercise
       10         stress_vs_exercise induced_stress_exercise
       30         stress_vs_exercise induced_stress_exercise
        5           pain_high_4_plus               painmonit
       10           pain_high_4_plus               painmonit
       30           pain_high_4_plus               painmonit
        5           pain_high_4_plus          painmonit_pmed
       10           pain_high_4_plus          painmonit_pmed
       30           pain_high_4_plus          painmonit_pmed
        5           pain_high_4_plus        physiopain_watch
       10           pain_high_4_plus        physiopain_watch
       30           pain_high_4_plus        physiopain_watch
        5           pain_high_4_plus              rheumapain
       10           pain_high_4_plus              rheumapain
       30           pain_high_4_plus              rheumapain
        5           pain_high_4_plus             silver_pain
       10           pain_high_4_plus             silver_pain
       30           pain_high_4_plus             silver_pain
        5               wesad_stress                   wesad
       10               wesad_stress                   wesad
       30               wesad_stress                   wesad
 median_order_advantage p90_order_advantage fraction_order_advantage_gt_002
           0.0000000000          0.05246883                      0.42424242
           0.0115705128          0.05037949                      0.48571429
           0.0261437500          0.07016750                      0.54285714
           0.0000000000          0.10268098                      0.32575758
           0.0000000000          0.14039394                      0.40357143
           0.0051262626          0.18718695                      0.41904762
           0.0000000000          0.02767479                      0.14646465
           0.0000000000          0.04419913                      0.24285714
           0.0008911875          0.06608666                      0.31428571
           0.0006347285          0.07062389                      0.34848485
           0.0121196037          0.13685651                      0.47857143
           0.0010642827          0.17737716                      0.45000000
           0.0000000000          0.03551378                      0.16883117
           0.0000000000          0.02367168                      0.13877551
           0.0000000000          0.01985157                      0.09387755
           0.0000000000          0.06263982                      0.26839827
           0.0000000000          0.07481494                      0.26122449
           0.0000000000          0.07595838                      0.30204082
           0.0000000000          0.07021605                      0.33587786
           0.0001597298          0.09282585                      0.35000000
           0.0000000000          0.03735077                      0.27142857
           0.0000000000          0.04590431                      0.20075758
           0.0000000000          0.04878089                      0.27936508
           0.0000000000          0.06000000                      0.29841270
```

## Subject-Fixed Significant Feature Counts

```
 window_s                       task              dataset_id feature_group
        5 cognitive_load_vs_baseline                   catsa          base
       10 cognitive_load_vs_baseline                   catsa          base
       30 cognitive_load_vs_baseline                   catsa          base
        5         stress_vs_exercise induced_stress_exercise          base
       10         stress_vs_exercise induced_stress_exercise          base
       30         stress_vs_exercise induced_stress_exercise          base
       10           pain_high_4_plus               painmonit          base
       30           pain_high_4_plus               painmonit          base
        5           pain_high_4_plus          painmonit_pmed          base
        5               wesad_stress                   wesad          base
       10               wesad_stress                   wesad          base
       30               wesad_stress                   wesad          base
       30           pain_high_4_plus             silver_pain      coupling
       10           pain_high_4_plus          painmonit_pmed       quality
       30           pain_high_4_plus          painmonit_pmed       quality
        5 cognitive_load_vs_baseline                   catsa       reverse
       10 cognitive_load_vs_baseline                   catsa       reverse
       30 cognitive_load_vs_baseline                   catsa       reverse
        5         stress_vs_exercise induced_stress_exercise       reverse
       10         stress_vs_exercise induced_stress_exercise       reverse
       30         stress_vs_exercise induced_stress_exercise       reverse
        5           pain_high_4_plus               painmonit       reverse
       10           pain_high_4_plus               painmonit       reverse
       30           pain_high_4_plus               painmonit       reverse
        5           pain_high_4_plus          painmonit_pmed       reverse
       10           pain_high_4_plus          painmonit_pmed       reverse
       30           pain_high_4_plus          painmonit_pmed       reverse
       30           pain_high_4_plus             silver_pain       reverse
        5               wesad_stress                   wesad       reverse
       10               wesad_stress                   wesad       reverse
       30               wesad_stress                   wesad       reverse
        5 cognitive_load_vs_baseline                   catsa         shape
       10 cognitive_load_vs_baseline                   catsa         shape
       30 cognitive_load_vs_baseline                   catsa         shape
        5         stress_vs_exercise induced_stress_exercise         shape
       10         stress_vs_exercise induced_stress_exercise         shape
       30         stress_vs_exercise induced_stress_exercise         shape
        5           pain_high_4_plus               painmonit         shape
       10           pain_high_4_plus               painmonit         shape
       30           pain_high_4_plus               painmonit         shape
        5           pain_high_4_plus          painmonit_pmed         shape
       10           pain_high_4_plus          painmonit_pmed         shape
       30           pain_high_4_plus          painmonit_pmed         shape
       30           pain_high_4_plus             silver_pain         shape
        5               wesad_stress                   wesad         shape
       10               wesad_stress                   wesad         shape
       30               wesad_stress                   wesad         shape
        5 cognitive_load_vs_baseline                   catsa       shuffle
       10 cognitive_load_vs_baseline                   catsa       shuffle
       30 cognitive_load_vs_baseline                   catsa       shuffle
        5         stress_vs_exercise induced_stress_exercise       shuffle
       10         stress_vs_exercise induced_stress_exercise       shuffle
       30         stress_vs_exercise induced_stress_exercise       shuffle
       10           pain_high_4_plus               painmonit       shuffle
       30           pain_high_4_plus               painmonit       shuffle
        5           pain_high_4_plus          painmonit_pmed       shuffle
       30           pain_high_4_plus          painmonit_pmed       shuffle
       30           pain_high_4_plus             silver_pain       shuffle
        5               wesad_stress                   wesad       shuffle
       10               wesad_stress                   wesad       shuffle
       30               wesad_stress                   wesad       shuffle
 significant_features_fdr_005
                            3
                            3
                            3
                            1
                            5
                            2
                            1
                            3
                            1
                           13
                            6
                            6
                            2
                            8
                            6
                            6
                            6
                            6
                           15
                           14
                           15
                            1
                            5
                           10
                           14
                           15
                           12
                           10
                            9
                           12
                           12
                            6
                            6
                            6
                           16
                           15
                           14
                            1
                            5
                            9
                           14
                           17
                           12
                           11
                            9
                           12
                           13
                            6
                            6
                            6
                            8
                            6
                            9
                            6
                            7
                            5
                           10
                            2
                            9
                           10
                            9
```

## Redundancy

```
 window_s                       task              dataset_id top_shape_features
        5 cognitive_load_vs_baseline                   catsa                 30
        5         stress_vs_exercise induced_stress_exercise                 30
        5           pain_high_4_plus               painmonit                 30
        5           pain_high_4_plus          painmonit_pmed                 30
        5           pain_high_4_plus        physiopain_watch                 30
        5           pain_high_4_plus              rheumapain                 30
        5           pain_high_4_plus             silver_pain                 30
        5               wesad_stress                   wesad                 30
       10 cognitive_load_vs_baseline                   catsa                 30
       10         stress_vs_exercise induced_stress_exercise                 30
       10           pain_high_4_plus               painmonit                 30
       10           pain_high_4_plus          painmonit_pmed                 30
       10           pain_high_4_plus        physiopain_watch                 30
       10           pain_high_4_plus              rheumapain                 30
       10           pain_high_4_plus             silver_pain                 30
       10               wesad_stress                   wesad                 30
       30 cognitive_load_vs_baseline                   catsa                 30
       30         stress_vs_exercise induced_stress_exercise                 30
       30           pain_high_4_plus               painmonit                 30
       30           pain_high_4_plus          painmonit_pmed                 30
       30           pain_high_4_plus        physiopain_watch                 30
       30           pain_high_4_plus              rheumapain                 30
       30           pain_high_4_plus             silver_pain                 30
       30               wesad_stress                   wesad                 30
 pairs_abs_correlation_ge_095
                            8
                           16
                            3
                            1
                           12
                           14
                           13
                           22
                           10
                            6
                            4
                            5
                           15
                           14
                           15
                           25
                           17
                           14
                           25
                            8
                           27
                           14
                           12
                           27
```
