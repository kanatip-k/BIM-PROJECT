"""Phase 6 regression snapshot for the proven CASE2/MERGED parity contract.

The CASE2 hashes are a hard precondition. If an export changes, downstream
snapshot comparisons are deliberately blocked until the expected results are
reviewed against that new source data.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python_app"))

from boq_workflow.configuration import load_bundle  # noqa: E402
from boq_workflow.pipeline import (  # noqa: E402
    EVIDENCE_FIELD_ALIASES,
    _evidence_alias_value_valid,
    run_pipeline,
)
from boq_workflow.service import _pipeline_input  # noqa: E402


EXPECTED_CASE2_SHA256 = {
    "CASE2_AR.boq.json": "D2DA9FB646FA54D44EDC70237306B92468708E8B306C7F46188E702D51F0E768",
    "CASE2_ST_ALL.boq.json": "AD86B0EDE7C2732F25D622738422C7568EC45D96F1EBC6F972630669C2F72157",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _assert_case2_hashes() -> dict[str, Path]:
    paths = {name: ROOT / "data" / "export" / name for name in EXPECTED_CASE2_SHA256}
    for name, expected in EXPECTED_CASE2_SHA256.items():
        path = paths[name]
        assert path.is_file(), f"CASE2 source is missing: {path}"
        actual = _sha256(path)
        assert actual == expected, (
            f"CASE2 source data changed for {name}: expected SHA-256 {expected}, got {actual}. "
            "Parity comparisons after this point are meaningless until the snapshot is re-audited."
        )
    return paths


@pytest.fixture(scope="session")
def verified_case2_paths() -> dict[str, Path]:
    # Repeat the first-test precondition so selecting any downstream test with
    # -k cannot bypass source identity validation.
    return _assert_case2_hashes()


@pytest.fixture(scope="session")
def case2_results(verified_case2_paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    bundle = load_bundle()
    results: dict[str, dict[str, Any]] = {}
    for scope, name in (
        ("Structure", "CASE2_ST_ALL.boq.json"),
        ("Architecture", "CASE2_AR.boq.json"),
    ):
        payload = json.loads(verified_case2_paths[name].read_text(encoding="utf-8"))
        results[scope] = {
            "payload": payload,
            "result": run_pipeline(
                payload["modelName"],
                [_pipeline_input(item) for item in payload["elements"]],
                bundle,
            ),
        }
    return results


def _issue_count(result: dict[str, Any], code: str) -> int:
    return sum(int(item.get("count", 1)) for item in result["issues"] if item["code"] == code)


def _non_walls(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in result["classifiedElements"]
        if (item.get("properties") or {}).get("Element.Category") != "Walls"
    ]


def _resolved_non_walls(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _non_walls(result) if item.get("element_code")]


def _element(
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
        "ancestor_path": "Regression probe",
        "uniformat_code": uniformat,
        "uniformat_title": "Regression UNIFORMAT",
        "boq_eligible": True,
        "has_geometry": True,
        "ifc_entity": ifc_entity,
        "ifc_predefined_type": predefined,
        "properties": properties,
    }


def _classified(result: dict[str, Any], element_id: str) -> dict[str, Any]:
    return next(item for item in result["classifiedElements"] if item["id"] == element_id)


def _measured(result: dict[str, Any], element_id: str) -> dict[str, Any] | None:
    return next((item for item in result["elements"] if item["id"] == element_id), None)


def _issue_codes(result: dict[str, Any], element_id: str) -> set[str]:
    return {
        item["code"] for item in result["issues"]
        if element_id in item.get("exampleElementIds", [])
    }


def test_00_case2_source_hashes_are_the_proven_snapshots():
    _assert_case2_hashes()


def test_acceptance_probes_cover_element_eit_uniformat_quantity_and_unit():
    generic = [
        _element("s001", "Pad Footing", "IfcFooting", "A1010", {
            "Element.Category": "Structural Foundations", "Element.Type": "PF-01",
            "Element.Volume": "DoubleVolume:12.5", "Level.Name": "Foundation",
        }, ifc_entity="IfcFooting", predefined="PAD_FOOTING"),
        _element("s028", "Driven Precast Pile", "IfcPile", "A1030", {
            "Element.Category": "Structural Foundations", "Element.Type": "Driven Pile 400",
            "Element.Length": "DoubleLength:18", "Level.Name": "Foundation",
        }, ifc_entity="IfcPile", predefined="NOTDEFINED"),
        _element("m045", "Testing Commissioning Balancing", "System", "D5090", {
            "Element.Category": "Mechanical Equipment", "Element.Type": "Commissioning",
            "Level.Name": "Project",
        }),
        _element("s031", "Steel Beam", "IfcBeam", "B1012", {
            "Element.Category": "Structural Framing", "Element.Type": "H-400x200 66 kg/m",
            "Element.Length": "DoubleLength:10", "Level.Name": "L1",
        }, ifc_entity="IfcBeam", predefined="NOTDEFINED"),
    ]
    generic_result = run_pipeline("PARITY_PROBES.nwc", generic, load_bundle())

    s001, s001_q = _classified(generic_result, "s001"), _measured(generic_result, "s001")
    assert (s001["element_code"], s001["eit_cost_code"], s001["uniformat_cost_code"]) == (
        "S001", "1 1 03", "A1010"
    )
    assert (s001_q["quantity"], s001_q["unit"]) == (12.5, "m3")

    s028, s028_q = _classified(generic_result, "s028"), _measured(generic_result, "s028")
    assert s028["element_code"] == "S028"
    assert (s028_q["measurement_rule"], s028_q["quantity"], s028_q["unit"]) == (
        "LENGTH", 18.0, "m"
    )
    assert "UNIT_BASIS_AMBIGUOUS" in _issue_codes(generic_result, "s028")

    m045, m045_q = _classified(generic_result, "m045"), _measured(generic_result, "m045")
    assert m045["element_code"] == "M045"
    assert (m045_q["quantity"], m045_q["unit"]) == (None, None)
    assert "MANUAL_LINE_ITEM_NOT_AUTO_COMPUTABLE" in _issue_codes(generic_result, "m045")

    s031, s031_q = _classified(generic_result, "s031"), _measured(generic_result, "s031")
    assert (s031["element_code"], s031["eit_cost_code"]) == ("S031", None)
    assert (s031_q["quantity"], s031_q["unit"]) == (None, None)

    case2_probes = [
        _element("steel-column", "Steel Column", "Structural Columns", "B1011", {
            "Element.Category": "Structural Columns", "Element.Family": "Steel Column",
            "Element.Type": "H-300x300", "Element Properties.StructuralMaterialType": "Steel",
            "Element.Volume": "DoubleVolume:1", "Level.Name": "L1",
        }),
        _element("steel-beam", "Steel Beam", "Structural Framing", "B1012", {
            "Element.Category": "Structural Framing", "Element.Family": "Steel Beam",
            "Element.Type": "H-400x200", "Element Properties.StructuralMaterialType": "Steel",
            "Element.Volume": "DoubleVolume:1", "Level.Name": "L1",
        }),
        _element("foundation-slab", "Foundation Slab", "Floors", "A1010", {
            "Element.Category": "Floors", "Element.Family": "Foundation Slab",
            "Element.Type": "Raft 600", "FloorType.IsFoundationSlab": "True",
            "Element.Volume": "DoubleVolume:25", "Level.Name": "Foundation",
        }),
    ]
    case2_result = run_pipeline("CASE2_ST_ALL.nwc", case2_probes, load_bundle())
    for element_id in ("steel-column", "steel-beam"):
        item, measured = _classified(case2_result, element_id), _measured(case2_result, element_id)
        assert (item["element_code"], item["eit_cost_code"]) == ("S031", None)
        assert measured["quantity"] is None
    slab, slab_q = _classified(case2_result, "foundation-slab"), _measured(case2_result, "foundation-slab")
    assert (slab["element_code"], slab["uniformat_cost_code"]) == ("S004", "A1010")
    assert (slab_q["quantity"], slab_q["unit"]) == (25.0, "m3")


def test_structure_snapshot_resolved_rate_wall_guards_and_group_filter(case2_results):
    result = case2_results["Structure"]["result"]
    non_walls = _non_walls(result)
    resolved = _resolved_non_walls(result)
    walls = [
        item for item in result["classifiedElements"]
        if (item.get("properties") or {}).get("Element.Category") == "Walls"
    ]

    assert len(case2_results["Structure"]["payload"]["elements"]) == 10665
    assert _issue_count(result, "GROUP_NODE_EXCLUDED") == 5871
    assert (len(resolved), len(non_walls), round(100 * len(resolved) / len(non_walls), 2)) == (
        3583, 4200, 85.31
    )
    assert Counter(item["element_code"] for item in resolved) == {
        "S004": 22, "S005": 82, "S006": 321, "S007": 294, "S011": 70, "S031": 2794,
    }
    assert len(walls) == 594
    assert _issue_count(result, "ELEMENT_TYPE_NOT_IN_SPEC") == 80
    assert _issue_count(result, "TYPE_ABBREVIATION_UNCONFIRMED") == 514
    assert sum(item.get("element_code") == "S008" for item in walls) == 0
    assert sum(line.get("elementCode") == "S008" for line in result["boq"]["lines"]) == 0


def test_architecture_snapshot_resolved_rate_and_group_filter(case2_results):
    result = case2_results["Architecture"]["result"]
    non_walls = _non_walls(result)
    resolved = _resolved_non_walls(result)

    assert len(case2_results["Architecture"]["payload"]["elements"]) == 33049
    assert _issue_count(result, "GROUP_NODE_EXCLUDED") == 8534
    assert (len(resolved), len(non_walls), round(100 * len(resolved) / len(non_walls), 2)) == (
        1155, 3163, 36.52
    )
    assert Counter(item["element_code"] for item in resolved) == {"A029": 718, "A030": 437}


def test_eit_mapping_distribution_is_the_confirmed_114_row_version():
    mapping = load_bundle()["eitMapping"]
    assert mapping["version"] == "boq-bim-thai-to-eit-costcode-1.0"
    assert len(mapping["mappings"]) == 114
    assert Counter(item["matchStatus"] for item in mapping["mappings"]) == {
        "matched": 75, "needs_review": 25, "unresolved": 14,
    }


def test_evidence_missing_rates_and_architecture_gap_are_model_evidence(case2_results):
    structure = _resolved_non_walls(case2_results["Structure"]["result"])
    architecture = _resolved_non_walls(case2_results["Architecture"]["result"])

    structure_missing = [
        item for item in structure
        if (item.get("required_field_audit") or {}).get("missingFields")
    ]
    architecture_missing = [
        item for item in architecture
        if (item.get("required_field_audit") or {}).get("missingFields")
    ]
    assert (len(structure_missing), len(structure), round(100 * len(structure_missing) / len(structure), 2)) == (
        2880, 3583, 80.38
    )
    assert (len(architecture_missing), len(architecture)) == (1155, 1155)

    # FinishType and FireRating have no confirmed CASE2 aliases. SectionSize
    # has only Element.Type, which counts solely when an explicit dimension is
    # present. Every resolved A029/A030 instance lacks that evidence.
    assert "FinishType" not in EVIDENCE_FIELD_ALIASES
    assert "FireRating" not in EVIDENCE_FIELD_ALIASES
    assert EVIDENCE_FIELD_ALIASES["SectionSize"] == ("Element.Type",)
    canonical = {"SectionSize", "FinishType", "FireRating"}
    for item in architecture:
        props = item.get("properties") or {}
        audit = item["required_field_audit"]
        assert canonical.isdisjoint(props)
        assert canonical <= set(audit["missingFields"])
        assert canonical.isdisjoint(audit["presentSources"])
        assert not _evidence_alias_value_valid(
            "SectionSize", "properties.Element.Type", props.get("Element.Type")
        )
        assert not re.search(
            r"\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?",
            str(props.get("Element.Type") or ""),
            re.IGNORECASE,
        )
