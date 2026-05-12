# PainThermometer PromptOpinion Install Package

This folder contains the assets to add the live PainThermometer MCP server and a patient-scoped BYO agent to PromptOpinion.

Direct account installation was not available from the public docs or local CLI. PromptOpinion documents MCP registration as a web-app flow under `Configuration -> MCP Servers`, followed by attaching the server under a BYO Agent's `Tools` tab. Use the files in this folder as the install payload.

## Live MCP Server

Use this in PromptOpinion's "Configure MCP Server" form:

```text
Friendly Name: PainThermometer
Endpoint: https://pain-thermometer-po.web.app/mcp
Transport Type: Streamable HTTP
Authentication Type: None
```

After clicking `Continue`, PromptOpinion should send `initialize` to the server. The server advertises the PromptOpinion FHIR context extension and these optional scopes:

```text
patient/Patient.rs
patient/Observation.rs
patient/Observation.cu
patient/QuestionnaireResponse.rs
patient/QuestionnaireResponse.cu
```

Enable/trust the FHIR context extension so tool calls receive:

```text
X-FHIR-Server-URL
X-FHIR-Access-Token
X-Patient-ID
```

## Attach to a BYO Agent

1. Open `Agents -> BYO Agents`.
2. Create or edit a patient-scoped agent.
3. Use `byo-agent-system-prompt.md` as the system prompt.
4. In the `Tools` tab, attach the `PainThermometer` MCP server.
5. In the `Response Format` tab, use `response-schema.json` if you want strict JSON summaries.
6. In the `A2A & Skills` tab, add the skill metadata from `skill-card.json`.

## Expected Agent Behaviors

- If the clinician asks "show patients", call `list_patients`.
- If the clinician asks "summarize this patient", call `summarize_patient_history`.
- If the clinician asks "compute pain", "recompute pain", "rescore pain", or similar, call `compute_pain_score`.
- During a watch pain incident, use `start_questionnaire` or `continue_dialogue` to guide the Geriatric Pain Measure follow-up.
- Ask broad, natural questions that fill multiple missing GPM fields at once.
- Once `can_submit` is true, tell the user that the survey is ready to submit.

## Smoke Tests

`smoke-tests.md` contains raw JSON-RPC calls you can run against the deployed MCP endpoint. They do not require an API key.

## Related Repo Files

- Live Firebase functions: `functions/index.js`
- Existing manifest: `mcp/pain-questionnaire-server/promptopinion.skill.json`
- Watch app endpoint client: `PainThermometer/PainThermometerWatchApp/UploadClient.swift`
- Dashboard: `promptopinion-dashboard-mock/src/main.tsx`
