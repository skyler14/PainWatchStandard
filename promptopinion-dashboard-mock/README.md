# Prompt Opinion Dashboard Mock

This is a small HeroUI v3 React mock for the clinician-facing review surface.
It models the backend organization we want for watch pain notifications:

```text
Group "Doctor A"
  Clinician "Doctor A"
  Patient "Test Patient"
    PainIncident
      activation window and trigger score
      100-sample watch buffer summaries
      completed GPM-style survey
      adjusted scores
      interview transcript
      service summaries
```

Run locally:

```shell
npm install
npm run dev
```

The current incident is mocked. The `Summarize` button rotates through canned
service summaries to show where a backend summary call would attach.

## Auth Boundary

The UI does not decide patient access directly. Group selection calls the local
backend/proxy route:

```text
POST /api/promptopinion/authorize-patient-access
```

Expected request:

```json
{
  "workspace_id": "po_workspace_id",
  "clinician_group_id": "grp_doctor_a",
  "patient_id": "pat_test",
  "requested_scope": "patient.read",
  "fhir_resource": "Patient/pat_test"
}
```

Expected response:

```json
{
  "allowed": false,
  "reason": "permission_denied: clinician group is not assigned to patient pat_test",
  "requestId": "authz_req_b_403",
  "checkedAt": "2026-05-11T16:51:04Z",
  "fhirPatientId": "pat_test",
  "policy": "registered_fhir_patient_scope"
}
```

That backend route should use the Prompt Opinion account/session and registered
FHIR system to enforce group-to-patient access. The local React app only hides
or shows data based on the backend decision. If the endpoint is unavailable in
local development, the app uses a clearly labeled local fallback so the screen
can still be reviewed.

For local development, put secrets only in `.env.local`:

```text
VITE_PROMPTOPINION_WORKSPACE_ID=...
PROMPTOPINION_AUTHZ_ENDPOINT=https://...
PROMPTOPINION_API_KEY=...
```

Only `VITE_PROMPTOPINION_WORKSPACE_ID` is exposed to browser code. The API key
stays server-side inside the Vite dev proxy.
