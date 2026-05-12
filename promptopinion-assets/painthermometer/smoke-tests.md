# PainThermometer MCP Smoke Tests

These calls should work without an API key because the MCP server is configured with no PromptOpinion-side password/auth header.

## PromptOpinion Agent Proxy

The currently attached BYO agent exposes a PromptOpinion MCP proxy here:

```text
https://app.promptopinion.ai/api/workspaces/019e0f28-64cc-7b65-b713-2ea3cb1a3756/ai-agents/019e1e5e-3d9a-71aa-8951-c890499ca9a8/mcp
```

That proxy is sessionful. Start with `initialize`, then copy the `Mcp-Session-Id` response header into subsequent requests.

```bash
curl -i -sS \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"init","method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"painthermometer-smoke","version":"1.0"}}}' \
  https://app.promptopinion.ai/api/workspaces/019e0f28-64cc-7b65-b713-2ea3cb1a3756/ai-agents/019e1e5e-3d9a-71aa-8951-c890499ca9a8/mcp
```

Then:

```bash
curl -fsSL \
  -H 'Content-Type: application/json' \
  -H 'Mcp-Session-Id: <session id from initialize response header>' \
  -d '{"jsonrpc":"2.0","id":"tools","method":"tools/list","params":{}}' \
  https://app.promptopinion.ai/api/workspaces/019e0f28-64cc-7b65-b713-2ea3cb1a3756/ai-agents/019e1e5e-3d9a-71aa-8951-c890499ca9a8/mcp
```

## Tools List

```bash
curl -fsSL \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"tools","method":"tools/list","params":{}}' \
  https://pain-thermometer-po.web.app/mcp
```

## List Doctor A Patients

```bash
curl -fsSL \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"patients","method":"tools/call","params":{"name":"list_patients","arguments":{"clinician_group_id":"grp_doctor_a"}}}' \
  https://pain-thermometer-po.web.app/mcp
```

## Summarize a Patient

Replace `PATIENT_ID` with an id from `list_patients`.

```bash
curl -fsSL \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"summary","method":"tools/call","params":{"name":"summarize_patient_history","arguments":{"clinician_group_id":"grp_doctor_a","patient_id":"PATIENT_ID"}}}' \
  https://pain-thermometer-po.web.app/mcp
```

## Recompute Pain

Replace `PATIENT_ID` and `SESSION_ID` with values from the registry/dashboard.

```bash
curl -fsSL \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"score","method":"tools/call","params":{"name":"compute_pain_score","arguments":{"clinician_group_id":"grp_doctor_a","patient_id":"PATIENT_ID","session_id":"SESSION_ID"}}}' \
  https://pain-thermometer-po.web.app/mcp
```

## Continue Questionnaire

```bash
curl -fsSL \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"continue","method":"tools/call","params":{"name":"continue_dialogue","arguments":{"session_id":"manual-smoke-session","response_text":"My left knee started hurting sharply when I stood up. It was about seven out of ten and made stairs and sleep harder."}}}' \
  https://pain-thermometer-po.web.app/mcp
```
