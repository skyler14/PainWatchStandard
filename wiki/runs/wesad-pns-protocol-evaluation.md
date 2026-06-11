---
type: run
status: completed
updated: 2026-06-11
tags: [wesad, pns, meditation, external-validation]
source_files:
  - scripts/evaluate_wesad_pns_protocol.py
  - outputs/wesad_pns_protocol_evaluation/metrics.csv
---

# WESAD PNS Protocol Evaluation

## Question

Can current PNS-proxy learners, trained without WESAD, identify WESAD
meditation windows against TSST stress windows?

## Design

```yaml
training:
  data: all current weak-label feature rows except WESAD
  target: parasympathetic_recovery_proxy
  learners: [portable_logistic, random_forest, gradient_boosting]
test:
  source: WESAD only
  positive: [medi_1, medi_2]
  negative: [tsst_stress]
  rows: 879
  subjects: 15
  windows_s: [5, 10, 30]
leakage_control:
  WESAD_protocol_labels_used_in_training: false
```

Meditation is a PNS-expected protocol, not direct RSA/PNS truth.

## Results

| Learner | AUC | Balanced accuracy | Subject AUC median |
|---|---:|---:|---:|
| Portable logistic | 0.458 | 0.462 | 0.479 |
| Random forest | 0.462 | 0.518 | 0.502 |
| Gradient boosting | 0.465 | 0.514 | 0.425 |

Adding baseline to the positive calm-context class did not help: AUC ranged
from 0.369 to 0.445.

No history length rescued performance. Strict meditation-versus-stress AUC
across 5, 10, and 30 seconds stayed between 0.419 and 0.505. Median predicted
PNS probability was usually lower during meditation than during TSST stress.

## Conclusion

Current PNS proxy fails zero-shot WESAD protocol validation. Prior high PNS
proxy AUC measured reconstruction of the physiology-derived weak target, not
recognition of meditation or recovery context. Do not call current output
parasympathetic activation.

Next valid experiments:

```yaml
  - train directly on WESAD meditation versus TSST with subject holdout
  - derive respiration-linked RSA from WESAD Respiban
  - compare protocol-only, RSA-only, and joint labels
  - evaluate E4/watch and Respiban/chest profiles separately
```
