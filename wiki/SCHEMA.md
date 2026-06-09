---
type: schema
status: active
updated: 2026-06-08
---

# Wiki Schema

This wiki is LLM-maintained project memory for `PainWatchStandard`.

## Layers

```yaml
raw_sources:
  location: /Users/skyler/Downloads/PainDatasets
  rule: immutable, never edit from wiki work

code_source:
  location: /Users/skyler/Downloads/pain datasets/PainWatchStandard
  rule: current clean-room implementation is source of truth

wiki:
  location: wiki/
  rule: LLM writes and maintains markdown synthesis
```

## Page Types

```yaml
overview:
  path: wiki/overview.md
  purpose: project map and current truth

dataset:
  path: wiki/datasets/*.md
  purpose: source coverage, labels, sensors, use/avoid rules

pipeline:
  path: wiki/pipeline/*.md
  purpose: ingest, windowing, artifacts, commands, schema

model:
  path: wiki/model/*.md
  purpose: features, baselines, inference, training rules, risks

decision:
  path: wiki/decisions/*.md
  purpose: durable choices and rejected approaches

open_question:
  path: wiki/open-questions/*.md
  purpose: unresolved research or engineering gap

source_summary:
  path: wiki/sources/*.md
  purpose: compact summary of raw docs, reports, scripts
```

## Frontmatter

Every page should start with:

```yaml
---
type: dataset|pipeline|model|decision|open_question|source_summary|overview|schema|index|log
status: active|draft|stale|superseded
updated: YYYY-MM-DD
---
```

Optional:

```yaml
tags: [pain, stress, baseline, ingest]
source_files:
  - docs/INGEST_PIPELINE.md
  - src/painwatchstandard/windowing.py
```

## Link Rules

Use Obsidian-style links for wiki pages:

```text
[[pipeline/windowing]]
[[model/state-normalization]]
```

Use repo-relative paths for code/docs:

```text
src/painwatchstandard/windowing.py
docs/INGEST_PIPELINE.md
```

## Maintenance Workflow

```yaml
ingest_or_update:
  - read relevant code/docs
  - update topic page
  - update index
  - append log entry
  - mark contradictions/gaps in open questions

query:
  - read wiki/index.md first
  - read linked pages
  - answer from wiki and current code
  - if answer creates durable insight, file it back into wiki

lint:
  - find stale pages
  - find orphan pages
  - find claims contradicted by code
  - find missing dataset/model pages
```

## Hard Rules

```yaml
pain_truth:
  allowed_only_from_explicit_pain_labels: true
  never_from_apple_watch_archetype: true
  never_from_sensor_presence: true

sensor_presence:
  meaning: availability/quality/device signature
  forbidden_meaning: direct positive state evidence

windowing:
  current_default: 1Hz output cadence with 30s trailing memory
  row_meaning: one prediction tick, not one non-overlapping segment

baseline:
  one_global_baseline_departure: rejected
  use: archetype/context-aware medians and robust spreads
```

