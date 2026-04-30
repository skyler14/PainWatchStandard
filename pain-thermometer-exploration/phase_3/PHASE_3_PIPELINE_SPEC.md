# Phase 3 Multi-Task Pain Thermometer Pipeline

Date: 2026-04-29

## Purpose

Phase 3 deploys the refined lightweight pipeline rather than replacing the project with a heavy sequence model. The core Phase 1 approach stays intact: compressed local files become canonical trailing windows, sensors remain as debuggable feature blocks, and models are evaluated by subject and source transfer. The Stress reference work is used selectively: it adds source-transfer discipline, auxiliary stress/state rows, and dataset-balanced weighting, but it does not turn stress labels into pain labels.

The main change is formal task routing. Every row now carries `label_family`, `source_family`, `collection_protocol`, and `pain_label_regime`. Direct pain rows can train pain regression or ordinal/classification targets. Stress, cognitive, emotion, exercise, and baseline rows can train auxiliary state heads or provide self-supervised coverage, but they are not allowed to update the direct pain objective. This keeps the useful physiological diversity without teaching the model that "stress equals pain."

## Deployment Artifacts

Phase 3 code lives in:

```text
phase_3/analysis/phase3_prepare_dataset.py
phase_3/analysis/phase3_multitask_baseline.py
```

The deployed Phase 3 feeder table and reports are written outside the repo with the rest of the large normalized artifacts:

```text
../_normalized/phase3/target_hz=1/window_features.parquet
../_normalized/phase3/target_hz=1/window_features.manifest.json
../_normalized/phase3/target_hz=1/label_family_audit.csv
../_normalized/phase3/target_hz=1/baselines/phase3_metrics.csv
../_normalized/phase3/target_hz=1/baselines/PHASE_3_BASELINE_REPORT.md
```

## Experimental Procedure

The dataset builder combines the Phase 1 all-dataset 1 Hz / 30 second window table with the Phase 2 Stress reference feeder rows. It then joins available baseline/state atlas fields, assigns label families, creates routing targets, and writes a compressed Parquet table. The first deployed run produced 611,439 windows and 422 columns. Direct pain supervision is limited to PainMonit, RheumaPain, and PhysioPain watch, totaling 41,520 pain-labeled rows. Stress/proxy supervision comes mostly from the Stress reference real and synthetic rows, plus WESAD and merged wearable stress rows.

The first baseline runner uses sklearn `HistGradientBoosting` models instead of transformers. This is intentional. The current question is not whether a large architecture can memorize the data; it is whether simple, inspectable models can show pain signal after subject/source blocking and whether metadata/protocol features are overpowering physiology. The runner trains separate task probes for direct pain, stress binary state, and baseline state. It evaluates multiple sensor subsets: `sensors_plus_state`, `apple_watch_like`, `hr_eda_stress`, `autonomic_core`, and `metadata_probe`.

Training uses dataset-balanced and class-balanced sample weights. Dataset balancing prevents very large sources, especially the Stress reference rows, from dominating the loss. Class balancing prevents low-prevalence states such as RheumaPain high-pain windows from disappearing under majority labels. `target_confidence` is also used on pain tasks so weak/session labels can be down-weighted relative to denser direct labels. This is the first implemented guardrail for the over-represented-sensor concern.

Validation is deliberately stricter than a pooled random split. Phase 3 reports direct-pain group holdout by `dataset_id::subject_id`, leave-direct-pain-dataset-out transfer, selected within-dataset LOSO checks, stress source transfer, and baseline-state group holdout. The metadata probe is preserved as a diagnostic, not as a deployment feature set: if metadata beats sensors under blocked validation, the result is telling us protocol identity remains a major confounder.

## Interface And Data Window Spec

The Phase 3 interface is still one row per prediction anchor:

```text
one row = one prediction anchor
anchor cadence = 1 Hz in this run
window = trailing 30 seconds ending at the anchor
sensor values = block-level native-sample summaries
targets = routed by label_family
```

