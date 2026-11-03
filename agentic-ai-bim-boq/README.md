# Agentic BIM-to-BOQ Prototype

A prototype for exporting Navisworks model properties and processing them through a Python bridge, MCP tools, and a web dashboard to prepare bill-of-quantities workflows.

## Overview and features

The inspected source contains acquisition, validation, normalization, classification, quantity calculation, demonstration pricing, and result generation workflows. It includes C# exporter projects, Python MCP tools, a FastAPI dashboard, and an ontology component. Feature presence was reviewed statically; execution has not been verified during migration.

## Technology and structure

- C# / .NET and Autodesk Navisworks exporter projects: `navisworks-headless-exporter/`
- Python, FastAPI, Uvicorn, MCP, HTTPX, Jinja2, Anthropic SDK, OpenPyXL: `python_app/`
- Ontology integration: `ontology_neo4j/`
- Existing tests: `tests/`; inspection utilities: `tools/`
- `start.ps1` launches the bridge and dashboard; `run_export.ps1` handles model export.

## Requirements and installation

Use Windows for the supplied scripts and Navisworks integration. Confirm the installed Navisworks version and the matching .NET SDK against the `.csproj` files before building the exporter. Python dependency versions are declared in `python_app/requirements.txt`; interpreter compatibility remains to be tested.

```powershell
cd python_app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

## Running

This review copy omits model data and generated exports. The withheld logging launcher was replaced in this copy with a version that stores no credential and uses the project virtual environment. Set any required provider credential through the process environment. Resolve the hold list in `PREPARATION_MANIFEST.json` before attempting a complete run. Obtain an authorized model and validate the exporter configuration, then run `run_export.ps1` and `start.ps1`. The supplied launcher expects JSON under `data/export/`, uses bridge port 8765, and serves the dashboard at `http://127.0.0.1:8000`.

Existing documentation lists `python -m pytest tests -q`; pytest is not in the application requirements. Migration checks selected `test_prototype_boq.py` and `test_regression_snapshot.py`: 5 tests passed, 1 failed and 3 errored because the reduced snapshot excludes `data/export/CASE2_AR.boq.json` and `CASE2_ST_ALL.boq.json`. These results do not verify the full suite. Supply the original authorized exports locally to run the snapshot checks; do not fabricate replacement fixtures.

## Status and limitations

Work in progress. The original documentation identifies unresolved element classifications, incomplete production verification, and demonstration prices that must not be used as contractual estimates. The owner confirmed rights to their work; model files and operational evidence remain excluded from this proposed source addition. Navisworks plugin compilation and hardware/software integration are unverified. Existing GitHub history will be retained alongside the addition.

## Screenshots, contributions and license

No verified demo or screenshots are supplied. Individual contributions and group ownership require confirmation. No new license is assigned; review existing notices and third-party rights before distribution.
