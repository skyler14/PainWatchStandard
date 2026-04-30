# Phase 1 Exploratory Analysis

Date: 2026-04-29

## Purpose

Phase 1 tested whether the local zipped and compressed datasets can be wrapped into a temporary data gateway, normalized into common time-series windows, and used to produce early evidence for a wearable "pain thermometer." The core question was deliberately modest: do the data and feature pipeline contain any predictive signal for pain, and can we separate that signal from stress, movement, exercise, subject baselines, and dataset/protocol artifacts?

The first normalization pass focused on direct-pain data: RheumaPain, PainMonit clinical, and PhysioPain watch. A broader archive-backed feeder then pulled in proxy and auxiliary datasets from CATSA, EPM-E4, WESAD, induced stress/exercise, merged wearable stress, wearable sports health, sample_27_9vuw, PhysioPain EEG, plus the normalized direct-pain tables. The resulting all-dataset table contains 103,149 windows across 11 dataset IDs. Direct pain labels exist only in RheumaPain, PainMonit, and PhysioPain watch; the other datasets are treated as auxiliary state/proxy data, never as pain truth.

## Experimental Procedure

The pipeline began by inventorying the zip and CSV archives without fully expanding them. For each supported source, we streamed only the needed members, mapped sensor names into canonical blocks, and wrote compressed Parquet outputs. The initial normalized direct-pain streams were built for RheumaPain and PainMonit PMCD. A second all-dataset feeder added archive-backed windows for CATSA, induced stress/exercise, WESAD E4, EPM-E4 clean Empatica slices, PhysioPain watch, PhysioPain EEG, merged wearable stress, wearable sports health, and sample_27_9vuw.

After windowing, we ran exploratory self-supervised probes. These were not pain models. They tested whether sensor blocks could reconstruct other sensor blocks, whether current windows could predict the next window, and whether augmented views of the same physiological window stayed close in a contrastive/PCA representation. We ran both metadata-inclusive and no-metadata checks to expose whether the model was learning sensor structure or merely dataset/protocol identity. Dataset/session weighting was applied so dense sources did not dominate.

Finally, we ran a supervised first-pass analysis using only direct-pain labels. This used lightweight sklearn gradient-boosted models over feature sets such as sensors-only, sensors-plus-state, E4-like, Apple-Watch-like, autonomic-core, motion-only, metadata-only, and sensors-plus-metadata. Results were reported under pooled subject holdout, within-dataset subject holdout, and leave-dataset-out validation. Leave-dataset-out is the most important integrity check because it shows whether a model transfers beyond the collection protocol it saw during training.

## Interface And Data Window Spec

The main modeling interface is a compressed Parquet table where each row is a trailing time window anchored at a regular prediction cadence. The Phase 1 all-dataset table is:

```text
../_normalized/window_features_all/target_hz=1/window_features.parquet
```

The current first-pass window spec is 1 Hz output cadence with a 30 second trailing window. Long sessions were capped to 100 evenly sampled windows for the first all-source pass so no dataset could overpower the exploratory analysis. Each row includes identifiers (`dataset_id`, `subject_id`, `session_id`), timing (`window_start_s`, `window_end_s`, `window_seconds`, `target_hz`), source metadata, sensor-block features, label fields, and baseline/state atlas fields where available.

Sensor blocks use canonical prefixes. Examples include `bvp__mean`, `eda__std`, `temperature__slope_per_s`, `acc__mag__mean`, `hr__mean`, `ibi__mean`, `respiration__mean`, `emg__mean`, `grip__mean`, and EEG band features. For each block, the feeder attempts to preserve presence and quality information through `__present`, `__valid_count`, and `__valid_frac` columns. Missing sensors are not aggressively imputed; missingness is part of the feature surface.

Pain targets are represented as `target_pain_nrs_0_10`, `target_pain_class_3`, `target_granularity`, `target_confidence`, and related coverage fields. This does not mean all datasets share identical label semantics. PainMonit is the strongest direct label source, RheumaPain is weak/session-level and low-range in these windows, and PhysioPain watch uses a source scale that currently maps as direct but still needs tighter semantic validation.

The temporary server/gateway work exposed these Parquet/CSV-backed tables without creating a dedicated database file. A PostgreSQL-compatible demo dump was also generated:

```text
../_exports/pain_demo_postgres_all_datasets.sql.gz
```

## Baseline And State Handling

Baseline is currently handled in two ways. First, when a dataset has an explicit rest/baseline/no-pain/neutral state, the feeder can compute per-subject baseline deltas and z-score-like features for mean sensor values. Second, the all-dataset pass creates a baseline/state atlas that bins rows into `baseline_like`, `moderate_departure`, `strong_departure`, `extreme_departure`, or `no_subject_baseline`.

This is a useful but incomplete state map. CATSA, EPM-E4, parts of RheumaPain, and some PhysioPain no-pain rows produce usable baseline-like anchors. PainMonit clinical, WESAD, induced stress/exercise, merged stress, and sample_27 still need clearer protocol parsing before baseline anchors are trustworthy. At this stage, the state atlas is best viewed as "departure from available baseline," not as a complete biological coordinate system for relaxed, pained, exercising, agitated, and recovering states.

## Results

The all-dataset self-supervised pass produced 103,149 windows and 385 columns. Contrastive separation survived the no-metadata check, but dataset identity remained very visible: top-1 same-dataset nearest-neighbor rate was about 0.94 without metadata. That means sensor/device/protocol signatures are still strong. This is expected for heterogeneous wearable datasets, but it means downstream pain models must use leave-dataset and leave-subject validation.

Next-window prediction was strong for several autocorrelated streams: EDA, temperature, grip, HR, IBI, EEG bands, and some ACC settings. Cross-sensor reconstruction was mixed. EEG bands, IBI, grip, and HR reconstructed better than baseline, while BVP, EDA, and ACC were weak or unstable. The practical conclusion is that we should preserve missing-sensor flags and not rely on broad sensor hallucination or imputation.

The supervised first-pass showed nonzero predictive signal but not a general pain model yet. Pooled high-pain classification reached ROC-AUC around 0.78 for sensors-only, 0.78 for sensors-plus-state, and 0.79 for Apple-Watch-like sensors. Motion-only was also high, around 0.81, which is a warning that protocol/activity effects may be helping. Pooled regression was weak; metadata-only and metadata-heavy models were competitive with or stronger than pure sensor models, again showing confounding.

The integrity checks were more mixed. Within-dataset subject-holdout worked best for PhysioPain watch, where Apple-Watch-like sensors improved regression MAE by about 26%. RheumaPain showed modest MAE improvement around 14%. PainMonit subject-holdout was negative, meaning the model did worse than predicting that dataset's training mean for new subjects. Leave-dataset-out high-pain classification was modest: PainMonit held out was near random, PhysioPain held out reached about 0.64-0.66 AUC with state features, and RheumaPain held out reached about 0.74 AUC with sensors-plus-state, but with very low high-pain prevalence.

## Phase 1 Conclusion

Phase 1 proves that the data gateway, feeder, state atlas, self-supervised probes, and supervised validation scripts work end to end. It also proves there is some pain-correlated physiological signal. It does not prove we have a deployable cross-dataset pain thermometer. The strongest current interpretation is that the pipeline can detect physiological/protocol state and some pain-related signal, but target semantics and dataset confounding are still the limiting factors.

The right next step is not a larger model. It is a more disciplined second pass: harmonize direct-pain labels into per-dataset ordinal regimes, parse baseline/protocol intervals more accurately, incorporate stress-state data as auxiliary context, and evaluate sensor subsets with leave-subject and leave-dataset splits.
