# State Normalization And R Findings

Date: 2026-05-27

## Decision Review

Old inference path allowed independent heads:

```text
pain_likelihood
stress_likelihood
low_exertion_context_likelihood
activity_likelihood
```

Problem: independent binary heads can all be high. Then UI sees high pain + high stress + high activity, and old confidence formula can still report confident positive event. This creates absurd real-world readings when model learned protocol/device/motion signatures.

Observed old confidence shape:

```text
confidence = 0.5 * sensor_quality + 0.5 * abs(probability - 0.5) * 2
```

If probability is extreme because of leakage, confidence rises. It does not ask whether competing states are also high.

## New Rule

Keep independent heads for audit. Add state-preference normalization for display/action:

```text
state_scores = pain, stress, activity, low_exertion_context, recovery, relaxed
state_preference = softmax(state_scores / temperature)
```

Meaning:

- pain can be high in absolute terms but low as preferred state if stress/activity are equally high
- low-exertion/watch context is not no-pain evidence by itself
- missing/dropout-impossible heads are omitted, not forced to zero
- sensor coverage/presence gates decide which heads are eligible
- confidence should depend on state margin, calibration, and quality, not raw positive probability alone

Candidate action confidence:

```text
state_margin = top_preference - second_preference
calibrated_confidence = calibration_quality * data_quality * f(state_margin)
```

Pain flag should need:

```text
pain_preference high
pain_abs_likelihood high
activity_preference not dominant
sensor_quality acceptable
sustained over blocks
```

## R Exploration

Script:

```text
scripts/r_phase3_state_coupling.R
```

Outputs:

```text
outputs/r_phase3_state_coupling/R_PHASE3_STATE_COUPLING_REPORT.md
outputs/r_phase3_state_coupling/leave_dataset_transfer_glm.csv
outputs/r_phase3_state_coupling/sensor_coverage_by_dataset.csv
outputs/r_phase3_state_coupling/direct_pain_transfer_state_summary.csv
outputs/r_phase3_state_coupling/all_dataset_transfer_state_summary.csv
outputs/r_phase3_state_coupling/pain_bins_vs_transfer_states.csv
outputs/r_phase3_state_coupling/confidence_formula_comparison.csv
```

R used:

- DuckDB Parquet read
- base `glm`
- dataset-level robust median/MAD normalization
- sensor present flags
- leave-dataset transfer checks
- transfer heads: pain, stress, activity, low-exertion/context
- softmax state-preference normalization

## Findings

1. Sensor availability is dataset identity.

Examples:

- PainMonit: BVP/EDA/TEMP/RESP/EMG/GRIP, no HR/ACC
- RheumaPain/PhysioPain watch: BVP/EDA/TEMP/ACC, no HR
- stress reference: HR/EDA, no BVP/ACC/TEMP
- wearable sports: HR/TEMP only

Thus dropout handling must be first-class. Missing sensor category is not random missingness; it encodes device/source.

2. GLM emitted separation/rank warnings.

Warnings:

```text
glm.fit: fitted probabilities numerically 0 or 1 occurred
glm.fit: algorithm did not converge
prediction from rank-deficient fit
```

Interpretation: simple models can become overconfident from source/sensor structure. This supports stricter confidence normalization.

3. Pain leave-dataset GLM remains weak.

High-pain leave-dataset AUC:

```text
rheumapain heldout: ~0.512
painmonit heldout: ~0.540
physiopain_watch heldout: ~0.641
```

Same pattern as old Phase 3: PhysioPain transfers somewhat, PainMonit/RheumaPain weak. Not deployable cross-dataset pain truth.

4. Stress transfer mixed.

Stress leave-source AUC:

```text
CATSA: ~0.497
merged_wearable_stress: ~0.429
stress_reference_real: ~0.566
stress_reference_synthetic: ~0.601
```

Stress labels/protocols are not one universal stress construct.

5. Activity target currently bad.

R activity head predicted `1` for nearly all direct-pain rows. Cause: available `target_activity_binary` rows are often one-class by dataset/protocol. Need better activity labels before using as strong gate.

6. Transferred stress rises with pain bin.

Direct pain rows:

```text
zero pain: stress_transfer ~0.653
mild:      stress_transfer ~0.773
moderate:  stress_transfer ~0.988
severe:    stress_transfer ~0.988
```

This suggests stress/autonomic transfer carries pain-correlated signal. It also shows why pain vs stress competition is needed.

7. Preference-normalized pain stays conservative.

Pain preference means:

```text
zero pain: ~0.187
mild: ~0.190
moderate: ~0.221
severe: ~0.234
```

Useful: severe pain increases pain preference, but stress/activity competition prevents runaway pain confidence.

## Next Model Ideas

Pioneer these next:

1. Multinomial state model with classes:

```text
low_exertion_context
cognitive_stress
emotional_arousal
exercise
direct_pain_low
direct_pain_high
unknown
```

Use `nnet::multinom` or `rpart` first. Goal: state competition native, not afterthought.

2. Multi-head model with shared robust-normalized features + availability masks.

Loss:

```text
pain loss only direct_pain rows
stress loss only stress rows
activity loss only activity rows
context loss only labeled context rows
state-contrast loss where label_family known
```

3. Calibration must be per sensor signature.

Define:

```text
sensor_signature = sorted present sensor blocks
```

Calibrate separately for:

```text
BVP+EDA+TEMP+ACC
BVP+EDA+TEMP+RESP+EMG+GRIP
HR+EDA
HR+TEMP
EEG-only
```

4. Dropout simulation during training.

Train with random sensor-block dropout only within physically plausible device packs. Do not create impossible combinations as if real.

5. Coupled transfer features.

Append auxiliary transferred states to direct-pain model:

```text
stress_transfer
low_exertion_context_transfer
activity_transfer
state_preference_pain
state_preference_margin
```

But fit these transfers inside train folds only to avoid leakage.
