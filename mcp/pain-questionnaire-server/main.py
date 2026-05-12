from pathlib import Path
import os
import sys

PO_FASTMCP_ROOT = Path(__file__).resolve().parents[1] / "po-fastmcp"
sys.path.append(str(PO_FASTMCP_ROOT))

from po_fastmcp import POFastMCP
from tools.questionnaire import register_tools

FHIR_SCOPES = [
    {"name": "patient/Patient.rs", "required": False},
    {"name": "patient/Observation.rs", "required": False},
    {"name": "patient/Observation.cu", "required": False},
    {"name": "patient/QuestionnaireResponse.rs", "required": False},
    {"name": "patient/QuestionnaireResponse.cu", "required": False},
]

mcp = POFastMCP(
    name="PainThermometer Questionnaire MCP",
    instructions=(
        "Administers a short chronic-pain questionnaire when a watch session "
        "reports sustained pain activation. Uses Prompt Opinion FHIR context "
        "when provided to associate testimony, scores, and observations with "
        "the active patient."
    ),
    fhir_scopes=FHIR_SCOPES,
)

register_tools(mcp)


def main() -> None:
    host = os.getenv("PAIN_MCP_HOST", "127.0.0.1")
    port = int(os.getenv("PAIN_MCP_PORT", "9010"))
    print(f"Starting questionnaire MCP server at http://{host}:{port}/mcp")
    mcp.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
