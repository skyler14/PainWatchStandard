# R Phase 3 State Coupling Report

Rows: 611439 

## Sensor Coverage By Dataset

                   dataset_id bvp__present hr__present eda__present
1                       catsa          1.0           1          1.0
2                      epm_e4          1.0           1          1.0
3     induced_stress_exercise          1.0           1          1.0
4      merged_wearable_stress          0.0           1          1.0
5                   painmonit          1.0           0          1.0
6              physiopain_eeg          0.0           0          0.0
7            physiopain_watch          1.0           0          1.0
8                  rheumapain          1.0           0          1.0
9              sample_27_9vuw          0.5           1          0.5
10      stress_reference_real          0.0           1          1.0
11 stress_reference_synthetic          0.0           1          1.0
12     wearable_sports_health          0.0           1          0.0
13                      wesad          1.0           1          1.0
   temperature__present acc__present respiration__present emg__present
1                   1.0          1.0                  0.0            0
2                   1.0          1.0                  0.0            0
3                   1.0          1.0                  0.0            0
4                   1.0          1.0                  0.0            0
5                   1.0          0.0                  1.0            1
6                   0.0          0.0                  0.0            0
7                   1.0          1.0                  0.0            0
8                   1.0          1.0                  0.0            0
9                   0.5          0.5                  0.5            0
10                  0.0          0.0                  0.0            0
11                  0.0          0.0                  0.0            0
12                  1.0          0.0                  0.0            0
13                  1.0          1.0                  0.0            0
   grip__present
1              0
2              0
3              0
4              0
5              1
6              0
7              0
8              0
9              0
10             0
11             0
12             0
13             0

## Leave-Dataset Transfer GLM

                     target                    heldout train_rows test_rows
pain.1     pain_high_4_plus                 rheumapain      17756     23764
pain.2     pain_high_4_plus                  painmonit      32364      9156
pain.3     pain_high_4_plus           physiopain_watch      32920      8600
stress.1         stress_bin                      catsa     515191     20000
stress.2         stress_bin    induced_stress_exercise     531590      3601
stress.3         stress_bin     merged_wearable_stress     531891      3300
stress.4         stress_bin      stress_reference_real     283701    251490
stress.5         stress_bin stress_reference_synthetic     278391    256800
activity.1     activity_bin                 rheumapain       6417     10132
activity.2     activity_bin     wearable_sports_health      16432       117
activity.3     activity_bin    induced_stress_exercise      10249      6300
baseline.1     baseline_bin                 rheumapain      41567     23454
baseline.2     baseline_bin     wearable_sports_health      64521       500
baseline.3     baseline_bin                      catsa      45021     20000
baseline.4     baseline_bin                     epm_e4      47154     17867
baseline.5     baseline_bin           physiopain_watch      63321      1700
baseline.6     baseline_bin             physiopain_eeg      63521      1500
           prevalence       auc        brier
pain.1     0.04405824 0.5123955 3.011271e-01
pain.2     0.59643949 0.5399640 4.978279e-01
pain.3     0.22093023 0.6408609 2.080639e-01
stress.1   0.75000000 0.4969880 2.499997e-01
stress.2   1.00000000        NA 5.314558e-04
stress.3   0.60606061 0.4294127 3.218146e-01
stress.4   0.41967474 0.5664767 2.748175e-01
stress.5   0.48571262 0.6009692 2.437859e-01
activity.1 1.00000000        NA 8.413943e-24
activity.2 0.00000000        NA          NaN
activity.3 1.00000000        NA 8.413943e-24
baseline.1 0.62675876 0.4998762 3.732412e-01
baseline.2 0.23800000 0.5329848 7.620000e-01
baseline.3 0.74900000 0.9618557 8.690455e-02
baseline.4 0.68752449 0.9832902 6.979968e-02
baseline.5 1.00000000        NA 5.055034e-01
baseline.6 1.00000000        NA 7.148595e-01

## Direct Pain Rows: Transferred State Means

        dataset_id label_family stress_transfer activity_transfer
1        painmonit  direct_pain          0.9875                 1
2 physiopain_watch  direct_pain          0.8156                 1
3       rheumapain  direct_pain          0.6869                 1
  baseline_departure_transfer pain_pref_norm max_state_pref
1                      0.2813         0.2284         0.2933
2                      0.2908         0.1802         0.3224
3                      0.3515         0.1860         0.3260

## Pain Bins vs Transferred States

  pain_bins stress_transfer activity_transfer baseline_departure_transfer
1      zero          0.6526                 1                      0.3248
2      mild          0.7727                 1                      0.3320
3  moderate          0.9877                 1                      0.2811
4    severe          0.9881                 1                      0.2812
  pain_pref_norm
1         0.1873
2         0.1898
3         0.2211
4         0.2340

## Notes

- Robust dataset-normalized features used: median/MAD within dataset, clipped to +/-8.
- Present flags included, so dropout/missing sensor categories become learnable evidence, not fake zeros alone.
- State preference normalization = softmax over pain/stress/activity/baseline-departure logits; this forces competition between states.
- This is exploratory GLM, not final model. Use to choose next validation gates.
