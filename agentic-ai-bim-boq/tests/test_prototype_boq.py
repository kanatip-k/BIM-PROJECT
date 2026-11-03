from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python_app"))

from boq_workflow.configuration import load_bundle  # noqa: E402
from boq_workflow.pipeline import run_pipeline  # noqa: E402
from boq_workflow.service import (  # noqa: E402
    _pipeline_input,
    export_workflow_csv,
    get_workflow,
    list_workflows,
    run_boq_workflow_from_payload,
)


def _fixture_payload() -> dict:
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "case2_real_samples.json").read_text(encoding="utf-8")
    )
    architecture = [
        sample for sample in fixture["samples"] if sample["sourceFile"] == "CASE2_AR.json"
    ]
    return {
        "modelName": architecture[0]["modelName"],
        "snapshotUtc": "2026-09-29T00:00:00Z",
        "elements": [sample["element"] for sample in architecture],
    }


def test_configuration_and_pipeline_keep_real_case2_guards():
    payload = _fixture_payload()
    result = run_pipeline(
        payload["modelName"],
        [_pipeline_input(item) for item in payload["elements"]],
        load_bundle(),
    )
    classified = {item["id"]: item for item in result["classifiedElements"]}
    codes = {item["element_code"] for item in classified.values()}
    assert {"A029", "A030", None} <= codes
    assert result["stages"][0]["outputCount"] == 3
    assert all(line["elementCode"] is not None for line in result["boq"]["lines"])
    assert any(issue["code"] == "GROUP_NODE_EXCLUDED" for issue in result["issues"])


def test_json_service_persists_and_exports_csv(tmp_path: Path):
    result = run_boq_workflow_from_payload(_fixture_payload(), result_dir=tmp_path)
    assert result["jobId"]
    assert "classifiedElements" not in result
    assert result["diagnostics"]["classifiedElementCount"] == 3
    assert get_workflow(result["jobId"], result_dir=tmp_path)["jobId"] == result["jobId"]
    assert list_workflows(result_dir=tmp_path)[0]["jobId"] == result["jobId"]
    assert export_workflow_csv(result).startswith("discipline,elementCode,eitCostCode")


def test_legacy_export_is_rejected_instead_of_returning_empty_boq(tmp_path: Path):
    payload = {
        "modelName": "legacy.json",
        "elements": [{"id": "", "properties": {}, "displayName": "Solid"} for _ in range(20)],
    }
    with pytest.raises(ValueError, match="LEGACY_EXPORT_SCHEMA"):
        run_boq_workflow_from_payload(payload, result_dir=tmp_path)
