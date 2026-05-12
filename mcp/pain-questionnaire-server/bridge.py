from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from tools.questionnaire import continue_dialogue, start_questionnaire, submit_questionnaire_answers


DOCTOR_GROUP_ID = "doctor_a"
DOCTOR_GROUP_NAME = "Doctor A"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class BridgeConfig:
    def __init__(self) -> None:
        load_env_file(Path(__file__).with_name(".env"))
        self.host = os.getenv("PAIN_BRIDGE_HOST", "127.0.0.1")
        self.port = int(os.getenv("PAIN_BRIDGE_PORT", "9020"))
        self.bridge_token = os.getenv("PAIN_BRIDGE_TOKEN", "")
        self.fhir_base_url = os.getenv("PROMPTOPINION_FHIR_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("PROMPTOPINION_API_KEY", "")


CONFIG = BridgeConfig()
INCIDENTS: dict[str, dict[str, Any]] = {}


class PainBridgeHandler(BaseHTTPRequestHandler):
    server_version = "PainThermometerBridge/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(
                {
                    "ok": True,
                    "fhir_configured": bool(CONFIG.fhir_base_url and CONFIG.api_key),
                    "doctor_group_id": DOCTOR_GROUP_ID,
                }
            )
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not_found")

    def do_POST(self) -> None:
        if not self._authorized():
            self._send_error(HTTPStatus.UNAUTHORIZED, "unauthorized")
            return

        try:
            payload = self._read_json()
            if self.path == "/v1/patients":
                self._send_json(handle_create_patient(payload))
            elif self.path == "/v1/pain-trigger":
                self._send_json(handle_pain_trigger(payload))
            elif self.path == "/v1/questionnaire/continue":
                self._send_json(handle_continue_questionnaire(payload))
            elif self.path == "/v1/questionnaire/submit":
                self._send_json(handle_submit_questionnaire(payload))
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found")
        except ValueError as error:
            self._send_error(HTTPStatus.BAD_REQUEST, str(error))
        except HTTPError as error:
            self._send_error(error.code, f"fhir_error:{error.reason}")
        except Exception as error:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"bridge_error:{error}")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self) -> bool:
        if not CONFIG.bridge_token:
            return True
        return self.headers.get("Authorization") == f"Bearer {CONFIG.bridge_token}"

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        decoded = json.loads(body.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("expected_json_object")
        return decoded

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus | int, message: str) -> None:
        self._send_json({"accepted": False, "error": message}, HTTPStatus(status))


def handle_create_patient(payload: dict[str, Any]) -> dict[str, Any]:
    patient = payload.get("patient")
    if not isinstance(patient, dict):
        raise ValueError("missing_patient")

    patient_id = str(patient.get("id") or payload.get("patient_id") or "")
    if not patient_id:
        raise ValueError("missing_patient_id")

    fhir_id = _safe_fhir_id(f"pain-watch-{patient_id}")
    fhir_patient = {
        "resourceType": "Patient",
        "id": fhir_id,
        "identifier": [
            {"system": "urn:painthermometer:patient-id", "value": patient_id},
            {"system": "urn:painthermometer:doctor-group", "value": DOCTOR_GROUP_ID},
        ],
        "name": [
            {
                "use": "usual",
                "family": patient.get("lastName") or patient.get("last_name") or "Patient",
                "given": [patient.get("firstName") or patient.get("first_name") or "Test"],
            }
        ],
        "managingOrganization": {
            "identifier": {"system": "urn:painthermometer:doctor-group", "value": DOCTOR_GROUP_ID},
            "display": DOCTOR_GROUP_NAME,
        },
        "meta": {"source": "PainThermometerWatchApp"},
    }
    fhir_result = fhir_put("Patient", fhir_id, fhir_patient)
    return {
        "accepted": True,
        "patient_id": patient_id,
        "fhir_patient_id": fhir_result.get("id", fhir_id),
        "doctor_group_id": DOCTOR_GROUP_ID,
    }


def handle_pain_trigger(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or "")
    device_id = str(payload.get("device_id") or "")
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    trigger_score = float(score.get("pain_likelihood_0_1") or (score.get("pain_score_0_100") or 0) / 100)
    if not run_id or not device_id:
        raise ValueError("missing_run_or_device")

    local_patient = payload.get("patient") if isinstance(payload.get("patient"), dict) else None
    fhir_patient_id = None
    if local_patient:
        fhir_patient_id = handle_create_patient({"patient": local_patient})["fhir_patient_id"]

    session_result = start_questionnaire(
        run_id=run_id,
        device_id=device_id,
        trigger_score=trigger_score,
        activation_positive_count=int(payload.get("activation_positive_count") or 7),
        activation_window_count=int(payload.get("activation_window_count") or 10),
        pain_scores=score,
        sensor_summary=summarize_buffer(payload.get("buffer")),
    )
    session = session_result["session"]
    incident_id = str(session["session_id"])
    INCIDENTS[incident_id] = {
        "incident_id": incident_id,
        "run_id": run_id,
        "device_id": device_id,
        "patient_id": local_patient.get("id") if local_patient else None,
        "fhir_patient_id": fhir_patient_id,
        "score_history": payload.get("score_history") or [],
        "buffer": payload.get("buffer") or [],
        "created_at": _now(),
    }
    write_incident_observations(incident_id, fhir_patient_id, payload)
    return questionnaire_response(True, session_result, incident_id=incident_id)


