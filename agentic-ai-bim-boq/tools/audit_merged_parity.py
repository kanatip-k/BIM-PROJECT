"""Reproduce the Phase 1-4 parity audit against the deployed MERGED package."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

MERGED = Path(__file__).resolve().parents[1]
ORIGINAL = Path(r"D:\BIM-PROJECT\NavisMCP-2.2\NavisMCP\release\cache")
sys.path.insert(0, str(MERGED / "python_app"))

from boq_workflow.configuration import load_bundle  # noqa: E402
from boq_workflow.pipeline import run_pipeline  # noqa: E402
from boq_workflow.service import _pipeline_input  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def issue_count(result: dict[str, Any], code: str) -> int:
    return sum(int(item.get("count", 1)) for item in result["issues"] if item["code"] == code)


def full_audit(path: Path, scope: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = run_pipeline(
        payload["modelName"],
        [_pipeline_input(item) for item in payload["elements"]],
        load_bundle(),
    )
    classified = result["classifiedElements"]
    measured = result["elements"]
    walls = [item for item in classified
             if (item.get("properties") or {}).get("Element.Category") == "Walls"]
    non_walls = [item for item in classified
                 if (item.get("properties") or {}).get("Element.Category") != "Walls"]
    resolved = [item for item in non_walls if item.get("element_code")]
    with_missing = [item for item in resolved
                    if (item.get("required_field_audit") or {}).get("missingFields")]
    missing_fields: Counter[str] = Counter()
    for item in resolved:
        missing_fields.update((item.get("required_field_audit") or {}).get("missingFields", []))
    measured_ids = {item.get("id") for item in measured}
    dropped = [item for item in resolved if item.get("id") not in measured_ids]
    return {
        "file": path.name,
        "modelName": payload["modelName"],
        "input": len(payload["elements"]),
        "acquired": result["stages"][0]["outputCount"],
        "groupNodeExcluded": issue_count(result, "GROUP_NODE_EXCLUDED"),
        "classified": len(classified),
        "nonWalls": {
            "total": len(non_walls),
            "resolved": len(resolved),
            "resolvedPercent": round(100 * len(resolved) / len(non_walls), 2),
            "resolvedCodes": dict(sorted(Counter(item["element_code"] for item in resolved).items())),
        },
        "walls": {
            "total": len(walls),
            "elementTypeNotInSpec": issue_count(result, "ELEMENT_TYPE_NOT_IN_SPEC"),
            "typeAbbreviationUnconfirmed": issue_count(result, "TYPE_ABBREVIATION_UNCONFIRMED"),
            "classifiedAsS008": sum(item.get("element_code") == "S008" for item in walls),
            "s008BoqLineCount": sum(line.get("elementCode") == "S008" for line in result["boq"]["lines"]),
        },
        "quantified": {
            "total": len(measured),
            "byElementCode": dict(sorted(Counter(item.get("element_code") for item in measured).items())),
            "resolvedButNotQuantified": len(dropped),
            "droppedByElementCode": dict(sorted(Counter(item.get("element_code") for item in dropped).items())),
            "missingMeasureIssues": issue_count(result, "MISSING_MEASURE"),
        },
        "evidence": {
            "resolved": len(resolved),
            "withAtLeastOneMissing": len(with_missing),
            "percentWithAtLeastOneMissing": round(100 * len(with_missing) / len(resolved), 2),
            "topFiveMissing": missing_fields.most_common(5),
        },
        "boq": result["summary"],
        "scope": scope,
    }


def element(
    element_id: str,
    name: str,
    class_name: str,
    uniformat: str,
    properties: dict[str, Any],
    *,
    ifc_entity: str | None = None,
    predefined: str | None = None,
) -> dict[str, Any]:
    return {
        "id": element_id,
        "display_name": name,
        "class_name": class_name,
        "ancestor_path": "Audit model",
        "uniformat_code": uniformat,
        "uniformat_title": "Audit UNIFORMAT",
        "boq_eligible": True,
        "has_geometry": True,
        "ifc_entity": ifc_entity,
        "ifc_predefined_type": predefined,
        "properties": properties,
    }


def find_by_id(result: dict[str, Any], element_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    classified = next(item for item in result["classifiedElements"] if item["id"] == element_id)
    measured = next((item for item in result["elements"] if item["id"] == element_id), None)
    return classified, measured


def issue_codes_for(result: dict[str, Any], element_id: str) -> list[str]:
    return sorted(item["code"] for item in result["issues"]
                  if element_id in item.get("exampleElementIds", []))


def probe_audit() -> dict[str, Any]:
    generic = [
        element("probe-s001", "Pad Footing", "IfcFooting", "A1010", {
            "Element.Category": "Structural Foundations", "Element.Type": "PF-01",
            "Element.Volume": "DoubleVolume:12.5", "Level.Name": "Foundation",
        }, ifc_entity="IfcFooting", predefined="PAD_FOOTING"),
        element("probe-s028", "Driven Precast Pile", "IfcPile", "A1030", {
            "Element.Category": "Structural Foundations", "Element.Type": "Driven Pile 400",
            "Element.Length": "DoubleLength:18", "Level.Name": "Foundation",
        }, ifc_entity="IfcPile", predefined="NOTDEFINED"),
        element("probe-m045", "Testing Commissioning Balancing", "System", "D5090", {
            "Element.Category": "Mechanical Equipment", "Element.Type": "Commissioning",
            "Level.Name": "Project",
        }),
        element("probe-s031", "Steel Beam", "IfcBeam", "B1012", {
            "Element.Category": "Structural Framing", "Element.Type": "H-400x200 66 kg/m",
            "Element.Length": "DoubleLength:10", "Level.Name": "L1",
        }, ifc_entity="IfcBeam", predefined="NOTDEFINED"),
    ]
    generic_result = run_pipeline("PARITY_PROBES.nwc", generic, load_bundle())

    case2 = [
        element("probe-steel-column", "Steel Column", "Structural Columns", "B1011", {
            "Element.Category": "Structural Columns", "Element.Family": "Steel Column",
            "Element.Type": "H-300x300", "Element Properties.StructuralMaterialType": "Steel",
            "Element.Volume": "DoubleVolume:1", "Level.Name": "L1",
        }),
        element("probe-steel-beam", "Steel Beam", "Structural Framing", "B1012", {
            "Element.Category": "Structural Framing", "Element.Family": "Steel Beam",
            "Element.Type": "H-400x200", "Element Properties.StructuralMaterialType": "Steel",
            "Element.Volume": "DoubleVolume:1", "Level.Name": "L1",
        }),
        element("probe-foundation-slab", "Foundation Slab", "Floors", "A1010", {
            "Element.Category": "Floors", "Element.Family": "Foundation Slab",
            "Element.Type": "Raft 600", "FloorType.IsFoundationSlab": "True",
            "Element.Volume": "DoubleVolume:25", "Level.Name": "Foundation",
        }),
    ]
    case2_result = run_pipeline("CASE2_ST_ALL.nwc", case2, load_bundle())
    output: dict[str, Any] = {}
    for probe_id in ("probe-s001", "probe-s028", "probe-m045", "probe-s031"):
        classified, measured = find_by_id(generic_result, probe_id)
        output[probe_id] = {
            "element_code": classified.get("element_code"),
            "eit_cost_code": classified.get("eit_cost_code"),
            "uniformat_cost_code": classified.get("uniformat_cost_code"),
            "measurementRule": measured.get("measurement_rule") if measured else None,
            "quantity": measured.get("quantity") if measured else None,
            "unit": measured.get("unit") if measured else None,
            "issues": issue_codes_for(generic_result, probe_id),
        }
    for probe_id in ("probe-steel-column", "probe-steel-beam", "probe-foundation-slab"):
        classified, measured = find_by_id(case2_result, probe_id)
        output[probe_id] = {
            "element_code": classified.get("element_code"),
            "eit_cost_code": classified.get("eit_cost_code"),
            "uniformat_cost_code": classified.get("uniformat_cost_code"),
            "measurementRule": measured.get("measurement_rule") if measured else None,
            "quantity": measured.get("quantity") if measured else None,
            "unit": measured.get("unit") if measured else None,
            "issues": issue_codes_for(case2_result, probe_id),
        }
    return output


def main() -> None:
    pairs = [
        (ORIGINAL / "CASE2_AR.json", MERGED / "data" / "export" / "CASE2_AR.boq.json"),
        (ORIGINAL / "CASE2_ST_ALL.json", MERGED / "data" / "export" / "CASE2_ST_ALL.boq.json"),
    ]
    hashes = []
    for original, merged in pairs:
        original_hash, merged_hash = sha256(original), sha256(merged)
        hashes.append({
            "original": str(original), "merged": str(merged),
            "originalBytes": original.stat().st_size, "mergedBytes": merged.stat().st_size,
            "originalSha256": original_hash, "mergedSha256": merged_hash,
            "identical": original_hash == merged_hash,
        })
    mapping = load_bundle()["eitMapping"]
    report = {
        "inputIdentity": hashes,
        "fullAudits": [
            full_audit(MERGED / "data" / "export" / "CASE2_ST_ALL.boq.json", "Structure"),
            full_audit(MERGED / "data" / "export" / "CASE2_AR.boq.json", "Architecture"),
        ],
        "probes": probe_audit(),
        "eitMapping": {
            "version": mapping["version"],
            "total": len(mapping["mappings"]),
            "statuses": dict(sorted(Counter(item["matchStatus"] for item in mapping["mappings"]).items())),
        },
        "evidenceImplementation": {
            "auditInput": "raw element plus confirmed EVIDENCE_FIELD_ALIASES during VALIDATE",
            "classificationStageCheck": "check_pipeline_fields('CLASSIFY', classified)",
            "quantifyStageCheck": "check_pipeline_fields('QUANTIFY', measured)",
            "note": "evidence is not inferred from element_code; pipeline-produced fields are checked after their producing stage",
        },
    }
    output = MERGED / "docs" / "merged_parity_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
