# Exploratory Self-Supervised Report

Date: 2026-04-29

Input: `_normalized/window_features_all/target_hz=1/window_features.parquet`

Output: `_normalized/self_supervised/all_datasets_1hz_30s`

## What Ran

- Sensor-block reconstruction: predict one sensor block's mean feature from other sensor blocks plus allowed metadata.
- Next-window prediction: predict selected sensor means one horizon ahead from the current window.
- Contrastive-style probe: create two augmented views with sensor-block dropout/noise, project with PCA, and compare positive pairs to random negatives.
- Sensor interconnection audit: cross-block absolute correlation scan.

## Data Audit

Rows: 103149

Columns: 385

Label regimes:

| dataset_id              | target_granularity    |   rows |
|:------------------------|:----------------------|-------:|
| catsa                   | none                  |  20000 |
| epm_e4                  | none                  |  17867 |
| induced_stress_exercise | none                  |   9901 |
| merged_wearable_stress  | none                  |   3300 |
| painmonit               | none                  |     61 |
| painmonit               | sparse_sample         |   9156 |
| physiopain_eeg          | none                  |   8300 |
| physiopain_watch        | archive_window_direct |   8600 |
| rheumapain              | session_weak          |  23764 |
| sample_27_9vuw          | none                  |    200 |
| wearable_sports_health  | none                  |    500 |
| wesad                   | none                  |   1500 |

Metadata policy: subject/session IDs are excluded from model features; basic dataset/protocol metadata is included unless `--metadata none` is used.

Balancing policy: `dataset_session`. The output includes `ssl_weight`, and weighted metrics are reported so denser datasets/sessions do not silently dominate interpretation.

## Reconstruction Metrics

| task                       | target_column        | status   |   rows |        test_mae |   weighted_test_mae |     baseline_mae |   weighted_baseline_mae |   mae_improvement_vs_mean |   weighted_mae_improvement_vs_mean |      test_r2 |
|:---------------------------|:---------------------|:---------|-------:|----------------:|--------------------:|-----------------:|------------------------:|--------------------------:|-----------------------------------:|-------------:|
| reconstruct_bvp            | bvp__mean            | ok       |  80000 |     0.850593    |         0.638331    |      0.721738    |              0.587043   |               -0.178534   |                        -0.087366   |  -0.076517   |
| reconstruct_bvp_rb         | bvp_rb__mean         | ok       |   9217 |     0.00437291  |         0.00399743  |      0.00428826  |              0.00384822 |               -0.0197407  |                        -0.0387739  |   0.0292254  |
| reconstruct_hr             | hr__mean             | ok       |  53268 |    10.8568      |        13.6355      |     12.39        |             17.6433     |                0.123748   |                         0.227161   |   0.286552   |
| reconstruct_ibi            | ibi__mean            | ok       |   9111 |     0.076184    |         0.0675362   |      0.161126    |              0.144805   |                0.527176   |                         0.533606   |   0.649572   |
| reconstruct_ecg            | ecg__mean            | skipped  |    100 |   nan           |       nan           |    nan           |            nan          |              nan          |                       nan          | nan          |
| reconstruct_eda            | eda__mean            | ok       |  80000 |     5.07871     |         4.41132     |      5.1694      |              4.9926     |                0.0175449  |                         0.116429   |  -0.305967   |
| reconstruct_eda_rb         | eda_rb__mean         | ok       |   9217 |     3.15084     |         2.80864     |      3.60996     |              3.10798    |                0.127182   |                         0.0963121  |   0.191285   |
| reconstruct_temperature    | temperature__mean    | ok       |  80000 |     7.20508     |         4.71322     |      8.39801     |              5.99785    |                0.142049   |                         0.214182   |  -0.0592747  |
| reconstruct_acc            | acc__mag__mean       | ok       |  80000 |     1.26786     |         3.17937     |      1.70521     |              1.68101    |                0.25648    |                        -0.891348   | -32.1692     |
| reconstruct_respiration    | respiration__mean    | ok       |   9317 |  1446.42        |      1438.31        |  89906.3         |          89906.3        |                0.983912   |                         0.984002   |  -8.7549e+07 |
| reconstruct_emg            | emg__mean            | ok       |   9217 |     0.000473423 |         0.000479597 |      0.000529897 |              0.00053808 |                0.106575   |                         0.108689   |   0.062458   |
| reconstruct_grip           | grip__mean           | ok       |   9217 |     0.357751    |         0.349237    |      0.491001    |              0.514088   |                0.271384   |                         0.320666   |  -0.25476    |
| reconstruct_bp_systolic    | bp_systolic__mean    | ok       |    500 |     7.93921     |         7.93418     |      7.90823     |              7.90254    |               -0.00391803 |                        -0.00400387 |  -0.0474473  |
| reconstruct_bp_diastolic   | bp_diastolic__mean   | ok       |    500 |     5.29647     |         5.28441     |      5.25325     |              5.24361    |               -0.00822854 |                        -0.00778118 |  -0.0187329  |
| reconstruct_spo2           | spo2__mean           | ok       |    500 |     1.53051     |         1.5318      |      1.54812     |              1.54962    |                0.0113771  |                         0.0114975  |   0.00927637 |
| reconstruct_steps          | steps__mean          | ok       |    500 |   184.337       |       184.203       |    181.041       |            180.882      |               -0.0182038  |                        -0.018356   |  -0.0323846  |
| reconstruct_eeg_delta      | eeg_delta__mean      | ok       |   8300 | 86547.1         |     86547.1         | 225484           |         225484          |                0.616171   |                         0.616171   |   0.79609    |
| reconstruct_eeg_theta      | eeg_theta__mean      | ok       |   8300 | 15615.8         |     15615.8         |  49168           |          49168          |                0.682399   |                         0.682399   |   0.866393   |
| reconstruct_eeg_alpha1     | eeg_alpha1__mean     | ok       |   8300 |  4992.52        |      4992.52        |  11182.7         |          11182.7        |                0.553551   |                         0.553551   |   0.741842   |
| reconstruct_eeg_alpha2     | eeg_alpha2__mean     | ok       |   8300 |  2994.09        |      2994.09        |   8041.94        |           8041.94       |                0.62769    |                         0.62769    |   0.833214   |
| reconstruct_eeg_beta1      | eeg_beta1__mean      | ok       |   8300 |  2553.62        |      2553.62        |   6964.94        |           6964.94       |                0.633361   |                         0.633361   |   0.826743   |
| reconstruct_eeg_beta2      | eeg_beta2__mean      | ok       |   8300 |  1858.94        |      1858.94        |   6449.81        |           6449.81       |                0.711784   |                         0.711784   |   0.89262    |
| reconstruct_eeg_gamma1     | eeg_gamma1__mean     | ok       |   8300 |  1379.98        |      1379.98        |   5245.23        |           5245.23       |                0.736908   |                         0.736908   |   0.898661   |
| reconstruct_eeg_gamma2     | eeg_gamma2__mean     | ok       |   8300 |   911.744       |       911.744       |   2537.25        |           2537.25       |                0.640656   |                         0.640656   |   0.743507   |
| reconstruct_eeg_attention  | eeg_attention__mean  | ok       |   8300 |     6.8442      |         6.8442      |      9.37263     |              9.37263    |                0.269768   |                         0.269768   |   0.428626   |
| reconstruct_eeg_meditation | eeg_meditation__mean | ok       |   8300 |     7.92382     |         7.92382     |      7.96884     |              7.96884    |                0.00564966 |                         0.00564966 |  -0.0106231  |

