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

The dialogue starts with “What happened around when the pain started?” and then
prioritizes missing or low-certainty GPM-style fields such as pain location,
quality, current 0-10 score, weekly average score, sleep, fatigue, help needed,
and mood.
