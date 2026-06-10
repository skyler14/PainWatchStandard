---
type: model
status: active
updated: 2026-06-10
tags: [autonomic-space, sympathetic, parasympathetic, RSA, PEP, CAB, CAR, functional-pain]
source_files:
  - src/painwatchstandard/functional_pain_v1.py
  - wiki/model/functional-pain-v1.md
external_sources:
  - https://philpapers.org/rec/BERADT-2
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC3767155/
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC8119784/
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC8604051/
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC5624990/
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC12987280/
  - https://www.biopac.com/impedance-cardiography-and-pre-ejection-period/
  - https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2017.00301/full
---

# Autonomic Space Model

Core idea: sympathetic and parasympathetic activity are not one slider. They can move independently.

## Vetted Model

Classic autonomic-space work rejects simple autonomic determinism. The two branches can be:

```yaml
reciprocal_sympathetic:
  pns: down
  sns: up
  example: exercise, threat, effort

reciprocal_parasympathetic:
  pns: up
  sns: down
  example: calming, rest, recovery

coactivation:
  pns: up
  sns: up
  example: dive reflex, cold-face response, mixed threat + bradycardia patterns

coinhibition:
  pns: down
  sns: down
  example: faint/shutdown-like states, severe dysregulation

uncoupled_pns:
  pns: changes
  sns: stable
  example: paced breathing / vagal modulation without strong arousal

uncoupled_sns:
  sns: changes
  pns: stable
  example: sudomotor arousal, vasoconstriction, some cognitive tasks
```

Important sign convention:

```yaml
rsa:
  higher: more cardiac vagal / parasympathetic activity

rmssd:
  higher: usually more short-term vagal HRV when signal quality and context valid

pep:
  shorter: more cardiac sympathetic contractility
  longer: sympathetic withdrawal

eda:
  higher_or_more_phasic: more sympathetic sudomotor arousal
```

## Gold-Standard Axes

```yaml
pns_axis:
  best_lab_marker: RSA
  derived_from:
    - beat-to-beat heart intervals
    - respiration phase or respiratory-frequency HRV band
  interpretation: cardiac vagal modulation

sns_axis:
  best_lab_marker: PEP
  derived_from:
    - ECG Q-wave onset
    - impedance cardiography dZ/dt B-point
  interpretation: cardiac sympathetic beta-adrenergic contractility
```

PEP caveat:

```yaml
strong_for: cardiac sympathetic inotropy
not_available_from: normal Apple Watch / most wrist PPG exports
not_same_as: EDA or HR
newer_warning: PEP-derived CAB/CAR may not fully separate autonomic balance and regulation; LVET plus RMSSD may sometimes separate axes better
```

## CAB And CAR

Published composite formulas often standardize PNS and SNS markers first.

```yaml
inputs:
  pns_z: RSA_z or HF_HRV_z or RMSSD_z
  sns_z: -PEP_z
  reason: shorter PEP means higher sympathetic activity

cardiac_autonomic_balance_CAB:
  formula: pns_z - sns_z
  high_positive: parasympathetic dominance
  high_negative: sympathetic dominance

cardiac_autonomic_regulation_CAR:
  formula: pns_z + sns_z
  high_positive: coactivation / high total cardiac autonomic regulation
  high_negative: coinhibition / low total cardiac autonomic regulation
```

PainWatch translation:

```yaml
functional_pain_v1:
  sympathetic: approximate sns axis
  parasympathetic: approximate pns axis
  homeostasis: near-baseline / low departure axis

future_functional_pain_v2:
  add:
    - cab_proxy
    - car_proxy
    - autonomic_mode
    - pns_reactivity
    - sns_reactivity
```

## Derivable From Current Data