## Next-Window Metrics

| task                           | target_column              | status   |   rows |        test_mae |   weighted_test_mae |     baseline_mae |   weighted_baseline_mae |   mae_improvement_vs_mean |   weighted_mae_improvement_vs_mean |       test_r2 |
|:-------------------------------|:---------------------------|:---------|-------:|----------------:|--------------------:|-----------------:|------------------------:|--------------------------:|-----------------------------------:|--------------:|
| next_window_bvp__mean          | bvp__mean__future          | ok       |  80000 |     0.717544    |         0.584061    |      0.720499    |             0.581811    |                0.00410086 |                        -0.00386687 |   0.060544    |
| next_window_hr__mean           | hr__mean__future           | ok       |  52557 |     2.69072     |         8.82583     |     12.4142      |            17.5833      |                0.783254   |                         0.498055   |   0.890359    |
| next_window_ibi__mean          | ibi__mean__future          | ok       |   9030 |     0.0620471   |         0.0637343   |      0.161176    |             0.144807    |                0.615035   |                         0.559866   |   0.756217    |
| next_window_ecg__mean          | ecg__mean__future          | skipped  |     99 |   nan           |       nan           |    nan           |           nan           |              nan          |                       nan          | nan           |
| next_window_eda__mean          | eda__mean__future          | ok       |  80000 |     0.146745    |         0.213663    |      5.1464      |             4.95551     |                0.971486   |                         0.956884   |   0.996018    |
| next_window_temperature__mean  | temperature__mean__future  | ok       |  80000 |     0.318156    |         0.257409    |      8.36662     |             5.95437     |                0.961973   |                         0.95677    |   0.994929    |
| next_window_acc__mag__mean     | acc__mag__mean__future     | ok       |  80000 |     0.218228    |         0.374096    |      1.67487     |             1.65258     |                0.869704   |                         0.773629   |   0.819573    |
| next_window_respiration__mean  | respiration__mean__future  | ok       |   9226 |  8546.56        |      8560.8         |  89871.1         |         89871.1         |                0.904902   |                         0.904744   |  -3.34247e+09 |
| next_window_emg__mean          | emg__mean__future          | ok       |   9127 |     0.000276686 |         0.000279126 |      0.000530152 |             0.000538141 |                0.478101   |                         0.481315   |   0.72086     |
| next_window_grip__mean         | grip__mean__future         | ok       |   9127 |     0.00839599  |         0.00779498  |      0.492377    |             0.515432    |                0.982948   |                         0.984877   |   0.997108    |
| next_window_bp_systolic__mean  | bp_systolic__mean__future  | skipped  |    490 |   nan           |       nan           |    nan           |           nan           |              nan          |                       nan          | nan           |
| next_window_bp_diastolic__mean | bp_diastolic__mean__future | skipped  |    490 |   nan           |       nan           |    nan           |           nan           |              nan          |                       nan          | nan           |
| next_window_spo2__mean         | spo2__mean__future         | skipped  |    490 |   nan           |       nan           |    nan           |           nan           |              nan          |                       nan          | nan           |
| next_window_steps__mean        | steps__mean__future        | skipped  |    490 |   nan           |       nan           |    nan           |           nan           |              nan          |                       nan          | nan           |
| next_window_eeg_delta__mean    | eeg_delta__mean__future    | ok       |   8217 | 74902.6         |     74902.6         | 226421           |        226421           |                0.669189   |                         0.669189   |   0.862129    |
| next_window_eeg_theta__mean    | eeg_theta__mean__future    | ok       |   8217 | 18796.5         |     18796.5         |  49305.9         |         49305.9         |                0.618778   |                         0.618778   |   0.799493    |

