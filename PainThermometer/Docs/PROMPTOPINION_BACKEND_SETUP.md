# Prompt Opinion Backend Setup

Status: initial integration notes
Date: 2026-05-11

## Docs Read

The public docs expose these relevant pages:

- Getting Started: model configuration, account/workspace, patient, agent,
  conversation, and question flow. Some API examples require authentication.
- Model Configuration: create an LLM config before creating agents.
- A2A V1 Migration: external agent cards now use `supportedInterfaces`; `url`,
  `preferredTransport`, and `capabilities.stateTransitionHistory` were removed.
- Agent Scopes: agents can be Workspace, Patient, or Group scoped.
- BYO Agents: BYO agents can use custom prompts, response JSON schema, MCP
  tools, guardrails, A2A skills, and FHIR context.
- External Agents: external agents are A2A connections discovered through
  `/.well-known/agent-card.json`; they are consulted from a BYO agent chat.
- FHIR Context Overview: Prompt Opinion can pass FHIR server URL, token, and
  patient ID.
- FHIR Context With MCP: MCP servers advertise
  `ai.promptopinion/fhir-context` during `initialize`; Prompt Opinion sends
  `X-FHIR-Server-URL`, `X-FHIR-Access-Token`, and `X-Patient-ID` headers.
- FHIR Context With A2A: A2A agents advertise the FHIR extension at
  `https://app.promptopinion.ai/schemas/a2a/v1/fhir-context` and receive FHIR
  context in message metadata.

## Intended Prompt Opinion Shape

PainThermometer should not send watch sensor buffers directly to the Prompt
Opinion chat UI. The watch app continues to send local/debug payloads to our
own endpoint contract. The Prompt Opinion-facing component is the
`mcp/pain-questionnaire-server`, which exposes tools a BYO agent can call after
a sustained pain trigger has been recorded.

Clinician-facing dashboard access should also be backend-authorized. The React
review surface may display mocked incidents, but patient visibility must come
from Prompt Opinion account/session authorization and the registered FHIR
patient scope. The frontend should ask a backend route for an access decision
and should not infer access from group names or local patient lists.

Recommended setup:

1. Create or choose a Prompt Opinion model configuration.
2. Create a Patient-scoped BYO agent for pain follow-up.
3. Deploy `mcp/pain-questionnaire-server` on an HTTPS URL reachable by Prompt
   Opinion.
4. Register that URL under `Configuration -> MCP Servers`.
5. Authorize the optional FHIR context extension when patient linkage is wanted.
6. Attach the MCP server to the BYO agent tools.

## Dashboard Authorization

Recommended route:

```text
POST /api/promptopinion/authorize-patient-access
```

Request:

```json
{
  "workspace_id": "po_workspace_id",
  "clinician_group_id": "grp_doctor_a",
  "patient_id": "pat_test",
  "requested_scope": "patient.read",
  "fhir_resource": "Patient/pat_test"
}
```

Response:

```json
{
  "allowed": true,
  "requestId": "authz_req_a_204",
  "checkedAt": "2026-05-11T16:51:04Z",
  "fhirPatientId": "pat_test",
  "policy": "registered_fhir_patient_scope"
}
```

Denied responses should return `allowed: false` with a non-sensitive reason.
The UI can show a generic no-access state and put the request ID/rejection
reason behind an information control for debugging.

The backend implementation should validate the logged-in Prompt Opinion
clinician, resolve group membership, and check the registered FHIR patient scope
before returning any patient, incident, survey, score, or transcript data.

## MCP Server Contract

Server URL:

```text
https://<deployment-host>/mcp
```

The server declares the MCP extension:

```json
{
  "ai.promptopinion/fhir-context": {
    "scopes": [
      { "name": "patient/Patient.rs", "required": false },
      { "name": "patient/Observation.rs", "required": false },
      { "name": "patient/Observation.cu", "required": false },
      { "name": "patient/QuestionnaireResponse.rs", "required": false },
      { "name": "patient/QuestionnaireResponse.cu", "required": false }
    ]
  }
}
```

Prompt Opinion may send these headers on tool calls:

```text
X-FHIR-Server-URL: https://app.promptopinion.ai/api/workspaces/<id>/fhir
X-FHIR-Access-Token: <token>
X-Patient-ID: <patient-id>
```

Current tools:

- `start_questionnaire`: creates a pain follow-up session from a watch trigger.
- `get_questionnaire`: reads active state, questions, missing fields, and score
  revisions.
- `submit_questionnaire_answers`: accepts structured answers and can complete a
  session.
- `continue_dialogue`: accepts free testimony and returns the next highest-value
  follow-up.

## Watch-To-Backend Bridge

The watch app already has a generic endpoint contract:

- `POST /v1/connect`
- `POST /v1/live-samples`
- `POST /v1/runs/import-jsonl`
- `POST /v1/pain-trigger`

For Prompt Opinion integration, `/v1/pain-trigger` should be implemented by a
bridge service that stores the 100-sample buffer and then calls the MCP
`start_questionnaire` tool or makes the same data available to the BYO agent.
The watch app should remain endpoint-agnostic and only require a base URL and
bearer token for the bridge.

## Current Gaps

- The watch app intentionally does not notify the MCP bridge yet; pain trigger
  payloads are built locally and discarded while device testing continues.
- Questionnaire sessions are in memory and need durable storage before remote
  use.
- FHIR write-back for Observation and QuestionnaireResponse is scoped but not
  implemented yet.
- Authenticated Prompt Opinion API examples in Getting Started were blocked in
  the public docs; actual workspace, patient, agent, and conversation API calls
  still need live credentials or copied examples from the PDF/export.