```yaml
directly_derivable_now:
  rmssd:
    data_needed: ibi
    current_status: implemented as ibi__rmssd_ms
    branch: pns_proxy
    caution: needs enough clean beats; 5s weak, 30s better, 60s+ better

  sdnn:
    data_needed: ibi
    current_status: implemented as ibi__sdnn_ms
    branch: mixed_longer_hrv
    caution: duration-sensitive, not pure pns

  hr_recovery_slope:
    data_needed: hr over time
    current_status: slope_per_s exists
    branch: recovery_proxy
    caution: needs context after exertion/stress/pain

  eda_level_slope_peaks:
    data_needed: eda
    current_status: mean, std, slope, peak_count exist
    branch: sns_sudomotor_proxy
    caution: wrist EDA weaker than palm; motion/temp artifacts

  bvp_instability:
    data_needed: bvp
    current_status: std/slope/peaks exist; richer morphology in temporal-shape scripts
    branch: mixed vascular/autonomic proxy
    caution: device gain and motion sensitive

  skin_temp_drop:
    data_needed: temperature
    current_status: slope_per_s exists
    branch: vasoconstriction / context proxy
    caution: ambient and device contact confound

  activity_load:
    data_needed: acc
    current_status: acc_mag summaries exist
    branch: confound/context
    caution: must gate HR/EDA interpretation
```

```yaml
partly_derivable_now:
  rsa_proxy:
    data_needed:
      - clean IBI or ECG R-R intervals
      - respiration signal or respiratory-rate estimate
    current_sources:
      - PMED has respiration + ECG/IBI
      - WESAD/Respiban has chest respiration + ECG
      - Apple export may have respiratory rate but not continuous phase
    method:
      - align R-R intervals to respiration phase
      - measure heart-period oscillation at breathing frequency
      - optionally compute respiratory-HR coherence
    output:
      - rsa_amplitude
      - rsa_coherence
      - rsa_reactivity_from_baseline

  hf_hrv:
    data_needed: longer clean IBI series
    current_status: possible in longer windows, not robust in 5s/10s
    method: spectral power in respiratory/HF band
    caution: breathing rate shifts HF interpretation

  ppg_respiratory_surrogate:
    data_needed: high-rate BVP/PPG
    method:
      - derive respiration from amplitude modulation
      - derive respiration from baseline wander
      - derive respiration from pulse interval modulation
    caution: exploratory only; needs validation against respiration belt
```

```yaml
not_derivable_from_current_watch_only_data:
  pep:
    missing:
      - impedance cardiography dZ/dt
      - ECG Q-wave quality
      - or validated seismocardiography chest signal

  lvet:
    missing:
      - impedance cardiography or high-quality cardiac timing waveform

  baroreflex_sensitivity:
    missing:
      - continuous blood pressure or validated pulse transit/blood pressure proxy

  pupil_pns_sns_axis:
    missing:
      - controlled pupillometry / camera protocol
```

## Acquisition Routes

```yaml
rsa_best:
  hardware:
    - ECG chest strap or clinical ECG
    - respiration belt
  protocol:
    - 2-5 min quiet baseline
    - paced breathing segment if possible
    - stress/pain/intervention/recovery blocks
  data_product:
    - rsa_amplitude
    - rsa_reactivity
    - respiratory_rate
    - respiratory_hr_coherence

rsa_watch_feasible:
  hardware:
    - Apple Watch / PPG device with IBI/HRV exports
    - optional respiratory rate during sleep
  protocol:
    - sleep/rest baseline
    - low-motion breathing or recovery sessions
  data_product:
    - rmssd/sdnn trend
    - rough pns_recovery score
  limitation: not true RSA without breath phase

pep_best:
  hardware:
    - impedance cardiography chest setup
    - ECG + dZ/dt
  protocol:
    - lab-quality baseline/task/recovery
  data_product:
    - pep_ms
    - sns_reactivity
    - CAB/CAR gold-ish axes

pep_field_experimental:
  hardware:
    - ECG + chest seismocardiography accelerometer
  protocol:
    - validate against impedance cardiography
  data_product:
    - scg_pep_proxy
  limitation: not wrist-only

sns_wearable:
  hardware:
    - EDA wristband or E4
    - PPG/BVP
    - skin temperature
    - accelerometer
  protocol:
    - artifact labels
    - motion contexts
    - ambient/contact checks
  data_product:
    - eda_scl
    - nonspecific_scr_rate
    - eda_reactivity
    - vascular/temperature proxies
```

