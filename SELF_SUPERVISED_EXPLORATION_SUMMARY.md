# Self-Supervised Exploration Summary

Date: 2026-04-29

Implementation: [pain_self_supervised.py](</Users/skyler/Downloads/pain datasets/pain_self_supervised.py:1>)

Input feeder table:

```text
_normalized/window_features/target_hz=1/window_features.parquet
```

Rows: 32,981  
Window cadence: 1 Hz  
Window length: trailing 30 seconds  

## Runs

Two exploratory runs were generated:

| Run | Metadata Features | Output |
| --- | --- | --- |
| Basic metadata | Includes dataset/protocol metadata except subject/session IDs and labels | `_normalized/self_supervised/exploratory_1hz_30s` |
| No metadata | Excludes dataset/protocol metadata from features | `_normalized/self_supervised/exploratory_1hz_30s_no_metadata` |

Each run writes:

```text
SELF_SUPERVISED_EXPLORATION_REPORT.md
metadata_label_audit.json
sensor_interconnection.csv
reconstruction_metrics.csv
reconstruction_predictions.parquet
next_window_metrics.csv
next_window_predictions.parquet
contrastive_metrics.json
contrastive_embeddings.parquet
manifest.json
```

## Balancing

The run uses `balance_mode=dataset_session`.

This adds `ssl_weight` so over-represented datasets/sessions do not dominate training or metrics.

Observed weight totals:

| Dataset | Rows | Sessions | Weight Sum |
| --- | ---: | ---: | ---: |
| PainMonit | 9,217 | 90 | 16,490.5 |
| RheumaPain | 23,764 | 83 | 16,490.5 |

PainMonit receives higher average row weight because it has fewer feeder rows. RheumaPain receives lower average row weight because it has more feeder rows. The total dataset influence is equalized in this exploratory step.

## Main Findings

### 1. Dataset/device separability is very strong

Contrastive results with basic metadata:

```text
positive_cosine_mean: 0.585
random_negative_cosine_mean: 0.018
positive_minus_negative_mean: 0.568
top1_same_dataset_rate: 0.999
top1_same_session_rate: 0.676
top1_same_subject_rate: 0.765
```

Contrastive results without metadata:

```text
positive_cosine_mean: 0.567
random_negative_cosine_mean: 0.021
positive_minus_negative_mean: 0.546
top1_same_dataset_rate: 0.999
top1_same_session_rate: 0.656
top1_same_subject_rate: 0.737
```

Interpretation: explicit metadata is not the main reason windows separate by dataset. The sensor/protocol structure itself separates them: PainMonit has respiration, EMG, grip, and respiratory-belt channels, while RheumaPain has ACC and E4-like watch channels. Downstream supervised models must be evaluated by device/sensor subset, not only by row-level splits.

### 2. Next-window prediction works, but mostly measures autocorrelation

Good one-step-ahead prediction:

| Target | Weighted MAE Improvement |
| --- | ---: |
| `eda__mean__future` | 0.944 |
| `temperature__mean__future` | 0.859 |
| `acc__mag__mean__future` | 0.881 |
| `grip__mean__future` | 0.949 |
| `emg__mean__future` | 0.483 |

Interpretation: the feeder windows contain strong short-term continuity. These next-window residuals are useful candidate features, but this is not evidence of pain prediction by itself.

### 3. Cross-sensor reconstruction is mixed

Better reconstruction targets:

| Target | Weighted MAE Improvement |
| --- | ---: |
| `grip__mean` | 0.328 |
| `emg__mean` | 0.133 |
| `eda_rb__mean` | 0.054 |

Weak/negative reconstruction targets:

| Target | Weighted MAE Improvement |
| --- | ---: |
| `bvp__mean` | -0.050 |
| `eda__mean` | -0.372 |
| `temperature__mean` | -0.739 |
| `acc__mag__mean` | -0.028 |

Interpretation: many sensor means are not reliably inferred from the other current sensor blocks in this mixed dataset. That argues against aggressive imputation as a first strategy. Preserve missingness flags and use reconstruction residuals where they are empirically useful.

### 4. Sensor associations are strongest inside related physiology groups

Top cross-block associations include:

```text
eda <-> eda_rb
eda <-> respiration
bvp_rb <-> eda_rb
bvp_rb <-> respiration
acc magnitude <-> bvp / eda / temperature, weakly
```

This is directionally plausible, but current correlations are still shaped by dataset-specific sensor availability.

## Implications For Downstream Pain Models

Use these guardrails:

1. Always carry `ssl_weight` or equivalent dataset/session weights into training.
2. Evaluate leave-subject-out.
3. Add leave-dataset-out or train-on-one/test-on-the-other checks.
4. Add sensor-subset evaluation:
   - E4-like: BVP + EDA + TEMP + ACC
   - PainMonit clinical: BVP + EDA + TEMP + RESP + EMG + GRIP
   - Minimal wearable: TEMP + ACC
   - Missing BVP
   - Missing EDA
5. Do not impute absent sensors as if they were observed.
6. Use reconstruction residuals as optional features, not required replacements.

## Commands

Basic metadata run:

```bash
python3 pain_self_supervised.py \
  --max-model-rows 6000 \
  --model-iterations 50 \
  --contrastive-sample 5000 \
  --output _normalized/self_supervised/exploratory_1hz_30s
```

No-metadata run:

```bash
python3 pain_self_supervised.py \
  --metadata none \
  --max-model-rows 6000 \
  --model-iterations 50 \
  --contrastive-sample 5000 \
  --output _normalized/self_supervised/exploratory_1hz_30s_no_metadata
```

Full uncapped model run, if we want more stable metrics:

```bash
python3 pain_self_supervised.py \
  --model-iterations 100 \
  --contrastive-sample 12000 \
  --output _normalized/self_supervised/exploratory_1hz_30s_fuller
```
