# PainThermometer - Watch Pain Detection + Questionnaire MCP Server

> **Wearable AI for detecting sustained pain-like patterns from Apple Watch sensor streams, then turning the event into a Prompt Opinion MCP-guided clinical follow-up.**  
> Built for the **Agents Assemble Hackathon 2026**.

[![MCP Server](https://img.shields.io/badge/MCP-Prompt%20Opinion-green)](https://app.promptopinion.ai/marketplace)
[![FHIR Context](https://img.shields.io/badge/FHIR-Context%20Ready-blue)](mcp/pain-questionnaire-server/README.md)
[![Apple Watch](https://img.shields.io/badge/Apple%20Watch-CoreML-black)](PainThermometer/)
[![Dashboard](https://img.shields.io/badge/Dashboard-React%20%2B%20HeroUI-purple)](promptopinion-dashboard-mock/)

---

## Live Test Interface

This repo includes a local clinician dashboard mock and a local MCP server:

```bash
# Clinician review dashboard
cd promptopinion-dashboard-mock
npm install
npm run dev
```

```bash
# Prompt Opinion questionnaire MCP server
cd mcp/po-fastmcp
uv sync
cd ../pain-questionnaire-server
../po-fastmcp/.venv/bin/python main.py
```

MCP endpoint:

```text
http://127.0.0.1:9010/mcp
```

Deploy the MCP server behind HTTPS before registering it in Prompt Opinion.

---

## What It Does

**PainThermometer is a watch-to-agent pain workflow.**  
Instead of waiting for patients to remember pain episodes later, the watch scores short sensor windows, watches for sustained activation, and then triggers a structured MCP questionnaire that a Prompt Opinion agent can use immediately.

### Core Pipeline

```text
Apple Watch Sensors
    ↓
30-second Window Features
    ↓
Phase 3 Multitask Model
    ↓
Pain Likelihood + 0-100 Score + Confidence
    ↓
7-of-10 Sustained Activation Check
    ↓
MCP Questionnaire Session
    ↓
GPM-Style Follow-Up + Open Testimony
    ↓
Prompt Opinion FHIR Context
    ↓
Clinician Review Dashboard
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `start_questionnaire` | Starts a pain follow-up session from a sustained watch activation |
| `get_questionnaire` | Returns active questionnaire state, questions, missing fields, and revised scores |
| `submit_questionnaire_answers` | Stores structured answers and completes the session when priority fields are covered |
| `continue_dialogue` | Adds open patient testimony and returns the next highest-value follow-up question |

The first question is intentionally simple:

```text
What happened around when the pain started?
```

The follow-up logic prioritizes location, quality, activity context, 0-10 pain scores, sleep, fatigue, help needed, and mood.

---

## Watch Scoring Outputs

Each scored feature row returns an agent- and UI-ready payload:

| Output | Meaning |
|--------|---------|
| `pain_likelihood_0_1` | Probability of a high-pain pattern |
| `pain_score_0_100` | Normalized pain score for display |
| `pain_flag` | Sustained pain-like pattern after rolling-window logic |
| `confidence_0_1` | Confidence after sensor quality and model distance checks |
| `quality_0_1` | Sensor coverage quality score |
| `stress_likelihood_0_1` | Companion stress estimate |
| `baseline_departure_0_1` | How far the window is from baseline state |
| `pain_blocks_10` | Ten-block rolling strip for the watch UI |

Activation mode is based on sustained evidence: **7 positive windows out of the last 10**.

---

## Wearable + Agent Architecture

PainThermometer combines three layers:

**Sensor Layer:** Apple Watch motion, heart-rate, temperature, oxygen, BVP, EDA, IBI, and related availability signals.  
**Model Layer:** A frozen Phase 3 multitask model that estimates pain, stress, and baseline departure from windowed features.  
**Agent Layer:** A Prompt Opinion MCP server that turns a pain trigger into a guided clinical questionnaire.

```text
Rule 1 - Sensor Quality:      Are enough signal blocks present to trust the window?
Rule 2 - Pain Activation:     Are enough recent windows positive to trigger follow-up?
Rule 3 - Questionnaire Gap:   Which clinical field is still missing or low-certainty?
```

This makes the workflow explainable enough for review: not just a pain score, but the sensor quality, rolling activation state, missing fields, and patient testimony behind it.

---

## SHARP / FHIR Context

The questionnaire MCP server declares Prompt Opinion FHIR context support during initialization.

Headers read automatically:

| Header | Purpose |
|--------|---------|
| `X-FHIR-Server-URL` | Base URL for the active FHIR server |
| `X-FHIR-Access-Token` | Bearer token for FHIR access |
| `X-Patient-ID` | Current patient FHIR ID |

FHIR scopes advertised:

```text
patient/Patient.rs
patient/Observation.rs
patient/Observation.cu
patient/QuestionnaireResponse.rs
patient/QuestionnaireResponse.cu
```

The current MCP server captures FHIR context in the session payload. Durable FHIR write-back is scoped but not yet implemented.

---

## Quick Start

### 1. Run the MCP Server

```bash
cd mcp/po-fastmcp
uv sync
cd ../pain-questionnaire-server
../po-fastmcp/.venv/bin/python main.py
```

Server:

```text
http://127.0.0.1:9010/mcp
```

Optional environment:

```bash
export PAIN_MCP_HOST=0.0.0.0
export PAIN_MCP_PORT=9010
```

Use `0.0.0.0` only when exposing the service through a secure HTTPS deployment.

### 2. Run the Dashboard Mock

```bash
cd promptopinion-dashboard-mock
npm install
npm run dev
```

The dashboard models a clinician review flow with patient access checks, pain incidents, watch activation data, survey answers, adjusted scores, and transcript summaries.

### 3. Score a Feature Row

```bash
python3 inference_flow/inference.py path/to/feature-row.json
```

Default model:

```text
inference_flow/models/pain-thermometer-phase3-final-v1/model.joblib
```

---

## MCP Server Endpoint

```text
URL: https://<deployment-host>/mcp
Transport: Streamable HTTP
Auth: Deployment-specific
```

Register in Prompt Opinion:

1. Deploy `mcp/pain-questionnaire-server` on a public HTTPS URL.
2. Open Prompt Opinion -> Configuration -> MCP Servers.
3. Add the `/mcp` endpoint.
4. Enable optional FHIR context if the questionnaire should attach to the active patient.
5. Attach the MCP server to a patient-scoped BYO agent.

---

## Project Structure

```text
pain datasets/
│
├── Watch App
│   ├── PainThermometer/
│   └── PainThermometer/Docs/
│
├── MCP + Prompt Opinion
│   ├── mcp/pain-questionnaire-server/
│   └── mcp/po-fastmcp/
│
├── Model Inference
│   ├── inference_flow/inference.py
│   ├── inference_flow/train_final_model.py
│   └── inference_flow/models/pain-thermometer-phase3-final-v1/
│
├── Dashboard
│   └── promptopinion-dashboard-mock/
│
├── Dataset + Feeder Pipeline
│   ├── pain_normalizer.py
│   ├── pain_feeder.py
│   ├── pain_all_dataset_feeder.py
│   ├── pain_self_supervised.py
│   └── pain_supervised_baseline.py
│
├── Exploration
│   └── pain-thermometer-exploration/
│
└── Exports
    └── _exports/
```

---

## Testing End-to-End

### Watch-to-Agent Flow

1. Record watch sensor windows.
2. Score each window with the Phase 3 model.
3. Trigger pain-detected mode when 7 of the last 10 windows are positive.
4. Start the MCP questionnaire with `start_questionnaire`.
5. Continue the dialogue until high-priority fields are captured.
6. Review the event, scores, transcript, and questionnaire output in the dashboard.

### Developer Flow

```bash
# Run questionnaire MCP
cd mcp/po-fastmcp && uv sync
cd ../pain-questionnaire-server
../po-fastmcp/.venv/bin/python main.py
```

```bash
# Run inference smoke test
python3 inference_flow/smoke_test.py
```

```bash
# Run feeder tests
python3 -m pytest test_pain_feeder.py
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Watch App | SwiftUI + watchOS |
| Local Inference | Core ML model artifacts |
| Server Inference | Python + scikit-learn/joblib |
| Feature Pipeline | Pandas + parquet window features |
| MCP Framework | FastMCP + Prompt Opinion wrapper |
| FHIR Context | Prompt Opinion MCP FHIR headers |
| Dashboard | React + TypeScript + Vite + HeroUI |
| Deployment Target | HTTPS MCP server + Prompt Opinion BYO agent |

---

## Current Status

- Apple Watch app records and displays rolling pain activation state.
- Phase 3 frozen inference artifact is checked in as `pain-thermometer-phase3-final-v1`.
- MCP questionnaire server exposes four Prompt Opinion tools.
- FHIR context is declared and captured by the MCP server.
- Clinician dashboard mock shows patient authorization and incident review flows.
- Durable session storage, production FHIR write-back, and deployed public endpoint remain next steps.

---

## Future Enhancements

- **FHIR Write-Back** - Create Observation and QuestionnaireResponse resources.
- **Persistent Sessions** - Store questionnaire sessions by run, device, and trigger time.
- **Watch Trigger Bridge** - Add `/v1/pain-trigger` backend integration from the watch app.
- **Clinician Feedback Loop** - Use reviewed incidents to improve thresholding and calibration.
- **Production AuthZ** - Enforce Prompt Opinion group-to-patient access before returning incident data.
- **Core ML Packaging** - Keep the watch model bundle aligned with the frozen server artifact.

---

## Hackathon

**Agents Assemble Healthcare AI Challenge 2026**  
Organized by: Prompt Opinion

**Unique value:** A wearable pain-detection workflow that connects sensor evidence to an agent-led clinical questionnaire. It does not stop at a model score; it asks the patient what happened, fills the missing clinical fields, and packages the episode for clinician review.

---

## Disclaimer

This project is for **research and demonstration purposes only**. The model output and questionnaire responses are not medical advice and must be reviewed by qualified clinicians before any clinical use. Not approved for diagnosis, treatment, or patient monitoring.

---

*Powered by Apple Watch + MCP + FHIR + Prompt Opinion*
