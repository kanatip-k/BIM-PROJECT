"""Load the small, versioned rule files used by the educational prototype."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path(__file__).resolve().parent / "config"


@lru_cache(maxsize=8)
def load_json(name: str) -> dict[str, Any]:
    path = _CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or not data.get("version"):
        raise ValueError(f"Invalid workflow configuration: {path}")
    return data


def load_bundle() -> dict[str, dict[str, Any]]:
    bundle = {
        "mapping": load_json("mapping_rules.json"),
        "measurement": load_json("measurement_rules.json"),
        "pricebook": load_json("demo_pricebook.json"),
        "elementRules": load_json("boq_element_rules.json"),
        "eitReference": load_json("eit_cost_code_reference.json"),
        "eitMapping": load_json("boq_to_eit_mapping.json"),
        "fieldRoles": load_json("field_roles.json"),
    }
    dictionary_fields = {row["fieldName"] for row in bundle["elementRules"]["dataDictionary"]}
    if set(bundle["fieldRoles"]["fieldRoles"]) != dictionary_fields:
        raise ValueError("Field roles must cover every element rule dataDictionary field exactly once")
    return bundle
