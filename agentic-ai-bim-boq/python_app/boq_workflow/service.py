"""Run the deterministic BOQ workflow directly from a Navisworks JSON export."""
from __future__ import annotations

import csv
import io
import json
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .configuration import load_bundle
from .pipeline import run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULT_DIR = PROJECT_ROOT / "data" / "boq_results"
ALLOWED_DISCIPLINES = {"Structure", "Architecture", "MEP"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pipeline_input(exported: dict[str, Any]) -> dict[str, Any]:
    """Translate the exporter's camelCase document to the pipeline contract."""
    return {
        "id": exported.get("id"),
        "display_name": exported.get("displayName"),
        "class_name": exported.get("classDisplayName"),
        "ancestor_path": exported.get("ancestorPath"),
        "source_file_name": exported.get("sourceFileName"),
        "uniformat_code": exported.get("uniformatCode"),
        "uniformat_title": exported.get("uniformatTitle"),
        "boq_eligible": exported.get("boqEligible"),
        "has_geometry": exported.get("hasGeometry"),
        "is_hidden": exported.get("isHidden"),
        "bounding_box": exported.get("boundingBox"),
        "position": exported.get("position"),
        "coordinate_units": exported.get("coordinateUnits"),
        "coordinate_frame": exported.get("coordinateFrame"),
        "spatial_source": exported.get("spatialSource"),
        "spatial_status": exported.get("spatialStatus", "missing"),
        "classification_evidence": exported.get("classificationEvidence"),
        "properties": exported.get("properties") or {},
    }


def _selected_disciplines(disciplines: list[str] | None) -> list[str]:
    selected = disciplines or sorted(ALLOWED_DISCIPLINES)
    invalid = sorted(set(selected) - ALLOWED_DISCIPLINES)
    if invalid:
        raise ValueError(f"Unsupported disciplines: {', '.join(invalid)}")
    return selected


def _result_directory(result_dir: str | Path | None = None) -> Path:
    configured = os.environ.get("BOQ_RESULT_DIR")
    return Path(result_dir or configured or DEFAULT_RESULT_DIR)


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep the auditable BOQ but avoid duplicating every raw BIM property."""
    classified = result.pop("classifiedElements", [])
    measured = result.pop("elements", [])
    result["spatialEvidence"] = [
        {key: item.get(key) for key in (
            "id", "source_file_name", "ancestor_path", "element_code",
            "bounding_box", "position", "coordinate_units", "coordinate_frame",
            "spatial_source", "spatial_status",
        )}
        for item in classified
    ]
    result["classificationEvidence"] = [
        {"id": item.get("id"), "element_code": item.get("element_code"),
         "source_file_name": item.get("source_file_name"),
         "evidence": item.get("classification_evidence")}
        for item in classified if item.get("classification_evidence") is not None
    ]
    result["diagnostics"] = {
        "classifiedElementCount": len(classified),
        "quantifiedElementCount": len(measured),
        "elementCodeCounts": dict(sorted(Counter(
            item.get("element_code") or "UNRESOLVED" for item in classified
        ).items())),
        "disciplineCounts": dict(sorted(Counter(
            item.get("discipline") or "Unknown" for item in classified
        ).items())),
    }
    return result


def _persist(result: dict[str, Any], result_dir: str | Path | None = None) -> Path:
    directory = _result_directory(result_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result['jobId']}.json"
    temporary = path.with_suffix(".json.writing")
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def run_boq_workflow_from_payload(
    payload: dict[str, Any],
    disciplines: list[str] | None = None,
    *,
    result_dir: str | Path | None = None,
    include_element_details: bool = False,
) -> dict[str, Any]:
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise ValueError("Navisworks JSON must contain an elements array")
    if elements:
        identified = sum(bool(item.get("id")) for item in elements)
        categorized = sum(bool((item.get("properties") or {}).get("Element.Category"))
                          for item in elements)
        minimum = max(1, len(elements) // 100)
        if identified < minimum or categorized < minimum:
            raise ValueError(
                "LEGACY_EXPORT_SCHEMA: export ไม่มี id/Element.Category เพียงพอสำหรับ BOQ; "
                "รัน run_export.ps1 ด้วย NavisHeadlessExporter รุ่นที่อัปเดตแล้ว"
            )

    selected = _selected_disciplines(disciplines)
    model = str(payload.get("modelName") or "Unnamed Navisworks model")
    result = run_pipeline(model, [_pipeline_input(item) for item in elements], load_bundle(), selected)
    result["spatialContext"] = {
        "coordinateUnits": payload.get("coordinateUnits"),
        "coordinateFrame": payload.get("coordinateFrame"),
        "crossModelAlignmentVerified": False,
        "schemaVersion": payload.get("spatialSchemaVersion"),
    }
    if not include_element_details:
        result = _compact_result(result)

    job_id = str(uuid.uuid4())
    request = {
        "model": model,
        "disciplines": selected,
        "sourceElementCount": len(elements),
        "snapshotUtc": payload.get("snapshotUtc"),
        "rulebook": "boq-element-rules",
        "pricebook": result["versions"]["pricebook"],
    }
    result.update({"jobId": job_id, "createdUtc": _now(), "request": request})
    result["resultPath"] = str(_result_directory(result_dir) / f"{job_id}.json")
    _persist(result, result_dir)
    return result


def run_boq_workflow_from_file(
    json_path: str | Path,
    disciplines: list[str] | None = None,
    *,
    result_dir: str | Path | None = None,
    include_element_details: bool = False,
) -> dict[str, Any]:
    path = Path(json_path)
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("Navisworks JSON root must be an object")
    return run_boq_workflow_from_payload(
        payload,
        disciplines,
        result_dir=result_dir,
        include_element_details=include_element_details,
    )


def run_boq_workflow(
    json_path: str | Path,
    disciplines: list[str] | None = None,
    *,
    result_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compatibility entry point used by the MCP server."""
    return run_boq_workflow_from_file(json_path, disciplines, result_dir=result_dir)


def get_workflow(job_id: str, *, result_dir: str | Path | None = None) -> dict[str, Any] | None:
    if not job_id or any(ch not in "0123456789abcdef-" for ch in job_id.casefold()):
        return None
    path = _result_directory(result_dir) / f"{job_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_workflows(limit: int = 20, *, result_dir: str | Path | None = None) -> list[dict[str, Any]]:
    directory = _result_directory(result_dir)
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "jobId": result.get("jobId"),
                "model": result.get("model"),
                "status": result.get("status"),
                "createdUtc": result.get("createdUtc"),
                "summary": result.get("summary", {}),
            })
        except (OSError, ValueError, TypeError):
            continue
        if len(rows) >= max(1, min(int(limit), 100)):
            break
    return rows


def export_workflow_csv(result: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    fields = [
        "discipline", "elementCode", "eitCostCode", "uniformatCostCode",
        "costCode", "title", "type", "material", "measurementRule",
        "quantity", "unit", "materialRate", "laborRate", "equipmentRate",
        "unitRate", "totalCost", "ruleId", "priceSource", "elementCount",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(result.get("boq", {}).get("lines", []))
    return output.getvalue()