An example direct-pain row has `label_family=direct_pain`, `target_available=1`, `target_pain_nrs_0_10`, `target_pain_ordinal_4`, `target_confidence`, and optional `target_stress_binary=NULL`. An auxiliary stress row has `label_family=stress_proxy`, `target_available=0`, no pain target, and `target_stress_binary` when a stress label exists. Baseline/state rows can expose `target_baseline_binary`, `baseline_state_bin`, `baseline_missing`, and `baseline_anchor_id`.

Z-score normalization is not used as a destructive preprocessing replacement. The feeder keeps raw window summaries, presence flags, valid-fraction flags, and baseline/state features. Personal baseline deltas or z-like features make sense when a subject has a clearly labeled relaxed/rest/no-pain anchor, but population scaling must remain inside the train-fold model pipeline. For collected data, the desired interface is to label baseline states explicitly, such as relaxed, passively in pain, exercising, agitated, and recovering, then let downstream models learn state-specific offsets rather than forcing one universal biological baseline.

## First Deployed Results

The initial fast run shows real but limited direct-pain signal. On direct-pain group holdout, `sensors_plus_state` reached high-pain ROC-AUC about `0.788`, average precision about `0.614`, and regression MAE improvement about `4.6%` over the training-mean baseline. The Apple-Watch-like subset was close: ROC-AUC about `0.780` and regression MAE improvement about `3.8%`. The metadata probe was stronger on pooled group holdout, with ROC-AUC about `0.819` and regression MAE improvement about `14.2%`, which means protocol/context leakage is still a serious confounder.

Leave-dataset-out pain transfer is the key warning. Holding out PainMonit was near random for high-pain classification, around `0.51` ROC-AUC for `sensors_plus_state` and below random for the Apple-Watch-like set. Holding out PhysioPain watch was modest, with Apple-Watch-like ROC-AUC about `0.674`. Holding out RheumaPain was also modest at about `0.65`, but RheumaPain high-pain prevalence is very low in this window table, so balanced accuracy and regression should be read together.

Auxiliary stress/state behavior is much stronger, which is expected because those rows are larger and have cleaner binary labels. Stress source transfer reached about `0.86` ROC-AUC on held-out SWELL with autonomic features, about `0.62` on NEURO, around random on UBFC and WESAD, and perfect scores for metadata probes because source/protocol identity leaks the label. The baseline-state probe reached about `0.98` ROC-AUC with watch-like sensors plus state fields. That is useful for state binning, but it also shows why baseline/protocol labels must be blocked carefully.

## Phase 3 Next Step

The next Phase 3 run should move from the fast deployment to a full integrity pass. Run the full feature mode, increase selected LOSO subjects or make LOSO exhaustive per direct-pain dataset, add ordinal pain-bin metrics, and add a strict no-metadata/no-state-ablation report so we can separate physiology, baseline-derived state, and protocol identity. PainMonit deserves special attention because cross-dataset transfer currently fails there; the likely causes are clinical protocol differences, sparse pain labels, and sensor-schema mismatch.

The best Phase 3 model candidate should not be chosen by pooled AUC. It should be chosen by whether sensor-only or sensor-plus-baseline models beat training-mean and metadata shortcuts under leave-subject, leave-dataset, and label-regime-blocked validation. Only after that should we add more sophisticated ensembling, residual state features from self-supervision, or synthetic state balancing.

## Commands

Build the Phase 3 feeder table:

```bash
/opt/anaconda3/envs/thepipe/bin/python phase_3/analysis/phase3_prepare_dataset.py
```

Run the fast deployed baseline:

```bash
/opt/anaconda3/envs/thepipe/bin/python phase_3/analysis/phase3_multitask_baseline.py --model-iterations 60 --max-aux-rows 60000 --max-loso-subjects 2 --feature-mode fast
```

Run the slower full feature pass:

```bash
/opt/anaconda3/envs/thepipe/bin/python phase_3/analysis/phase3_multitask_baseline.py --model-iterations 100 --max-aux-rows 120000 --max-loso-subjects 6 --feature-mode full
```
