from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

from agent import handle_agent_request
from boq_workflow import (
    export_workflow_csv,
    get_workflow,
    list_workflows,
    run_boq_workflow_from_payload,
)
from boq_workflow.configuration import load_bundle
from json_bridge import store

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Navisworks Agentic BOQ Dashboard", version="0.2.0")


class BoqRequest(BaseModel):
    disciplines: list[str] | None = Field(default=None)


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    disciplines: list[str] | None = Field(default=None)
    model: str | None = Field(default=None)
    max_steps: int | None = Field(default=None)


class WorkflowRequest(BoqRequest):
    model: str | None = Field(default=None)


def _raw_elements() -> list[dict[str, Any]]:
    return store.ensure_loaded().get("elements") or []


def _prop(element: dict[str, Any], *keys: str) -> str:
    props = element.get("properties") or {}
    for key in keys:
        value = props.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _typed_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    match = re.search(r"(?:Double(?:Area|Volume|Length)?):(-?[\d.eE+]+)", str(value))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _measures(element: dict[str, Any]) -> dict[str, float | None]:
    return {
        "area": _typed_number(_prop(element, "Element.Area", "Wall.Area", "Element Properties.Area")),
        "volume": _typed_number(_prop(element, "Element.Volume", "Wall.Volume", "Element Properties.Volume")),
        "length": _typed_number(_prop(element, "Element.Length", "Wall.Length", "GeometryCurve.Length")),
    }


def _compat_element(element: dict[str, Any], rowid: int) -> dict[str, Any]:
    props = element.get("properties") or {}
    return {
        "rowid": rowid,
        "id": element.get("id") or "",
        "displayName": element.get("displayName") or element.get("display_name") or "",
        "className": element.get("classDisplayName") or element.get("class_name") or "",
        "uniformatCode": element.get("uniformatCode") or element.get("uniformat_code") or "",
        "uniformatTitle": element.get("uniformatTitle") or element.get("uniformat_title") or "",
        "hasGeometry": bool(element.get("hasGeometry", element.get("has_geometry", False))),
        "isHidden": bool(element.get("isHidden", element.get("is_hidden", False))),
        "ancestorPath": element.get("ancestorPath") or element.get("ancestor_path") or "",
        "sourceFile": element.get("sourceFileName") or element.get("source_file") or "",
        "boqEligible": bool(element.get("boqEligible", element.get("boq_eligible", True))),
        "boundingBox": element.get("boundingBox"),
        "position": element.get("position"),
        "coordinateUnits": element.get("coordinateUnits"),
        "coordinateFrame": element.get("coordinateFrame"),
        "spatialStatus": element.get("spatialStatus", "missing"),
        "classificationEvidence": element.get("classificationEvidence"),
        "propCount": len(props),
        "properties": props,
        "measures": _measures(element),
    }


def _filtered_elements(
    q: str = "",
    class_name: str = "",
    uniformat: str = "",
    type_name: str | None = None,
    material: str | None = None,
) -> list[tuple[int, dict[str, Any]]]:
    query = q.casefold().strip()
    rows: list[tuple[int, dict[str, Any]]] = []
    for index, element in enumerate(_raw_elements(), start=1):
        row = _compat_element(element, index)
        if class_name and row["className"] != class_name:
            continue
        if uniformat and row["uniformatCode"] != uniformat:
            continue
        actual_type = _prop(element, "Element.Type", "Item.Type")
        actual_material = _prop(
            element, "Revit Material.Name", "Structural Material.Name",
            "Element.Structural Material", "Material.Name", "Item.Material",
        )
        if type_name is not None and actual_type != type_name:
            continue
        if material is not None and actual_material != material:
            continue
        if query:
            searchable = " ".join([
                row["id"], row["displayName"], row["className"],
                row["uniformatCode"], row["uniformatTitle"],
                *[f"{key} {value}" for key, value in row["properties"].items()],
            ]).casefold()
            if query not in searchable:
                continue
        rows.append((index, element))
    return rows


def _compat_models() -> dict[str, Any]:
    summary = store.summary()
    model = summary["modelName"]
    return {
        "selected": model,
        "models": [{
            "model": model,
            "elements": summary["elementCount"],
            "ingested": True,
            "onDisk": store.path.is_file(),
            "path": str(store.path),
        }],
    }


