# PainThermometer Questionnaire MCP

This is the parent-repo wrapper around the `mcp/po-fastmcp` submodule. It starts
a small MCP server for a conversational questionnaire that can be triggered
after a watch session reaches sustained pain activation.

## Run

```shell
cd mcp/po-fastmcp
uv sync
cd ../pain-questionnaire-server
../po-fastmcp/.venv/bin/python main.py
```

The server listens at:

```text
http://127.0.0.1:9010/mcp
```

Set `PAIN_MCP_HOST=0.0.0.0` and expose the service over HTTPS when registering
it from the Prompt Opinion web app. Keep `127.0.0.1` for local-only testing.

## Tools

- `start_questionnaire`: called when the app has a sustained pain activation,
  normally 7 positive windows out of the last 10. It accepts the trigger score,
  optional score details, and an optional sensor summary.
- `get_questionnaire`: returns active questionnaire state and item definitions.
- `submit_questionnaire_answers`: stores answers and marks the questionnaire
  session complete when no high-priority fields are missing.
- `continue_dialogue`: adds open testimony and returns the next natural
  follow-up question.

This PoC keeps questionnaire sessions in memory. A production version should
persist sessions keyed by `run_id`, `device_id`, and trigger timestamp.

## Prompt Opinion Registration

1. Deploy the server so the Prompt Opinion backend can reach `/mcp`.
2. In Prompt Opinion, go to `Configuration -> MCP Servers` and add the public
   MCP URL.
3. Continue through the initialize step. The server declares
   `ai.promptopinion/fhir-context` with optional Patient, Observation, and
   QuestionnaireResponse scopes.
4. Enable FHIR context if this questionnaire should attach output to the active
   patient. Prompt Opinion will pass `X-FHIR-Server-URL`,
   `X-FHIR-Access-Token`, and `X-Patient-ID` headers on tool calls.
5. Attach this MCP server to the BYO agent that will conduct the pain follow-up
   dialogue.

The dialogue starts with “What happened around when the pain started?” and then
prioritizes missing or low-certainty GPM-style fields such as pain location,
quality, current 0-10 score, weekly average score, sleep, fatigue, help needed,
and mood.
