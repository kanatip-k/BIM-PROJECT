"""Executable integration probe for REST and stdio MCP surfaces."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
PYTHON_APP = ROOT / "python_app"
sys.path.insert(0, str(PYTHON_APP))


def make_snapshot() -> Path:
    source = json.loads(
        (ROOT / "tests" / "fixtures" / "case2_real_samples.json").read_text(encoding="utf-8")
    )
    samples = [item for item in source["samples"] if item["sourceFile"] == "CASE2_AR.json"]
    snapshot = {
        "modelName": samples[0]["modelName"],
        "snapshotUtc": "2026-09-29T00:00:00Z",
        "source": "integration-probe",
        "elementCount": len(samples),
        "elements": [item["element"] for item in samples],
    }
    path = ROOT / "tests" / "integration_snapshot.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    return path


async def main() -> None:
    snapshot = make_snapshot()
    os.environ["NAVIS_JSON_PATH"] = str(snapshot)
    os.environ["BOQ_RESULT_DIR"] = str(ROOT / "tests" / "integration_results")
    os.environ["PYTHONPATH"] = str(PYTHON_APP)

    from web_app import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        options = await client.get("/api/boq/options")
        assert options.status_code == 200
        response = await client.post(
            "/api/boq/run", json={"disciplines": ["Architecture"]}
        )
        assert response.status_code == 200, response.text
        result = response.json()
        csv_response = await client.get(f"/api/boq/{result['jobId']}/export.csv")
        assert csv_response.status_code == 200
        assert csv_response.text.startswith("discipline,elementCode")
        agent = await client.post(
            "/api/agent/chat",
            json={"message": "อธิบายโมเดล", "disciplines": ["Architecture"]},
        )
        assert agent.status_code == 200

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(PYTHON_APP / "mcp_server.py")],
        env=dict(os.environ),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {"get_navisworks_elements", "run_boq_workflow",
                    "get_boq_workflow_result", "list_boq_workflows"} <= names
            mcp_result = await session.call_tool(
                "run_boq_workflow", arguments={"disciplines": ["Architecture"]}
            )
            result_text = "\n".join(
                item.text for item in mcp_result.content if getattr(item, "text", None)
            )
            assert json.loads(result_text)["summary"]["lineCount"] > 0

    print(json.dumps({
        "restStatus": result["status"],
        "restLineCount": result["summary"]["lineCount"],
        "mcpTools": sorted(names),
        "csvBytes": len(csv_response.content),
    }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