async def call_mcp_tool(limit: int = 1000, offset: int = 0):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(BASE_DIR / "mcp_server.py")],
        env=dict(os.environ),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_navisworks_elements",
                arguments={"limit": limit, "offset": offset},
            )

    if getattr(result, "is_error", False):
        detail = "\n".join(
            text for item in result.content if (text := getattr(item, "text", None))
        )
        raise RuntimeError(detail or "MCP tool failed")
    text_parts = [getattr(item, "text", None) for item in result.content]
    text_parts = [text for text in text_parts if text]
    if not text_parts:
        return {"error": "MCP returned no text content", "elements": []}
    return json.loads("\n".join(text_parts))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/api/model")
async def model_data(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    try:
        return JSONResponse(await call_mcp_tool(limit=limit, offset=offset))
    except Exception as exc:
        return JSONResponse(
            {"error": str(exc), "elements": [], "source": "MCP"},
            status_code=500,
        )


# Compatibility API for the NavisMCP-2.2 dashboard layout. The source stays
# the current Headless JSON snapshot; no legacy SQLite database is introduced.
@app.get("/api/stats")
async def compat_stats(model: str | None = None):
    payload = store.ensure_loaded()
    elements = payload.get("elements") or []
    classes = {
        element.get("classDisplayName") or element.get("class_name") or ""
        for element in elements
    }
    uniformats = {
        element.get("uniformatCode") or element.get("uniformat_code") or ""
        for element in elements
    }
    return {
        "model": payload.get("modelName") or store.path.name,
        "totalElements": len(elements),
        "distinctClasses": len(classes - {""}),
        "distinctUniformats": len(uniformats - {""}),
        "totalProperties": sum(len(element.get("properties") or {}) for element in elements),
    }


@app.get("/api/classes")
async def compat_classes(limit: int = Query(default=1000, ge=1, le=5000), model: str | None = None):
    counts = Counter(
        element.get("classDisplayName") or element.get("class_name") or ""
        for element in _raw_elements()
    )
    return {
        "classes": [
            {"name": name, "count": count}
            for name, count in counts.most_common(limit) if name
        ]
    }


@app.get("/api/uniformat")
async def compat_uniformat(limit: int = Query(default=1000, ge=1, le=5000), model: str | None = None):
    groups: dict[tuple[str, str], int] = Counter()
    for element in _raw_elements():
        code = element.get("uniformatCode") or element.get("uniformat_code") or ""
        title = element.get("uniformatTitle") or element.get("uniformat_title") or ""
        groups[(code, title)] += 1
    ordered = sorted(groups.items(), key=lambda item: (-item[1], item[0][0]))[:limit]
    return {
        "uniformat": [
            {"code": code, "title": title, "count": count}
            for (code, title), count in ordered
        ]
    }


@app.get("/api/elements")
async def compat_elements(
    q: str = "",
    className: str = "",
    uniformat: str = "",
    type: str | None = None,
    material: str | None = None,
    model: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=5000),
):
    rows = _filtered_elements(q, className, uniformat, type, material)
    start = (page - 1) * limit
    selected = rows[start:start + limit]
    return {
        "model": store.summary()["modelName"],
        "total": len(rows),
        "page": page,
        "limit": limit,
        "elements": [_compat_element(element, rowid) for rowid, element in selected],
    }


@app.get("/api/elements/{rowid}")
async def compat_element_detail(rowid: int):
    elements = _raw_elements()
    if rowid < 1 or rowid > len(elements):
        raise HTTPException(status_code=404, detail="Element not found")
    return _compat_element(elements[rowid - 1], rowid)


@app.get("/api/semantic")
async def compat_semantic(
    q: str = "",
    model: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=5000),
):
    result = await compat_elements(q=q, model=model, page=page, limit=limit)
    result.update({
        "parser": "keyword-compatible",
        "interpretation": {"keywords": [word for word in q.split() if word]},
    })
    return result


def _raw_boq_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for element in _raw_elements():
        measures = _measures(element)
        rows.append({
            "code": element.get("uniformatCode") or element.get("uniformat_code") or "",
            "title": element.get("uniformatTitle") or element.get("uniformat_title") or "",
            "type": _prop(element, "Element.Type", "Item.Type"),
            "material": _prop(
                element, "Revit Material.Name", "Structural Material.Name",
                "Element.Structural Material", "Material.Name", "Item.Material",
            ),
            "count": 1,
            "area": measures["area"] or 0.0,
            "volume": measures["volume"] or 0.0,
            "length": measures["length"] or 0.0,
        })
    return rows


