import json
import os
from pathlib import Path

import httpx
from mcp.server import MCPServer

from boq_workflow import get_workflow, list_workflows, run_boq_workflow as execute_boq_workflow

mcp = MCPServer("navisworks-mcp")
BRIDGE_URL = os.environ.get("NAVIS_BRIDGE_URL", "http://127.0.0.1:8765").rstrip("/")
MAX_LIMIT = 5000
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "data" / "export"


def _json_path() -> Path:
    configured = os.environ.get("NAVIS_JSON_PATH")
    if configured:
        return Path(configured)
    candidates = sorted(
        (path for path in EXPORT_DIR.glob("*.json") if not path.name.endswith(".status.json")),
        key=lambda path: (
            path.name.casefold().endswith(".boq.json"),
            path.stat().st_mtime,
        ),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No Navisworks JSON export found in data/export")
    return candidates[0]


@mcp.tool()
async def get_health() -> str:
    """Check that the JSON Bridge is reachable and report basic model stats (element count, model name)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BRIDGE_URL}/health")
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)


@mcp.tool()
async def get_navisworks_elements(limit: int = 500, offset: int = 0) -> str:
    """Read a page of raw elements from the local Navisworks JSON bridge. Use only for small,
    already-narrowed slices — for a full-model quantity takeoff use get_category_type_summary."""
    safe_limit = max(1, min(limit, MAX_LIMIT))
    safe_offset = max(0, offset)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(
            f"{BRIDGE_URL}/api/elements",
            params={"limit": safe_limit, "offset": safe_offset},
        )
        response.raise_for_status()
        payload = response.json()

    elements = payload.get("elements", [])
    payload["elements"] = elements[:safe_limit]
    payload["returnedCount"] = len(payload["elements"])
    payload["offset"] = safe_offset
    payload["transport"] = "Headless JSON -> JSON Bridge -> MCP Tool"

    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
async def get_category_type_summary() -> str:
    """Aggregate the WHOLE model in one call: element count grouped by (Element.Category,
    Element.Type). This is the tool to use for a full quantity takeoff / Uniformat
    classification — it covers every element without pagination or per-item property reads.
    Also reports elementsWithoutCategory: elements the Navisworks exporter captured that carry
    no Element.Category (e.g. raw geometry/material fragments) and are therefore excluded from
    the groups — a large value here usually means the export needs to run with the fixed
    NavisHeadlessExporterPlugin (selects Element-level nodes, not just HasGeometry nodes)."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(f"{BRIDGE_URL}/api/summary")
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)


@mcp.tool()
def run_boq_workflow(disciplines: list[str] | None = None) -> str:
    """Run the versioned deterministic BIM-to-BOQ workflow on the selected snapshot.

    The agent chooses when to invoke this tool. Engineering classification,
    quantities, issues and demo pricing are calculated outside the LLM.
    """
    result = execute_boq_workflow(_json_path(), disciplines)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_boq_workflow_result(job_id: str) -> str:
    """Return one persisted BOQ workflow result by job id."""
    result = get_workflow(job_id)
    if result is None:
        return json.dumps({"error": "BOQ workflow not found", "jobId": job_id})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def list_boq_workflows(limit: int = 20) -> str:
    """List recent persisted BOQ workflow runs."""
    return json.dumps({"workflows": list_workflows(limit)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
