import json
import httpx
from mcp.server import MCPServer

mcp = MCPServer("navisworks-mcp")
BRIDGE_URL = "http://127.0.0.1:8765"

@mcp.tool()
async def get_navisworks_elements(limit: int = 500) -> str:
    """Read Navisworks model elements from the local Navisworks bridge."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{BRIDGE_URL}/api/elements")
        response.raise_for_status()
        payload = response.json()

    elements = payload.get("elements", [])
    payload["elements"] = elements[:max(1, min(limit, 5000))]
    payload["returnedCount"] = len(payload["elements"])
    payload["transport"] = "Navisworks Bridge -> MCP Tool"

    return json.dumps(payload, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
