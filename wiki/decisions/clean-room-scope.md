---
type: decision
status: active
updated: 2026-06-08
tags: [scope, clean-room]
---

# Clean Room Scope

Decision:

```yaml
keep:
  - ingest code
  - feature/window code
  - baseline/inference contracts
  - tests
  - docs/wiki

ignore:
  - mobile app
  - old UI
  - unrelated app code
  - raw archives inside repo
```

Reason:

```yaml
goal: clean next-gen core that can later feed app/device code
avoid: carrying old model/UI assumptions into new training stack
```

