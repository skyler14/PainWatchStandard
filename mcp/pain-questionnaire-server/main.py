from pathlib import Path
import sys

PO_FASTMCP_ROOT = Path(__file__).resolve().parents[1] / "po-fastmcp"
sys.path.append(str(PO_FASTMCP_ROOT))

from po_fastmcp import POFastMCP
from tools.questionnaire import register_tools

mcp = POFastMCP(
    name="PainThermometer Questionnaire MCP",
    instructions=(
        "Administers a short chronic-pain questionnaire when a watch session "
        "reports sustained pain activation."
    ),
    fhir_scopes=[],
)

register_tools(mcp)


def main() -> None:
    print("Starting questionnaire MCP server at http://127.0.0.1:9010/mcp")
    mcp.run(transport="http", host="127.0.0.1", port=9010)


if __name__ == "__main__":
    main()