def handle_continue_questionnaire(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("questionnaire_session_id") or "")
    response = str(payload.get("response") or "").strip()
    if not session_id or not response:
        raise ValueError("missing_session_or_response")
    result = continue_dialogue(session_id=session_id, response=response)
    if result is None:
        raise ValueError("unknown_questionnaire_session")
    return questionnaire_response(True, result)


def handle_submit_questionnaire(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("questionnaire_session_id") or "")
    if not session_id:
        raise ValueError("missing_questionnaire_session_id")
    transcript = payload.get("transcript") if isinstance(payload.get("transcript"), list) else []
    answers = {"transcript": transcript}
    result = submit_questionnaire_answers(session_id=session_id, answers=answers)
    if result is None:
        raise ValueError("unknown_questionnaire_session")
    completion = completion_fraction(result)
    return {"accepted": True, "completed": completion >= 0.8, "completion_0_1": completion}


def questionnaire_response(accepted: bool, result: dict[str, Any], incident_id: str | None = None) -> dict[str, Any]:
    next_question = result.get("next_question") or "Can you say a little more about what changed?"
    response = {
        "accepted": accepted,
        "questionnaire_session_id": result.get("session", {}).get("session_id"),
        "incident_id": incident_id,
        "question": {
            "id": "agent_followup",
            "text": next_question,
            "input_type": "open_text",
            "target_fields": result.get("missing_fields") or [],
        },
        "next_question": next_question,
        "missing_fields": result.get("missing_fields") or [],
        "completion_0_1": completion_fraction(result),
        "can_submit": completion_fraction(result) >= 0.8,
        "revised_scores": result.get("revised_scores"),
    }
    return response


def completion_fraction(result: dict[str, Any]) -> float:
    missing = result.get("missing_fields") or []
    priority_total = 10
    return max(0.0, min(1.0, (priority_total - len(missing)) / priority_total))


def summarize_buffer(buffer: object) -> dict[str, Any]:
    if not isinstance(buffer, list):
        return {}
    by_sensor: dict[str, list[float]] = {}
    for row in buffer:
        if not isinstance(row, dict):
            continue
        sensor = str(row.get("sensor") or "")
        value = row.get("value")
        if sensor and isinstance(value, int | float):
            by_sensor.setdefault(sensor, []).append(float(value))
    return {
        sensor: {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
        }
        for sensor, values in by_sensor.items()
        if values
    }


def write_incident_observations(incident_id: str, fhir_patient_id: str | None, payload: dict[str, Any]) -> None:
    if not fhir_patient_id:
        return
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    score_value = score.get("pain_score_0_100")
    if isinstance(score_value, int | float):
        observation_id = _safe_fhir_id(f"pain-incident-{incident_id}-score")
        observation = {
            "resourceType": "Observation",
            "id": observation_id,
            "status": "preliminary",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "survey"}]}],
            "code": {"text": "PainThermometer inferred pain score"},
            "subject": {"reference": f"Patient/{fhir_patient_id}"},
            "effectiveDateTime": payload.get("triggered_at") or _now(),
            "valueQuantity": {"value": score_value, "unit": "0-100", "system": "urn:painthermometer", "code": "pain-score"},
            "derivedFrom": [{"display": f"PainThermometer incident {incident_id}"}],
        }
        fhir_put("Observation", observation_id, observation)


def fhir_put(resource_type: str, resource_id: str, resource: dict[str, Any]) -> dict[str, Any]:
    if not CONFIG.fhir_base_url or not CONFIG.api_key:
        return resource
    url = f"{CONFIG.fhir_base_url}/{quote(resource_type)}/{quote(resource_id)}"
    body = json.dumps(resource).encode("utf-8")
    request = Request(url, data=body, method="PUT")
    request.add_header("Accept", "application/fhir+json")
    request.add_header("Content-Type", "application/fhir+json")
    request.add_header("Prefer", "return=representation")
    request.add_header("Authorization", f"Bearer {CONFIG.api_key}")
    with urlopen(request, timeout=20) as response:
        response_body = response.read()
    return json.loads(response_body.decode("utf-8")) if response_body else resource


def _safe_fhir_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-." else "-" for char in value)[:64]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    print(f"Starting PainThermometer bridge at http://{CONFIG.host}:{CONFIG.port}")
    print(f"FHIR configured: {bool(CONFIG.fhir_base_url and CONFIG.api_key)}")
    server = ThreadingHTTPServer((CONFIG.host, CONFIG.port), PainBridgeHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
