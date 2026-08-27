import json
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Navisworks MCP Dashboard")

async def call_mcp_tool():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(BASE_DIR / "mcp_server.py")],
        env=None,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_navisworks_elements",
                arguments={"limit": 1000},
            )

    text_parts = []
    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            text_parts.append(text)

    if not text_parts:
        return {"error": "MCP returned no text content", "elements": []}

    return json.loads("\n".join(text_parts))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )

@app.get("/api/model")
async def model_data():
    try:
        data = await call_mcp_tool()
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse(
            {"error": str(exc), "elements": [], "source": "MCP"},
            status_code=500,
        )
