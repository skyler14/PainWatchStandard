# Stress Repo Scaffolding Notes

Generated from local inspection plus `thepipe` code-relation mapping on `phase_2/reference/Stress`.

## Top-Level Shape

The repo is a compact R analysis project built around derived HR/EDA feature tables.

- `README.md`: paper/reproduction overview and links.
- `StressData.zip`: bundled real merged stress feature table.
- `SynthesizedStressData.zip`: bundled synthetic stress feature table.
- `MakeStressData.R`: builds the real merged feature table from raw public datasets when those raw datasets are available locally.
- `MakeSynthesizedStressData.R`: builds the synthesized feature table.
- `Experiment1.R` through `Experiment11.R`: paper experiment scripts for real, synthetic, mixed, and validation settings.
- `Supplement6.R`, `Supplement10.R`: supplemental experiment scripts.
- `Exploration.R`: exploratory checks.
- `ConvertBVP2HR.py`: helper for BVP-to-HR conversion.
- `stresshelpers/`: local R helper package used by the experiment scripts.

## Main Code Flow

The original workflow is:

1. Convert raw public datasets into a common engineered feature schema.
2. Merge real sources into `StressData.csv`.
3. Generate or load synthesized rows into `SynthesizedStressData.csv`.
4. Train classical models and small neural ensembles over HR/EDA engineered features.
5. Evaluate source-transfer and validation behavior.

The scripts rely on R packages that are not installed here, including `caret`, `xgboost`, `randomForest`, `keras`, and the local `stresshelpers` package. For our Phase 2 pass, I used the included derived zips directly and ran a Python/sklearn equivalent focused on the same transfer/lift question.

## Included Feature Schema

The bundled real and synthetic zips share these feature columns:

```text
hrrange
hrvar
hrstd
hrmin
edarange
edastd
edavar
hrkurt
edamin
hrmax
metric
subject
```

`metric` is the binary stress label. `subject` encodes source for the real table by prefix: `N` = NEURO, `S` = SWELL, `U` = UBFC, `W` = WESAD. Synthetic rows use `X`.

## Relevance To Pain Thermometer

This repo should not be treated as pain supervision. It is useful because it provides a clean example of lightweight tree/boosting models over wearable HR/EDA features and because its synthetic feature table improved cross-source stress transfer in our Python equivalent run. For our pipeline, these rows belong in auxiliary state learning and confounder modeling.
