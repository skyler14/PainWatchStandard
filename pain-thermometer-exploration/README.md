# Pain Thermometer Exploration

This repository packages the Phase 1 exploratory analysis for a wearable pain-score pipeline, a Phase 2 reference analysis using `github.com/xalentis/Stress`, and the first deployed Phase 3 multi-task baseline pipeline.

The work is intentionally split into two phases:

- `phase_1/`: what we already built and measured from the local pain/wearable archives.
- `phase_2/`: reference stress-model work, code/data notes, lift analysis, and a refined plan for rerunning Phase 1.
- `phase_3/`: multi-task feeder construction, task-routed lightweight baselines, and the Phase 3 pipeline spec.
- `src/`: small bridge scripts that adapt reference data into our feeder-style format.

Large source archives remain outside this repository in the parent working directory. The Phase 2 reference repo is cloned into `phase_2/reference/Stress` and registered in `.gitmodules` so the upstream dependency is explicit.

## Key Artifacts

- Phase 1 report: `phase_1/PHASE_1_EXPLORATORY_ANALYSIS.md`
- Phase 2 report: `phase_2/PHASE_2_REFERENCE_AND_REFINED_APPROACH.md`
- Full Stress reference report: `phase_2/FULL_STRESS_REFERENCE_REPORT.md`
- Stress repo scaffold notes: `phase_2/reference/STRESS_SCAFFOLDING.md`
- Stress reference metrics: `phase_2/analysis/outputs/stress_reference_metrics.csv`
- Stress reference lift table: `phase_2/analysis/outputs/stress_reference_lifts.csv`
- R stress reference metrics: `phase_2/analysis/outputs/stress_reference_r_metrics.csv`
- Stress feeder rows: `phase_2/analysis/outputs/stress_reference_feeder_rows.parquet`
- Phase 3 pipeline spec: `phase_3/PHASE_3_PIPELINE_SPEC.md`
- Phase 3 dataset builder: `phase_3/analysis/phase3_prepare_dataset.py`
- Phase 3 baseline runner: `phase_3/analysis/phase3_multitask_baseline.py`
- Phase 3 external feeder table: `../_normalized/phase3/target_hz=1/window_features.parquet`
- Phase 3 external baseline report: `../_normalized/phase3/target_hz=1/baselines/PHASE_3_BASELINE_REPORT.md`

## Reproduction Commands

Use the local conda Python that has the needed packages:

```bash
/opt/anaconda3/envs/thepipe/bin/python phase_2/analysis/stress_reference_analysis.py
/opt/anaconda3/envs/thepipe/bin/python src/stress_reference_feeder_adapter.py
./.conda-r/bin/Rscript phase_2/analysis/stress_reference_r_analysis.R
/opt/anaconda3/envs/thepipe/bin/python phase_3/analysis/phase3_prepare_dataset.py
/opt/anaconda3/envs/thepipe/bin/python phase_3/analysis/phase3_multitask_baseline.py --model-iterations 60 --max-aux-rows 60000 --max-loso-subjects 2 --feature-mode fast
```

The original `xalentis/Stress` code is R-based. Global Homebrew `Rscript` was not available during this pass, so the repo includes both a Python/sklearn equivalent and an R 4.6.0 validation script run from the local `.conda-r/` environment.
