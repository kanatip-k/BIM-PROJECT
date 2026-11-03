from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python_app"))
from boq_workflow.service import run_boq_workflow_from_payload, get_workflow
from web_app import _compat_element

def test_composite_element_spatial_evidence_survives_pipeline_and_persistence(tmp_path):
    box = dict(minX=1, minY=2, minZ=3, maxX=5, maxY=6, maxZ=7)
    element = dict(id="spatial-door", displayName="Door", classDisplayName="Doors",
        hasGeometry=False, boqEligible=True, uniformatCode="C1020",
        sourceFileName="CASE2_AR.nwc", boundingBox=box, position=dict(x=3,y=4,z=5),
        coordinateUnits="Meters", coordinateFrame="navisworks-document",
        spatialStatus="available", spatialSource="ModelItem.BoundingBox including children",
        properties={"Element.Category":"Doors", "Element.Type":"AD1", "Element.Family":"AD1"})
    payload=dict(modelName="CASE2_AR.nwc",coordinateUnits="Meters",
        coordinateFrame="navisworks-document",spatialSchemaVersion="1.0",elements=[element])
    result=run_boq_workflow_from_payload(payload,result_dir=tmp_path)
    saved=get_workflow(result["jobId"],result_dir=tmp_path)
    assert saved["spatialEvidence"][0]["bounding_box"]==box
    assert saved["spatialEvidence"][0]["coordinate_units"]=="Meters"
    assert saved["spatialContext"]["crossModelAlignmentVerified"] is False
    assert _compat_element(element,1)["boundingBox"]==box
    assert _compat_element(element,1)["position"]==element["position"]

def test_legacy_snapshot_does_not_invent_position_or_units(tmp_path):
    element=dict(id="legacy-door",displayName="Door",classDisplayName="Doors",
        uniformatCode="C1020",boqEligible=True,properties={"Element.Category":"Doors"})
    result=run_boq_workflow_from_payload(dict(modelName="CASE2_AR.nwc",elements=[element]),result_dir=tmp_path)
    assert result["spatialEvidence"][0]["bounding_box"] is None
    assert result["spatialEvidence"][0]["coordinate_units"] is None
    assert result["spatialEvidence"][0]["spatial_status"]=="missing"
