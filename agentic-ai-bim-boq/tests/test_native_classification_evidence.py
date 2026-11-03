"""Native classification must remain evidence, not an automatic cost-code override."""
import json
import re
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python_app"))
from boq_workflow.service import run_boq_workflow_from_payload, get_workflow
from web_app import _compat_element


def test_conflicting_native_evidence_survives_without_overriding_classification(tmp_path):
    evidence = {"schemaVersion": "1.0", "nativeProperties": [
        {"kind": "assemblycode", "propertyKey": "Type.Assembly Code", "value": "A1020110",
         "internalPropertyKey": "type.assembly", "sourcePath": "model > Family > Type",
         "sourceNodeClass": "Type", "ancestorDistance": 1},
        {"kind": "omniclass", "propertyKey": "Family.OmniClass Number", "value": "conflicting-native-code",
         "sourcePath": "model > Family", "sourceNodeClass": "Family", "ancestorDistance": 2},
        {"kind": "keynote", "propertyKey": "Type.Keynote", "value": "03310",
         "sourcePath": "model > Family > Type", "sourceNodeClass": "Type", "ancestorDistance": 1}],
        "derivedUniformat": {"code": "B1011", "source": "UniformatClassifier.Classify"}}
    element = dict(id="native-column", displayName="Column", classDisplayName="Structural Columns",
        uniformatCode="B1011", boqEligible=True, classificationEvidence=evidence,
        properties={"Element.Category": "Structural Columns",
                    "Element Properties.StructuralMaterialType": "Steel"})
    result = run_boq_workflow_from_payload(dict(modelName="CASE2_ST_ALL.nwc", elements=[element]), result_dir=tmp_path)
    saved = get_workflow(result["jobId"], result_dir=tmp_path)
    assert saved["classificationEvidence"][0]["evidence"] == evidence
    assert saved["classificationEvidence"][0]["element_code"] == "S031"
    assert _compat_element(element, 1)["classificationEvidence"] == evidence
    assert "Type.Keynote" not in element["properties"]  # no silent flattening of inherited fields


@pytest.mark.parametrize("name", ["CASE2_ST_ALL", "CASE2_AR"])
def test_real_nwc_export_preserves_existing_data_and_attaches_ancestor_evidence(name):
    old_path = ROOT / "data/export" / (name + ".spatial.json")
    new_path = ROOT / "data/export" / (name + ".classified-source.json")
    assert new_path.exists(), "Run tools/export_classification.ps1 on the real CASE2 NWC first"
    old = json.loads(old_path.read_text(encoding="utf-8-sig"))
    new = json.loads(new_path.read_text(encoding="utf-8-sig"))
    assert new["classificationEvidenceSchemaVersion"] == "1.0"
    assert new["elementCount"] == old["elementCount"]
    old_rows = old["elements"]
    new_rows = new["elements"]
    assert len(old_rows) == len(new_rows)
    valid = 0
    keynote_values = set()
    for before, after in zip(old_rows, new_rows):
        for key, value in before.items():
            if key != "properties":
                assert after[key] == value, (name, before.get("id"), key)
                continue
            assert value.keys() == after[key].keys()
            # Navisworks creates different temporary texture paths per process.
            volatile_keys = {
                "Autodesk Material.generic_diffuse/unifiedbitmap_Bitmap",
                "Autodesk Material.concrete_bump_map/unifiedbitmap_Bitmap",
                "Autodesk Material.concrete_color/unifiedbitmap_Bitmap",
            }
            for prop, raw in value.items():
                actual = after[key][prop]
                if raw != actual and prop in volatile_keys:
                    for path in (raw, actual):
                        assert re.fullmatch(r"C:\\Users\\Asus\\AppData\\Local\\Temp\\navis_[^\\]+\.(png|jpg)", path, re.I)
                else:
                    assert raw == actual, (name, before.get("id"), prop)
        ev = after["classificationEvidence"]
        assert ev["derivedUniformat"]["code"] == after["uniformatCode"]
        assert ev["derivedUniformat"]["source"] == "UniformatClassifier.Classify"
        rows = ev["nativeProperties"]
        if after.get("id") and after["properties"].get("Element.Category") and rows:
            valid += 1
        for row in rows:
            assert row["value"].strip()
            assert row["internalPropertyKey"]
            assert row["sourceFileName"] == after["sourceFileName"]
            assert row["ancestorDistance"] >= 0
            assert after["ancestorPath"] == row["sourcePath"] or after["ancestorPath"].startswith(row["sourcePath"] + " > ")
            if row["ancestorDistance"]:
                assert row["sourceNodeClass"] in {"Type", "Family"}
            if row["propertyKey"] == "Type.Keynote":
                keynote_values.add(row["value"])
    assert valid == {"CASE2_ST_ALL": 1479, "CASE2_AR": 1155}[name]
    if name == "CASE2_ST_ALL":
        assert keynote_values == {"03310", "05100"}
        assert any(row["value"] == "A1020110" for e in new_rows for row in e["classificationEvidence"]["nativeProperties"])
    else:
        assert keynote_values == set()
        assert any(row["value"] == "23.75.00.00" for e in new_rows for row in e["classificationEvidence"]["nativeProperties"])


def test_default_source_prefers_enriched_snapshot_and_ignores_status(tmp_path, monkeypatch):
    import json_bridge
    monkeypatch.setattr(json_bridge, "_DATA_EXPORT_DIR", tmp_path)
    baseline = tmp_path / "CASE2_ST_ALL.boq.json"
    enriched = tmp_path / "CASE2_ST_ALL.classified-source.json"
    status = tmp_path / "CASE2_ST_ALL.classified-source.status.json"
    baseline.write_text("{}", encoding="utf-8")
    enriched.write_text("{}", encoding="utf-8")
    status.write_text("{}", encoding="utf-8")
    assert json_bridge._find_default_json() == enriched
    enriched.unlink()
    assert json_bridge._find_default_json() == baseline
    baseline.unlink()
    assert json_bridge._find_default_json() != status