## Contrastive Probe

```json
{
  "components": 40,
  "dropout_probability": 0.45,
  "explained_variance_ratio_sum": 0.8684700521016779,
  "features": 345,
  "noise_scale": 0.025,
  "positive_cosine_mean": 0.8579415076914189,
  "positive_minus_negative_mean": 0.19087898025630323,
  "random_negative_cosine_mean": 0.6670625274351156,
  "rows": 60000,
  "status": "ok",
  "top1_same_dataset_rate": 0.9732,
  "top1_same_row_rate": 0.020266666666666665,
  "top1_same_session_rate": 0.23633333333333334,
  "top1_same_subject_rate": 0.33476666666666666
}
```

Interpretation: higher positive-vs-random cosine separation means augmented views of the same physiological window stay closer than unrelated windows. Top-1 same-row/session/subject rates show whether the representation is mostly instance-level, session-level, or dataset/protocol-level.

## Strongest Cross-Block Associations

| target_block   | target_column      | source_block   |   features_compared |   max_abs_corr |   mean_top5_abs_corr |
|:---------------|:-------------------|:---------------|--------------------:|---------------:|---------------------:|
| acc            | acc__mag__mean     | ibi            |                  10 |      0.123972  |            0.0987172 |
| acc            | acc__mag__mean     | bvp            |                  14 |      0.104187  |            0.0521488 |
| acc            | acc__mag__mean     | temperature    |                  12 |      0.103828  |            0.0530538 |
| acc            | acc__mag__mean     | eda            |                  12 |      0.072479  |            0.0515622 |
| acc            | acc__mag__mean     | hr             |                  10 |      0.0381353 |            0.0334979 |
| bp_diastolic   | bp_diastolic__mean | bp_systolic    |                   4 |      0.0336284 |            0.0336284 |
| bp_diastolic   | bp_diastolic__mean | hr             |                   4 |      0.0332568 |            0.0332568 |
| bp_diastolic   | bp_diastolic__mean | steps          |                   4 |      0.0310715 |            0.0310715 |
| bp_diastolic   | bp_diastolic__mean | spo2           |                   4 |      0.0202405 |            0.0202405 |
| bp_diastolic   | bp_diastolic__mean | temperature    |                   4 |      0.0161816 |            0.0161816 |
| bp_systolic    | bp_systolic__mean  | steps          |                   4 |      0.0381474 |            0.0381474 |
| bp_systolic    | bp_systolic__mean  | bp_diastolic   |                   4 |      0.0336284 |            0.0336284 |
| bp_systolic    | bp_systolic__mean  | temperature    |                   4 |      0.0278256 |            0.0278256 |
| bp_systolic    | bp_systolic__mean  | spo2           |                   4 |      0.0204307 |            0.0204307 |
| bp_systolic    | bp_systolic__mean  | hr             |                   4 |      0.0127273 |            0.0127273 |
| bvp            | bvp__mean          | acc            |                  60 |      0.0532719 |            0.023738  |
| bvp            | bvp__mean          | respiration    |                  10 |      0.0406782 |            0.0273392 |
| bvp            | bvp__mean          | bvp_rb         |                  10 |      0.0395509 |            0.010618  |
| bvp            | bvp__mean          | grip           |                  10 |      0.0369107 |            0.0218615 |
| bvp            | bvp__mean          | emg            |                  10 |      0.0210459 |            0.0180609 |

## Notes

- This is exploratory self-supervision, not a final pain model.
- Direct pain labels are excluded from self-supervised inputs and are only retained for auditing embeddings/results.
- Reconstruction residuals are useful candidate features for later supervised pain models.
- If metadata-conditioned metrics are too high, rerun with `--metadata none` to check whether dataset/protocol shortcuts are driving the result.
