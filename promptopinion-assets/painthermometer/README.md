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

After the server is attached to the current BYO agent, PromptOpinion exposes it through this agent-specific MCP proxy:

```text
https://app.promptopinion.ai/api/workspaces/019e0f28-64cc-7b65-b713-2ea3cb1a3756/ai-agents/019e1e5e-3d9a-71aa-8951-c890499ca9a8/mcp
```

I verified that proxy initializes and lists the PainThermometer tools. Direct MCP testing against the proxy is sessionful: call `initialize` first, capture the `Mcp-Session-Id` response header, then include that header for `tools/list` and `tools/call`.

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
3. Name or reference the MCP server as `PainThermometer`. This is the invocation name the prompt expects.
4. Use `byo-agent-system-prompt.md` as the system prompt. It includes the exact tool names and GPM question content.
5. In the `Tools` tab, attach the `PainThermometer` MCP server.
6. In the `Response Format` tab, use `response-schema.json` if you want strict JSON summaries.
7. In the `A2A & Skills` tab, add the skill metadata from `skill-card.json`.

## Invocation Names

MCP server invocation/display name:

```text
PainThermometer
```

Exact tool names the agent should call:

```text
list_patients
summarize_patient_history
compute_pain_score
start_questionnaire
get_questionnaire
continue_dialogue
submit_questionnaire_answers
```

Common user phrases and intended tool calls:

| User/clinician phrase | Tool |
| --- | --- |
| "show actual patients" | `list_patients` |
| "summarize this patient" | `summarize_patient_history` |
| "compute pain" | `compute_pain_score` |
| "recompute pain for this session" | `compute_pain_score` |
| "start the questionnaire" | `start_questionnaire` |
| patient answers a question | `continue_dialogue` |
| "submit the survey" | `submit_questionnaire_answers` |

Default clinician group:

```text
grp_doctor_a
```

## Expected Agent Behaviors

- If the clinician asks "show patients", call `list_patients`.
- If the clinician asks "summarize this patient", call `summarize_patient_history`.
- If the clinician asks "compute pain", "recompute pain", "rescore pain", or similar, call `compute_pain_score`.
- During a watch pain incident, use `start_questionnaire` or `continue_dialogue` to guide the Geriatric Pain Measure follow-up.
- Ask broad, natural questions that fill multiple missing GPM fields at once.
- Once `can_submit` is true, tell the user that the survey is ready to submit.

The GPM content is not optional. The agent prompt includes the actual question fields:

- activity/function: vigorous activity, moderate activity, groceries, stairs, few steps, walking more than one block, walking one block or less, bathing/dressing
- activity limitation: reduced time, accomplishing less, limited kind of activities, extra effort
- sleep/social/support/mood: sleep trouble, religious activity, social/recreation, transportation, fatigue, help needed, sadness/depression
- severity: pain today 0-10, average pain last seven days 0-10
- chronicity/frequency: never goes away, daily pain, several times per week

## Smoke Tests

`smoke-tests.md` contains raw JSON-RPC calls you can run against the deployed MCP endpoint. They do not require an API key.

## Related Repo Files

- Live Firebase functions: `functions/index.js`
- Existing manifest: `mcp/pain-questionnaire-server/promptopinion.skill.json`
- Watch app endpoint client: `PainThermometer/PainThermometerWatchApp/UploadClient.swift`
- Dashboard: `promptopinion-dashboard-mock/src/main.tsx`
