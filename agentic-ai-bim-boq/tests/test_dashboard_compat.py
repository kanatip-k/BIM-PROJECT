from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python_app"))

import web_app  # noqa: E402


def test_navis_22_layout_keeps_the_new_agent_and_workflow_buttons():
    client = TestClient(web_app.app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "NavisMCP Explorer" in html
    assert 'id="modelsBtn"' in html
    assert 'id="boqBtn"' in html
    assert 'id="boqDetailBtn"' in html
    assert 'id="agentBtn"' in html
    assert 'id="boqWorkflowBtn"' in html
    client.close()


def test_dashboard_compatibility_api_uses_the_current_json_snapshot(tmp_path, monkeypatch):
    snapshot = tmp_path / "dashboard-sample.boq.json"
    snapshot.write_text(json.dumps({
        "modelName": "DASHBOARD_SAMPLE.nwc",
        "snapshotUtc": "2026-09-29T00:00:00Z",
        "elementCount": 2,
        "elements": [
            {
                "id": "door-1", "displayName": "Door D1",
                "classDisplayName": "Doors: D1", "hasGeometry": True,
                "uniformatCode": "C1020", "uniformatTitle": "Interior Doors",
                "boqEligible": True,
                "properties": {
                    "Element.Category": "Doors", "Element.Type": "D1",
                    "Element.Area": "DoubleArea:2.5",
                },
            },
            {
                "id": "beam-1", "displayName": "Beam B1",
                "classDisplayName": "Structural Framing: B1", "hasGeometry": True,
                "uniformatCode": "B1012", "uniformatTitle": "Floor Construction",
                "boqEligible": True,
                "properties": {
                    "Element.Category": "Structural Framing", "Element.Type": "B1",
                    "Element.Volume": "DoubleVolume:1.25",
                },
            },
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(web_app.store, "path", snapshot)
    monkeypatch.setattr(web_app.store, "_payload", None)
    monkeypatch.setattr(web_app.store, "_modified_ns", None)

    client = TestClient(web_app.app)
    assert client.get("/api/stats").json()["totalElements"] == 2
    assert client.get("/api/classes?limit=10").json()["classes"][0]["count"] == 1
    assert client.get("/api/uniformat?limit=10").status_code == 200
    elements = client.get("/api/elements?page=1&limit=10").json()
    assert elements["total"] == 2
    assert elements["elements"][0]["rowid"] == 1
    assert client.get("/api/elements/1").json()["id"] == "door-1"
    boq = client.get("/api/boq").json()
    assert boq["totals"] == {"count": 2, "area": 2.5, "volume": 1.25, "length": 0.0}
    assert client.get("/api/boq/detailed").status_code == 200
    assert client.get("/api/agent/status").json()["enabled"] is True
    client.close()
