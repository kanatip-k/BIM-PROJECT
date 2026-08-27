import json
import os
import httpx
from mcp.server import MCPServer

mcp = MCPServer("navisworks-mcp")
BRIDGE_URL = os.environ.get("NAVIS_BRIDGE_URL", "http://127.0.0.1:8765").rstrip("/")
MAX_LIMIT = 5000

@mcp.tool()
async def get_navisworks_elements(limit: int = 500, offset: int = 0) -> str:
    """Read a page of elements from the local Navisworks JSON bridge."""
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

if __name__ == "__main__":
    mcp.run()