def _sum_boq(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    return {
        "count": sum(int(row["count"]) for row in rows),
        "area": round(sum(float(row["area"]) for row in rows), 3),
        "volume": round(sum(float(row["volume"]) for row in rows), 3),
        "length": round(sum(float(row["length"]) for row in rows), 3),
    }


@app.get("/api/boq")
async def compat_boq(order: str = "code", model: str | None = None):
    source = _raw_boq_rows()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in source:
        grouped[(row["code"], row["title"])].append(row)
    items = [
        {"code": code, "title": title, **_sum_boq(rows)}
        for (code, title), rows in grouped.items()
    ]
    items.sort(key=lambda row: (row["code"], row["title"]))
    return {"items": items, "totals": _sum_boq(source), "units": {"area": "m²", "volume": "m³", "length": "m"}}


@app.get("/api/boq/detailed")
async def compat_boq_detailed(order: str = "code", model: str | None = None):
    source = _raw_boq_rows()
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in source:
        grouped[(row["code"], row["title"], row["type"], row["material"])].append(row)
    items = [
        {"code": code, "title": title, "type": type_name, "material": material, **_sum_boq(rows)}
        for (code, title, type_name, material), rows in grouped.items()
    ]
    items.sort(key=lambda row: (row["code"], row["type"], row["material"]))
    return {"items": items, "totals": _sum_boq(source), "units": {"area": "m²", "volume": "m³", "length": "m"}}


@app.get("/api/models")
async def compat_models():
    return _compat_models()


@app.get("/api/models/scan")
async def compat_model_scan():
    return _compat_models()


@app.get("/api/agent/status")
async def compat_agent_status():
    return {"enabled": True, "model": "local deterministic MCP/BOQ agent"}


@app.get("/api/boq/options")
async def boq_options():
    bundle = load_bundle()
    return {
        "disciplines": ["Structure", "Architecture", "MEP"],
        "model": store.summary(),
        "versions": {name: value["version"] for name, value in bundle.items()},
        "phase": "1-4 implemented; project rules and final verification remain guarded",
    }


@app.post("/api/boq/run")
async def run_boq(request: BoqRequest):
    try:
        payload = store.ensure_loaded()
        result = await asyncio.to_thread(
            run_boq_workflow_from_payload, payload, request.disciplines
        )
        return JSONResponse(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"BOQ workflow failed: {exc}") from exc


@app.get("/api/boq/workflows")
async def boq_workflows(limit: int = Query(default=20, ge=1, le=100)):
    return {"workflows": list_workflows(limit)}


@app.get("/api/boq/{job_id}")
async def boq_result(job_id: str):
    result = get_workflow(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="BOQ workflow not found")
    return JSONResponse(result)


@app.get("/api/boq/{job_id}/export.csv")
async def boq_csv(job_id: str):
    result = get_workflow(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="BOQ workflow not found")
    content = export_workflow_csv(result)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="boq-{job_id}.csv"'},
    )


@app.get("/api/workflows/boq/options")
async def compat_workflow_options():
    return await boq_options()


@app.post("/api/workflows/boq")
async def compat_run_workflow(request: WorkflowRequest):
    return await run_boq(BoqRequest(disciplines=request.disciplines))


@app.get("/api/workflows/boq")
async def compat_workflows(limit: int = Query(default=20, ge=1, le=100)):
    return await boq_workflows(limit)


@app.get("/api/workflows/boq/{job_id}")
async def compat_workflow_result(job_id: str):
    return await boq_result(job_id)


@app.get("/api/workflows/boq/{job_id}/export/csv")
async def compat_workflow_csv(job_id: str):
    return await boq_csv(job_id)


@app.get("/api/workflows/boq/{job_id}/export/json")
async def compat_workflow_json(job_id: str):
    result = get_workflow(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="BOQ workflow not found")
    return Response(
        content=json.dumps(result, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="boq-{job_id}.json"'},
    )


@app.post("/api/refresh")
async def compat_refresh(model: str | None = None):
    # Refresh the in-memory view from the configured snapshot. A new Navisworks
    # export remains an explicit run_export.ps1 operation.
    payload = store.ensure_loaded()
    return {
        "status": "reloaded",
        "model": payload.get("modelName") or store.path.name,
        "ingestedElements": len(payload.get("elements") or []),
        "source": str(store.path),
    }


@app.post("/api/agent/chat")
async def agent_chat(request: AgentRequest):
    try:
        result = await asyncio.to_thread(
            handle_agent_request,
            request.message,
            store.ensure_loaded(),
            request.disciplines,
        )
        result.setdefault("answer", result.get("message", ""))
        result.setdefault("trace", [{
            "phase": "act",
            "tool": result.get("action", "describe_model"),
            "message": "Local Agent selected a deterministic MCP/BOQ tool",
            "output": result.get("summary") or {
                "model": result.get("model"), "elementCount": result.get("elementCount")
            },
        }])
        return JSONResponse(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent failed: {exc}") from exc