## Functional Pain Scoring Implication

Do not collapse autonomic space into one pain value too early.

```yaml
display_state:
  - sympathetic
  - parasympathetic
  - homeostasis

derivative_scores:
  cab_proxy:
    formula_shape: pns_proxy_z - sns_proxy_z
    meaning: branch dominance

  car_proxy:
    formula_shape: pns_proxy_z + sns_proxy_z
    meaning: coactivation vs coinhibition

  pns_recovery:
    formula_shape: positive rmssd/rsa change + falling hr + falling eda
    meaning: successful downshift

  unresolved_arousal:
    formula_shape: sympathetic high + homeostasis low + no activity explanation
    meaning: pain/stress-like unresolved load

  functional_pain:
    formula_shape: unresolved_arousal + direct-pain residual model
    meaning: pain-relevant state, not diagnosis
```

## Proposed Data Additions

No raw schema rewrite needed. Add derived feature columns.

```yaml
standard_window_additions:
  hrv_quality:
    - ibi_beat_count
    - ibi_outlier_frac
    - hrv_window_duration_s
    - hrv_valid_for_rmssd
    - hrv_valid_for_sdnn

  pns_proxy:
    - rmssd_robust_z_by_archetype
    - sdnn_robust_z_by_archetype
    - hr_recovery_slope_z
    - rsa_proxy_when_resp_available
    - rsa_quality

  sns_proxy:
    - eda_scl_robust_z_by_archetype
    - eda_scr_rate
    - eda_rise_slope_z
    - skin_temp_drop_z
    - bvp_amplitude_or_instability_z

  autonomic_space:
    - sns_proxy_z
    - pns_proxy_z
    - cab_proxy
    - car_proxy
    - autonomic_mode
```

Autonomic mode labels:

```yaml
mode_rules:
  reciprocal_sympathetic: sns_delta_z >= 1 and pns_delta_z <= -1
  reciprocal_parasympathetic: sns_delta_z <= -1 and pns_delta_z >= 1
  coactivation: sns_delta_z >= 1 and pns_delta_z >= 1
  coinhibition: sns_delta_z <= -1 and pns_delta_z <= -1
  uncoupled_sns: abs(pns_delta_z) < 0.5 and abs(sns_delta_z) >= 1
  uncoupled_pns: abs(sns_delta_z) < 0.5 and abs(pns_delta_z) >= 1
  homeostatic: abs(sns_delta_z) < 0.5 and abs(pns_delta_z) < 0.5
```

Thresholds are starting heuristics. They must be calibrated per user, device, and archetype.

## Watch-First Strategy

```yaml
v1_now:
  pns: RMSSD/SDNN + HR recovery + respiration regularity if available
  sns: EDA + HR/BVP/temp + activity gating
  mode: approximate autonomic-space proxy

v2_with_respiration:
  pns: RSA proxy from IBI + respiration
  sns: EDA/BVP/temp
  mode: better branch separation

v3_lab_validation:
  pns: RSA
  sns: PEP or LVET
  mode: true autonomic-space calibration
```

## Sources Notes

Berntson/Cacioppo/Quigley define autonomic space and coupled/uncoupled modes. RSA is widely treated as cardiac vagal control proxy. PEP is a standard cardiac sympathetic systolic-time marker, requiring ECG plus impedance cardiography. CAB/CAR formulas commonly use standardized PNS and SNS markers, but newer systolic-time work warns PEP may not always separate balance from regulation as cleanly as assumed.
