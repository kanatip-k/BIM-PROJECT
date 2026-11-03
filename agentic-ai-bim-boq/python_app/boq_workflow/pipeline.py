"""Pure deterministic stages for the BIM to BOQ workflow.

The Agent decides *when* to run this workflow.  These functions decide the
numbers.  Keeping calculation outside the LLM makes identical inputs and rule
versions produce identical BOQ results.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

MEASURE_KEYS = {
    "AREA": ("Element.Area", "Wall.Area", "Element Properties.Area"),
    "VOLUME": ("Element.Volume", "Wall.Volume", "Element Properties.Volume"),
    "LENGTH": ("Element.Length", "Element.Cut Length", "Wall.Length", "GeometryCurve.Length"),
    # TODO: confirm exported weight keys AND source units with a real weight takeoff.
    "WEIGHT": (),
}
UNITS = {"COUNT": "item", "LENGTH": "m", "AREA": "m2", "VOLUME": "m3", "WEIGHT": "kg"}
UNIT_MEASURE_TYPES = {"m³": "VOLUME", "m²": "AREA", "m": "LENGTH",
                      "kg": "WEIGHT", "kg/ton": "WEIGHT", "ton": "WEIGHT",
                      "nr": "COUNT", "item": "COUNT", "ชิ้น": "COUNT"}
# TODO: populate only after confirming IFC quantity basis, material scope and
# source units against a real export. CASE2_ST_ALL/CASE2_AR contain Element.*
# quantities but no IFC Qto keys: this is NOT evidence of Net/Gross equivalence.
# Keys are IFC source names; values are verified exported property key tuples.
QTO_PROPERTY_ALIASES: dict[str, tuple[str, ...]] = {}

# Canonical evidence fields from boq_element_rules.json mapped only to property
# keys observed in CASE2. An absent entry means that CASE2 has no confirmed,
# semantically equivalent property; it must remain missing rather than being
# satisfied by a similarly named value. Some aliases have field-specific
# validation in _evidence_alias_value_valid (for example, Element.Type proves a
# SectionSize only when it actually contains dimensions).
EVIDENCE_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ElementKey": ("Element Properties.UniqueId", "Element ID.Value"),
    "TypeCode": ("Element.Type",),
    "LevelZone": (
        "Level.Name", "Base Level.Name", "Reference Level.Name",
        "Schedule Level.Name", "Top Level.Name", "Element.Level",
        "Element.Base Level", "Element.Reference Level",
        "Element.Schedule Level", "Element.Top Level",
    ),
    "MaterialCode": (
        "Revit Material.Name", "Structural Material.Name",
        "Element.Structural Material", "Material.Name", "Item.Material",
    ),
    "ConcreteGrade": ("Revit Material.ConcreteCompression",),
    "Volume": ("Element.Volume", "Wall.Volume", "Element Properties.Volume"),
    "Area": ("Element.Area", "Wall.Area", "Element Properties.Area"),
    "Length": (
        "Element.Length", "Element.Cut Length", "Wall.Length",
        "GeometryCurve.Length", "GeometryCurve.ApproximateLength",
    ),
    "SectionSize": ("Element.Type",),
    "SteelGrade": (
        "Revit Material.MinimumYieldStress", "Structural Material.Name",
        "Element.Structural Material",
    ),
    "UnitMass": ("Element.Type",),
    "Width": ("Element.Width", "Element Properties.Width"),
    "Height": ("Element Properties.Height", "Element.Unconnected Height"),
    "Thickness": ("Element.Thickness", "Element Properties.Thickness", "WallType.Width"),
    "Diameter": ("Element.Type",),
}

EVIDENCE_FIELD_ALIAS_NOTES: dict[str, str] = {
    "ElementKey": "exported element id is primary; Revit UniqueId/numeric Element ID are observed fallbacks",
    "TypeCode": "Element.Type is the exported Revit type value",
    "LevelZone": "observed level references prove the Level part; CASE2 has no separate verified zone property",
    "MaterialCode": "observed material identifiers/names; presence audit does not validate project coding",
    "ConcreteGrade": "concrete compressive strength is exported explicitly in MPa",
    "Volume": "native exported volume property; source unit and net/gross basis remain unverified",
    "Area": "native exported area property; source unit and face/net/gross basis remain unverified",
    "Length": "native exported length property; source unit and measurement basis remain unverified",
    "SectionSize": "Element.Type counts only when it contains an explicit dimensional pattern such as 400x2450",
    "SteelGrade": "explicit yield stress or a numbered steel material designation",
    "UnitMass": "Element.Type counts only when it contains an explicit kg/m value; kN/m3 UnitWeight is excluded",
    "Width": "explicit exported width property",
    "Height": "explicit exported height property",
    "Thickness": "explicit exported thickness or wall type width property",
    "Diameter": "Element.Type counts only when it explicitly labels a diameter",
}

# Only codes/categories observed in the two CASE2 exports are listed. The
# scope dimension matters: B1010 means different work in ST and AR models.
CASE2_UNIFORMAT_CANDIDATES: dict[tuple[str, str, str], tuple[str, ...]] = {
    ("Structure", "A1010", "Structural Foundations"): ("S001", "S002", "S003", "S004", "S011"),
    ("Structure", "B1010", "Floors"): ("S007",),
    ("Structure", "B1011", "Structural Columns"): ("S005", "S031"),
    ("Structure", "B1012", "Structural Framing"): ("S006", "S031"),
    ("Structure", "C2010", "Stairs"): ("S009",),
    ("Structure", "C2010", "Runs"): ("S009",),
    ("Architecture", "B1010", "Floors"): ("A008", "A009", "A010", "A011"),
    ("Architecture", "B2010", "Generic Models"): ("A019", "A020"),
    ("Architecture", "B2020", "Windows"): ("A030",),
    ("Architecture", "C1020", "Doors"): ("A029",),
    ("Architecture", "C2010", "Stairs"): ("A021", "A022"),
    ("Architecture", "C2010", "Runs"): ("A021", "A022"),
    ("Architecture", "C2020", "Railings"): ("A024", "A025"),
    ("Architecture", "C3030", "Ceilings"): ("A012", "A013", "A014"),
}


def _case2_scope(model: str) -> str | None:
    stem = re.sub(r"\.[^.]+$", "", str(model).replace("\\", "/").rsplit("/", 1)[-1]).upper()
    if stem.startswith("CASE2_ST_"):
        return "Structure"
    if stem == "CASE2_AR" or stem.startswith("CASE2_AR_"):
        return "Architecture"
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(element: dict[str, Any]) -> str:
    props = element.get("properties") or {}
    return " ".join(
        str(v) for v in (
            element.get("display_name", ""), element.get("class_name", ""),
            element.get("ancestor_path", ""), element.get("uniformat_title", ""),
            *props.values(),
        )
    ).casefold()


def _is_eligible(element: dict[str, Any]) -> bool:
    explicit = element.get("boq_eligible")
    if explicit is not None:
        return bool(explicit)
    noise = ("solid", "family", "category", "room", "grid", "level", "type")
    text = f"{element.get('class_name', '')} {element.get('display_name', '')}".casefold()
    return bool(element.get("has_geometry")) and not any(x in text for x in noise)


def _normal(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _parse_number(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if ":" in text:
        text = text.split(":", 1)[1]
    text = text.replace(",", "")
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _measure(element: dict[str, Any], rule: str,
             property_keys: tuple[str, ...] | None = None) -> tuple[float | None, str | None]:
    if rule == "COUNT":
        return 1.0, "element instance"
    props = element.get("properties") or {}
    for key in property_keys if property_keys is not None else MEASURE_KEYS[rule]:
        if key in props:
            value = _parse_number(props[key])
            if value is not None:
                return value, key
    return None, None


def _infer_discipline(element: dict[str, Any], mapping: dict[str, Any], cost_code: str) -> tuple[str, str]:
    if element.get("element_discipline"):
        return element["element_discipline"], (element.get("element_discipline_source")
                                                 or element.get("element_rule_source")
                                                 or "element-category-structural")
    for rule in mapping.get("costCodeDisciplines", []):
        if any(cost_code.startswith(prefix) for prefix in rule["prefixes"]):
            return rule["discipline"], rule["id"]
    text = _text(element)
    for rule in mapping["disciplineRules"]:
        if any(word.casefold() in text for word in rule["keywords"]):
            return rule["discipline"], rule["id"]
    return "Architecture", "discipline-default-architecture"


def _cost_code(element: dict[str, Any], mapping: dict[str, Any]) -> tuple[str, str, str]:
    current = _normal(element.get("uniformat_code"))
    title = _normal(element.get("uniformat_title"))
    if current:
        return current, title or "UNIFORMAT element", "bim-uniformat"
    if "ifcslab" in _entity_names(element) and _subtype(element) == "BASESLAB":
        return "A10", "Foundations", "uniformat-baseslab-fallback"
    if "ifcfooting" in _entity_names(element):
        return "A1010", "Standard Foundations", "uniformat-foundation-fallback"
    text = _text(element)
    for rule in mapping["costCodeRules"]:
        if any(word.casefold() in text for word in rule["keywords"]):
            return rule["code"], rule["title"], rule["id"]
    return "UNCLASSIFIED", "Unclassified BIM element", "no-cost-code-match"


def _entity_names(element: dict[str, Any]) -> set[str]:
    """Read explicit IFC entities and entity names in exported class/category text."""
    props = element.get("properties") or {}
    text = " ".join(str(v) for v in (
        element.get("ifc_entity", ""), element.get("class_name", ""),
        props.get("Element.Category", ""),
        *(v for k, v in props.items() if "ifc" in k.casefold() and
          any(s in k.casefold() for s in ("entity", "class", "type"))
          and "predefined" not in k.casefold()),
    ))
    names = set(re.findall(r"\bIfc[A-Za-z]+\b", text, re.IGNORECASE))
    names = {name.casefold() for name in names}
    # Revit categories with direct entity equivalents. Do not infer a foundation
    # slab or a structural foundation's subtype from its category alone.
    for category, entity in {
        "footing": "ifcfooting", "walls": "ifcwall", "doors": "ifcdoor",
        "windows": "ifcwindow", "structural columns": "ifccolumn",
        "structural framing": "ifcbeam", "structural rebar": "ifcreinforcingbar",
        "pipes": "ifcpipesegment", "ducts": "ifcductsegment",
        "railings": "ifcrailing", "foundation slab": "ifcslab",
    }.items():
        if re.search(r"(?<!\w)" + re.escape(category) + r"s?(?!\w)", text, re.IGNORECASE):
            names.add(entity)
    return names


def _subtype(element: dict[str, Any]) -> str:
    raw = element.get("ifc_predefined_type") or element.get("predefined_type")
    if not raw:
        for key, value in (element.get("properties") or {}).items():
            if re.sub(r"[^a-z]", "", key.casefold()).endswith("predefinedtype"):
                raw = value
                break
    return _normal(raw).rsplit(":", 1)[-1].strip().strip('"').upper()


def _keyword_present(keyword: str, text: str) -> bool:
    if keyword.isascii():
        return bool(re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text))
    return keyword in text


def _is_unconfirmed_structural_wall(element: dict[str, Any]) -> bool:
    """Structural wall scope is explicit; its Type abbreviation is not resolved."""
    props = element.get("properties") or {}
    return (props.get("Element.Category") == "Walls"
            and _normal(props.get("Element.Structural")).casefold() == "true"
            and _normal(props.get("Element.Structural Usage") or
                        props.get("Element Properties.StructuralUsage")).casefold() == "bearing")


def _is_structural_curb(element: dict[str, Any]) -> bool:
    """Explicit no-spec item, based only on exported wall attributes."""
    return (_is_unconfirmed_structural_wall(element)
            and bool(re.search(r"(?<![A-Za-z])CURB(?![A-Za-z])",
                               _normal((element.get("properties") or {}).get("Element.Type")), re.IGNORECASE)))


def _scoped_rule_match(element: dict[str, Any], config: dict[str, Any], scope: str) -> dict[str, Any]:
    """Resolve only reviewed CASE2 UNIFORMAT/category/material combinations."""
    props = element.get("properties") or {}
    category = _normal(props.get("Element.Category"))
    code = _normal(element.get("uniformat_code"))
    family = _normal(props.get("Element.Family"))
    element_type = _normal(props.get("Element.Type"))
    selected = None
    issue_code = None
    candidates = list(CASE2_UNIFORMAT_CANDIDATES.get((scope, code, category), ()))
    if category in ("Floors", "Structural Foundations") and _normal(props.get("FloorType.IsFoundationSlab")).casefold() == "true":
        selected, candidates = "S004", ["S004"]
    elif category in ("Floors", "Structural Foundations") and family.casefold() == "foundation slab":
        candidates = ["S004", "S007"]
    elif scope == "Structure" and code == "A1010" and category == "Structural Foundations":
        if re.search(r"bored[ _-]*piles?", f"{family} {element_type}", re.IGNORECASE):
            selected = "S011"
        else:
            candidates = ["S001", "S002", "S003", "S011"]
    elif scope == "Structure" and code in ("B1011", "B1012") and category in ("Structural Columns", "Structural Framing"):
        material_type = _normal(props.get("Element Properties.StructuralMaterialType"))
        if material_type.casefold() == "steel":
            selected = "S031"
        elif material_type.casefold() == "concrete":
            selected = "S005" if code == "B1011" else "S006"
        elif not material_type:
            issue_code = "STRUCTURAL_MATERIAL_TYPE_MISSING"
    elif scope == "Structure" and code == "B1010" and category == "Floors":
        selected = "S007"
    elif scope == "Architecture" and (code, category) in (("C1020", "Doors"), ("B2020", "Windows")):
        selected = "A029" if category == "Doors" else "A030"
    # Other observed buckets remain candidates until a reviewed Family/Type
    # vocabulary distinguishes work items. Never assign the first candidate.
    if selected:
        for discipline, rules in config.get("elementRules", {}).items():
            for rule in rules:
                if rule["code"] == selected:
                    return {"element_code": selected, "work_group": rule["workGroup"],
                            "element_rule_source": selected, "element_match_source": "case2-uniformat-category",
                            "element_discipline": discipline, "element_rule": rule,
                            "element_rule_candidates": [], "element_match_issue_code": None}
    return {"element_code": None, "work_group": None, "element_rule_source": None,
            "element_match_source": None, "element_rule": None,
            "element_rule_candidates": candidates, "element_match_issue_code": issue_code,
            "element_discipline": scope, "element_discipline_source": "case2-model-scope"}


def _match_element_rule(element: dict[str, Any], config: dict[str, Any], scope: str | None = None) -> dict[str, Any]:
    if scope and _normal((element.get("properties") or {}).get("Element.Category")) != "Walls":
        return _scoped_rule_match(element, config, scope)
    entities = _entity_names(element)
    rows = [(discipline, rule) for discipline, rules in config.get("elementRules", {}).items()
            for rule in rules]
    candidates = [(discipline, rule) for discipline, rule in rows
                  if entities.intersection(name.casefold() for name in
                                           re.findall(r"\bIfc[A-Za-z]+\b", rule["ifcEntityRevitCategory"]))]
    subtype = _subtype(element)
    names = " ".join(str(v) for v in (
        element.get("display_name", ""), element.get("class_name", ""),
        *(v for k, v in (element.get("properties") or {}).items()
          if k.casefold().split(".")[-1] in ("name", "family", "type", "material", "boqcode")),
    )).casefold()
    selected = None
    source = None
    # Authoritative entity-specific enum mappings supplied for this workflow.
    if "ifcfooting" in entities and subtype in ("PAD_FOOTING", "STRIP_FOOTING", "PILE_CAP"):
        selected = {"PAD_FOOTING": "S001", "STRIP_FOOTING": "S002", "PILE_CAP": "S003"}[subtype]
        source = "ifc-predefined-type"
    elif "ifcslab" in entities and subtype == "BASESLAB":
        selected, source = "S004", "ifc-predefined-type"
    # Explicit BOQCode is a subtype/work-item identifier, not an EIT code guess.
    if selected is None:
        explicit = _normal((element.get("properties") or {}).get("BOQCode") or
                           (element.get("properties") or {}).get("Element.BOQCode"))
        if any(rule["code"] == explicit for _, rule in candidates):
            selected, source = explicit, "bim-boq-code"
    if selected is None and subtype not in ("", "NOTDEFINED", "USERDEFINED"):
        # Only accept subtype text that distinguishes one work item. Unknown
        # enums do not fall through to a guessed keyword interpretation.
        token = subtype.casefold().replace("_", " ")
        matches = [rule["code"] for _, rule in candidates
                   if _keyword_present(token, rule["elementWorkItem"].casefold())]
        if len(matches) == 1:
            selected, source = matches[0], "ifc-predefined-type"
    if selected is None and subtype in ("", "NOTDEFINED", "USERDEFINED"):
        hints = {
            "S001": ("pad footing", "isolated footing", "spread footing", "ฐานรากเดี่ยว", "ฐานแผ่"),
            "S002": ("strip", "แถบ"), "S003": ("pile cap", "หัวเข็ม", "หัวเสาเข็ม"),
            "S004": ("raft", "แพ"), "S005": ("concrete column", "คอนกรีตเสา"),
            "S006": ("concrete beam", "คอนกรีตคาน"),
            "S022": ("formwork footing", "แบบหล่อฐานราก"),
            "S028": ("precast pile", "driven pile", "เสาเข็มสำเร็จรูป", "ตอก"),
            "S031": ("steel beam", "steel column", "steel member", "เหล็กโครงสร้าง"),
        }
        scores = []
        for discipline, rule in candidates:
            phrases = hints.get(rule["code"], tuple(
                phrase.strip().casefold() for phrase in rule["elementWorkItem"].split("/")
                if len(phrase.strip()) > 2))
            score = max((len(phrase) for phrase in phrases if _keyword_present(phrase, names)), default=0)
            if score:
                scores.append((score, rule["code"]))
        # M045 is a contract/system item, often without a geometric IFC entity.
        if not candidates and any(_keyword_present(word, names) for word in
                                  ("testing", "commissioning", "balancing")):
            selected = "M045"
        elif scores:
            best = max(score for score, _ in scores)
            winners = [code for score, code in scores if score == best]
            if len(winners) == 1:
                selected = winners[0]
        if selected:
            source = "element-keyword-fallback"
    if selected is None and len(candidates) == 1:
        selected, source = candidates[0][1]["code"], "ifc-entity"
    if selected:
        discipline, rule = next((d, r) for d, r in rows if r["code"] == selected)
        return {"element_code": selected, "work_group": rule["workGroup"],
                "element_rule_source": selected, "element_match_source": source,
                "element_discipline": discipline, "element_rule": rule,
                "element_rule_candidates": []}
    codes = [rule["code"] for _, rule in candidates]
    if "ifcfooting" in entities and not any(word in names for word in ("formwork", "แบบหล่อ")):
        codes = ["S001", "S002", "S003"]
    return {"element_code": None, "work_group": None, "element_rule_source": None,
            "element_match_source": None, "element_rule": None,
            "element_rule_candidates": codes}


def _measurement_rule(element: dict[str, Any], discipline: str, rules: dict[str, Any],
                      use_element_rule: bool = True) -> dict[str, Any]:
    item = element.get("element_rule") if use_element_rule else None
    if item:
        code = item["code"]
        if code == "M045":
            return {"id": code, "measure": "MANUAL", "unit": item["boqUnit"]}
        if code == "S028":
            return {"id": code, "measure": "LENGTH", "unit": "m", "ambiguousUnit": True}
        measure = UNIT_MEASURE_TYPES.get(item["boqUnit"])
        if measure:
            return {"id": code, "measure": measure, "unit": item["boqUnit"]}
    text = _text(element)
    for rule in rules["rules"]:
        allowed = rule.get("disciplines", ["*"])
        if "*" not in allowed and discipline not in allowed:
            continue
        if any(word.casefold() in text for word in rule["keywords"]):
            return {**rule, "unit": UNITS[rule["measure"]], "unmappedUnit": bool(item)}
    rule = rules["defaultRule"]
    return {**rule, "unit": UNITS[rule["measure"]], "unmappedUnit": bool(item)}


def _qto_keys(item: dict[str, Any]) -> tuple[str, ...]:
    """Resolve only aliases verified for the quantity source in this item."""
    sources = re.findall(r"Qto_[A-Za-z0-9_]+\.[A-Za-z0-9_]+", item["bimMappingQuantitySource"])
    return tuple(dict.fromkeys(key for source in sources for key in QTO_PROPERTY_ALIASES.get(source, ())))


def _required_field_audit(element: dict[str, Any], rule: dict[str, Any], model: str,
                          roles: dict[str, Any]) -> dict[str, Any]:
    """Check evidence only; defer pipeline-produced fields to their stages."""
    props = element.get("properties") or {}
    explicit = element.get("required_field_values") or {}
    present: dict[str, str] = {}
    missing: list[str] = []
    pipeline_fields: dict[str, list[str]] = {}
    for field in rule.get("requiredFields", []):
        role = roles["fieldRoles"][field]
        if role["role"] == "pipeline-produced":
            pipeline_fields.setdefault(role["checkAfter"], []).append(field)
            continue
        candidates: list[tuple[str, Any]] = [(f"required_field_values.{field}", explicit.get(field)),
                                             (f"element.{field}", element.get(field)),
                                             (f"properties.{field}", props.get(field))]
        if field == "ElementKey":
            candidates.append(("element.id", element.get("id")))
        candidates.extend((f"properties.{key}", props.get(key))
                          for key in EVIDENCE_FIELD_ALIASES.get(field, ()))
        source = next((name for name, value in candidates
                       if _evidence_alias_value_valid(field, name, value)), None)
        if source:
            present[field] = source
        else:
            missing.append(field)
    return {"ruleId": rule["code"], "presentSources": present, "missingFields": missing,
            "requiredPipelineFields": pipeline_fields,
            "pipelineStageResults": {},
            "scope": "evidence presence-only; quantity basis and source units remain unverified"}


def _evidence_alias_value_valid(field: str, source: str, value: Any) -> bool:
    """Reject nonempty lookalikes that do not prove the canonical evidence field."""
    text = _normal(value)
    if not text:
        return False
    if source.startswith("required_field_values.") or source.startswith("element."):
        return True
    if field == "SectionSize" and source == "properties.Element.Type":
        return bool(re.search(r"\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?", text, re.IGNORECASE))
    if field == "UnitMass" and source == "properties.Element.Type":
        return bool(re.search(r"\d+(?:\.\d+)?\s*kg\s*/\s*m\b", text, re.IGNORECASE))
    if field == "Diameter" and source == "properties.Element.Type":
        return bool(re.search(r"(?:diameter|\bdia\.?\b|[Ø⌀])", text, re.IGNORECASE)
                    and re.search(r"\d", text))
    if field == "SteelGrade" and source in (
            "properties.Structural Material.Name", "properties.Element.Structural Material"):
        return bool(re.search(r"(?:steel|metal)", text, re.IGNORECASE) and re.search(r"\d", text))
    return True


def _quantified_pipeline_fields(measure: str, rule_id: str, basis: str) -> dict[str, str]:
    """Expose canonical pipeline-produced fields once QUANTIFY has produced them."""
    fields = {"RuleID": rule_id, "QuantityBasis": basis}
    basis_field = {
        "COUNT": "CountBasis", "LENGTH": "LengthBasis", "AREA": "AreaBasis",
        "VOLUME": "VolumeBasis", "WEIGHT": "WeightBasis",
    }.get(measure)
    if basis_field:
        fields[basis_field] = basis
    return fields


def _pipeline_field_check(element: dict[str, Any], audit: dict[str, Any],
                          stage: str, model: str) -> dict[str, Any]:
    """Check a produced field only after its designated workflow stage."""
    props = element.get("properties") or {}
    explicit = element.get("required_field_values") or {}
    present: dict[str, str] = {}
    missing: list[str] = []
    for field in audit["requiredPipelineFields"].get(stage, []):
        candidates = [(f"required_field_values.{field}", explicit.get(field)),
                      (f"element.{field}", element.get(field)),
                      (f"properties.{field}", props.get(field))]
        if field == "ModelFile":
            candidates.append(("workflow.model", model))
        source = next((name for name, value in candidates
                       if value is not None and str(value).strip() != ""), None)
        if source:
            present[field] = source
        else:
            missing.append(field)
    return {"presentSources": present, "missingFields": missing}


def _normalize_quantified_unit(unit: str | None, quantity: float | None) -> str | None:
    """Canonical output spelling at the QUANTIFY boundary; no numeric conversion."""
    if quantity is None:
        return None
    return {"m³": "m3", "m²": "m2", "nr": "item", "ชิ้น": "item"}.get(unit, unit)


def _type_name(element: dict[str, Any]) -> str:
    class_name = _normal(element.get("class_name"))
    if ":" in class_name:
        return class_name.rsplit(":", 1)[1].strip() or "Unnamed type"
    return _normal(element.get("display_name")) or class_name or "Unnamed type"


def _material(element: dict[str, Any]) -> str:
    props = element.get("properties") or {}
    for key in ("Element.Structural Material", "Material.Name", "Element.Material", "Item.Material"):
        raw = _normal(props.get(key))
        if not raw:
            continue
        quoted = re.search(r'"([^"]+)"', raw)
        if quoted:
            return quoted.group(1).strip()
        return raw.split(", #", 1)[0].strip()
    return "Unspecified"


def _price_for(code: str, discipline: str, unit: str, pricebook: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if code == "UNCLASSIFIED":
        return None, "unclassified-has-no-price"
    candidates: list[tuple[int, dict[str, Any]]] = []
    for entry in pricebook["entries"]:
        if entry["unit"] != unit:
            continue
        if entry.get("discipline", "*") not in ("*", discipline):
            continue
        prefix = entry.get("codePrefix", "*")
        if prefix == "*" or code.startswith(prefix):
            candidates.append((0 if prefix == "*" else len(prefix), entry))
    if not candidates:
        return None, "no-price-match"
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    entry = candidates[0][1]
    return entry, entry["id"]


def run_pipeline(
    model: str,
    raw_elements: list[dict[str, Any]],
    bundle: dict[str, dict[str, Any]],
    disciplines: list[str] | None = None,
) -> dict[str, Any]:
    """Run every stage and return one serializable, auditable result document."""
    mapping, measurement, pricebook = bundle["mapping"], bundle["measurement"], bundle["pricebook"]
    requested = set(disciplines or ["Structure", "Architecture", "MEP"])
    issues: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    stages: list[dict[str, Any]] = []

    def event(stage: str, input_count: int, output_count: int, message: str) -> None:
        item = {"stage": stage, "status": "COMPLETED", "inputCount": input_count,
                "outputCount": output_count, "message": message, "timestamp": _now()}
        stages.append(item)
        audit.append(dict(item))

    def check_pipeline_fields(stage: str, elements: list[dict[str, Any]]) -> None:
        for element in elements:
            field_audit = element.get("required_field_audit")
            if not field_audit or stage not in field_audit["requiredPipelineFields"]:
                continue
            result = _pipeline_field_check(element, field_audit, stage, model)
            field_audit["pipelineStageResults"][stage] = result
            if result["missingFields"]:
                issues.append({"severity": "error", "code": "PIPELINE_FIELD_UNRESOLVED",
                               "elementId": element.get("id"), "ruleId": field_audit["ruleId"],
                               "stage": stage, "missingFields": result["missingFields"],
                               "message": "workflow ยังไม่สร้าง required field หลัง stage ที่กำหนด"})

    acquired: list[dict[str, Any]] = []
    for index, element in enumerate(raw_elements):
        missing = []
        if not _normal(element.get("id")):
            missing.append("id")
        if not _normal((element.get("properties") or {}).get("Element.Category")):
            missing.append("Element.Category")
        if missing:
            issues.append({"severity": "warning", "code": "GROUP_NODE_EXCLUDED",
                           "elementId": element.get("id") or f"input:{index}",
                           "missingAttributes": missing,
                           "message": "ตัด hierarchy/group node ที่ไม่มี id หรือ Element.Category ก่อน CLASSIFY"})
            continue
        if _is_eligible(element):
            acquired.append(element)
    event("ACQUIRE", len(raw_elements), len(acquired), "อ่านเฉพาะ BIM instances ที่มี id และ Element.Category")

    validated: list[dict[str, Any]] = []
    for element in acquired:
        reference = element.get("id") or f"row:{element.get('rowid_pk')}"
        if not _normal(element.get("display_name")) and not _normal(element.get("class_name")):
            issues.append({"severity": "error", "code": "MISSING_NAME", "elementId": reference,
                           "message": "ไม่มีชื่อหรือ class สำหรับจัดหมวดงาน"})
            continue
        if not element.get("has_geometry"):
            issues.append({"severity": "warning", "code": "NO_GEOMETRY", "elementId": reference,
                           "message": "องค์ประกอบไม่มี geometry แต่ยังสามารถนับจำนวนได้"})
        item = dict(element)
        if not _is_unconfirmed_structural_wall(element):
            match = _match_element_rule(element, bundle.get("elementRules", {}), _case2_scope(model))
            item["_preclassified"] = match
            if match["element_rule"]:
                field_audit = _required_field_audit(element, match["element_rule"], model,
                                                    bundle["fieldRoles"])
                item["required_field_audit"] = field_audit
                if field_audit["missingFields"]:
                    issues.append({"severity": "error", "code": "REQUIRED_FIELD_MISSING",
                                   "elementId": reference, "ruleId": match["element_code"],
                                   "missingFields": field_audit["missingFields"],
                                   "message": "requiredFields ไม่มีหลักฐานใน export/workflow; ไม่เติมค่าศูนย์หรือเดา alias"})
        validated.append(item)
    event("VALIDATE", len(acquired), len(validated), "ตรวจชื่อ class geometry และข้อมูลขั้นต่ำ")

    normalized: list[dict[str, Any]] = []
    for element in validated:
        item = dict(element)
        item["display_name"] = _normal(item.get("display_name"))
        item["class_name"] = _normal(item.get("class_name"))
        item["properties"] = {_normal(k): _normal(v) for k, v in (item.get("properties") or {}).items()}
        normalized.append(item)
    event("NORMALIZE", len(validated), len(normalized), "ปรับช่องว่าง ชื่อ และ property text ให้อยู่ในรูปแบบเดียวกัน")
    check_pipeline_fields("ACQUIRE", normalized)
    check_pipeline_fields("NORMALIZE", normalized)

    classified: list[dict[str, Any]] = []
    eit_mapping = {row["code"]: row for row in bundle.get("eitMapping", {}).get("mappings", [])}
    for element in normalized:
        preclassified = element.pop("_preclassified", None)
        unconfirmed_wall = _is_unconfirmed_structural_wall(element)
        structural_curb = unconfirmed_wall and _is_structural_curb(element)
        if unconfirmed_wall:
            exclusion = "ELEMENT_TYPE_NOT_IN_SPEC" if structural_curb else "TYPE_ABBREVIATION_UNCONFIRMED"
            element = {**element, "element_code": None, "work_group": None,
                       "element_rule_source": None, "element_match_source": None,
                       "element_rule": None, "element_rule_candidates": [],
                       "element_discipline": "Structure",
                       "element_discipline_source": "element-structural-bearing",
                       "excluded_reason": exclusion}
            code, title, mapping_source = ("UNCLASSIFIED", "Unconfirmed structural wall type",
                                           "rejected-exported-wall-code")
        else:
            element = {**element, **(preclassified or _match_element_rule(element, bundle.get("elementRules", {}),
                                                                       _case2_scope(model)))}
            code, title, mapping_source = _cost_code(element, mapping)
        discipline, discipline_source = _infer_discipline(element, mapping, code)
        if discipline not in requested:
            continue
        reference = element.get("id") or f"row:{element.get('rowid_pk')}"
        eit = eit_mapping.get(element["element_code"])
        eit_code = eit.get("eitSubGroupCode") if eit and eit.get("matchStatus") == "matched" else None
        if structural_curb:
            issues.append({"severity": "warning", "code": "ELEMENT_TYPE_NOT_IN_SPEC",
                           "elementId": reference, "message": "CURB ไม่มี element code ในสเปก; ไม่สร้าง BOQ quantity",
                           "elementType": element["properties"].get("Element.Type")})
        elif unconfirmed_wall:
            issues.append({"severity": "warning", "code": "TYPE_ABBREVIATION_UNCONFIRMED",
                           "elementId": reference, "message": "ยังไม่ยืนยันความหมาย Type ของผนัง Structure จากแบบหรือทีมโมเดล",
                           "elementType": element["properties"].get("Element.Type")})
        elif element["element_code"] is None:
            issue_code = element.get("element_match_issue_code") or "NO_ELEMENT_RULE_MATCH"
            message = ("ไม่มี Element Properties.StructuralMaterialType สำหรับแยกงานเหล็ก/คอนกรีต"
                       if issue_code == "STRUCTURAL_MATERIAL_TYPE_MISSING"
                       else "ไม่พบ rule หรือข้อมูลชนิดย่อยไม่พอแยกรายการ BOQ")
            issues.append({"severity": "warning", "code": issue_code, "elementId": reference,
                           "message": message,
                           "candidateCodes": element["element_rule_candidates"]})
        elif eit_code is None:
            issues.append({"severity": "warning", "code": "EIT_COSTCODE_NEEDS_CONFIRMATION",
                           "elementId": reference, "ruleId": element["element_code"],
                           "message": eit.get("note", "ไม่มี EIT mapping") if eit else "ไม่มี EIT mapping"})
        if element["element_match_source"] == "element-keyword-fallback":
            issues.append({"severity": "warning", "code": "ELEMENT_CODE_FROM_KEYWORD_FALLBACK",
                           "elementId": reference, "ruleId": element["element_code"],
                           "message": "จับคู่ชนิดงานจากชื่อ family/type ต้องยืนยันกับแบบและ IFC subtype"})
        if code == "UNCLASSIFIED" and not unconfirmed_wall:
            issues.append({"severity": "warning", "code": "UNCLASSIFIED", "elementId": element.get("id") or f"row:{element.get('rowid_pk')}",
                           "message": "ไม่พบ UNIFORMAT Cost Code จากโมเดลหรือ mapping rules"})
        classified.append({**element, "discipline": discipline, "discipline_source": discipline_source,
                           "BOQCode": element["element_code"],
                           "cost_code": code, "uniformat_cost_code": None if unconfirmed_wall else code,
                           "exported_uniformat_code": _normal(element.get("uniformat_code")) or None,
                           "eit_cost_code": eit_code,
                           "primary_cost_code": None if unconfirmed_wall else (eit_code or code),
                           "cost_title": title, "mapping_source": mapping_source})
    event("CLASSIFY", len(normalized), len(classified), "จัดหมวด element rules และเก็บ EIT คู่กับ UNIFORMAT")
    check_pipeline_fields("CLASSIFY", classified)

    measured: list[dict[str, Any]] = []
    for element in classified:
        if element.get("excluded_reason") in ("ELEMENT_TYPE_NOT_IN_SPEC", "TYPE_ABBREVIATION_UNCONFIRMED"):
            continue
        # Classification issues remain visible in ``classifiedElements`` and
        # the issue summary, but an unresolved work item must never become a
        # priced BOQ line.  There is no defensible quantity/rate key without an
        # element code.
        if element.get("element_code") is None:
            continue
        rule = _measurement_rule(element, element["discipline"], measurement)
        reference = element.get("id") or f"row:{element.get('rowid_pk')}"
        item = element.get("element_rule")
        if rule["measure"] == "MANUAL":
            issues.append({"severity": "error", "code": "MANUAL_LINE_ITEM_NOT_AUTO_COMPUTABLE",
                           "elementId": reference, "ruleId": rule["id"],
                           "message": "ต้องกรอกปริมาณ Testing/Commissioning ตามขอบเขตสัญญา ไม่มีสูตร geometry"})
            basis = "manual-contract-scope"
            measured.append({**element, "measurement_rule": "MANUAL", "rule_id": rule["id"],
                             "quantity": None, "unit": rule["unit"], "quantity_source": None,
                             "quantity_basis_source": basis,
                             **_quantified_pipeline_fields("MANUAL", rule["id"], basis)})
            continue
        if item and item["code"] == "S031":
            issues.append({"severity": "error", "code": "WEIGHT_UNIT_UNVERIFIED",
                           "elementId": reference, "ruleId": "S031",
                           "message": "ยังไม่ยืนยันหน่วย Length ดิบและฐานน้ำหนัก kg/m; ไม่คำนวณน้ำหนักเหล็ก"})
            basis = "unit-unverified"
            measured.append({**element, "measurement_rule": "WEIGHT", "rule_id": "S031",
                             "quantity": None, "unit": rule["unit"], "quantity_source": None,
                             "quantity_basis_source": basis,
                             **_quantified_pipeline_fields("WEIGHT", "S031", basis)})
            continue
        if rule.get("ambiguousUnit"):
            issues.append({"severity": "warning", "code": "UNIT_BASIS_AMBIGUOUS",
                           "elementId": reference, "ruleId": rule["id"],
                           "message": "ใช้ความยาวจาก BIM; ต้องยืนยันราคาต่อเมตรหรือต่อต้นจาก pricebook/สัญญา"})
        if rule.get("unmappedUnit"):
            issues.append({"severity": "warning", "code": "UNIT_NOT_MAPPED",
                           "elementId": reference, "ruleId": item["code"],
                           "message": f"ยังไม่มีวิธีวัดหน่วย {item['boqUnit']}; ใช้ measurement rule เดิม"})
        source_basis = "legacy-measurement-rule"
        if item and not rule.get("unmappedUnit") and rule["measure"] != "COUNT":
            quantity, source_key = _measure(element, rule["measure"], _qto_keys(item))
            source_basis = "verified-qto-alias"
            if quantity is None:
                issues.append({"severity": "warning", "code": "ELEMENT_RULE_UNIT_NOT_FOUND",
                               "elementId": reference, "ruleId": rule["id"],
                               "message": "ไม่มี property alias ที่ยืนยันสำหรับ element rule; ตรวจ export และ quantity basis ก่อนใช้งานจริง"})
                fallback = _measurement_rule(element, element["discipline"], measurement, False)
                # A length/count fallback cannot stand in for mass, area or
                # volume. Retain the element rule's measure type and read the
                # legacy keys for that type, without dimensional substitution.
                if fallback["measure"] == rule["measure"]:
                    fallback_source = fallback["id"]
                else:
                    fallback_source = "legacy-measure-keys"
                quantity, source_key = _measure(element, rule["measure"])
                source_basis = fallback_source
        else:
            quantity, source_key = _measure(element, rule["measure"])
        if quantity is None or quantity < 0:
            issues.append({"severity": "error", "code": "MISSING_MEASURE", "elementId": reference,
                           "message": f"กฎ {rule['measure']} ต้องใช้ property ปริมาณที่โมเดลไม่มี",
                           "ruleId": rule["id"]})
            continue
        measured.append({**element, "measurement_rule": rule["measure"], "rule_id": rule["id"],
                         "quantity": round(quantity, 6), "unit": rule["unit"],
                         "quantity_source": source_key, "quantity_basis_source": source_basis,
                         **_quantified_pipeline_fields(rule["measure"], rule["id"], source_basis)})
    for element in measured:
        element["unit"] = _normalize_quantified_unit(element["unit"], element["quantity"])
    event("QUANTIFY", len(classified), len(measured), "ใช้ Count Length Area Volume Weight และปรับชื่อหน่วยส่งออกให้ตรงกัน")
    check_pipeline_fields("QUANTIFY", measured)

    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for element in measured:
        key = (element["discipline"], element["cost_code"], element["cost_title"],
               _type_name(element), _material(element), element["measurement_rule"], element["unit"], element["rule_id"],
               element["element_code"], element["eit_cost_code"])
        line = grouped.setdefault(key, {
            "discipline": key[0], "costCode": key[1], "title": key[2], "type": key[3],
            "material": key[4], "measurementRule": key[5], "unit": key[6], "ruleId": key[7],
            "quantity": 0.0, "elementCount": 0, "quantitySources": [],
            "mappingSources": [], "evidenceElementIds": [],
            "elementCode": element["element_code"], "eitCostCode": element["eit_cost_code"],
            "uniformatCostCode": element["uniformat_cost_code"], "workGroup": element["work_group"],
        })
        if element["quantity"] is None:
            line["quantity"] = None
        elif line["quantity"] is not None:
            line["quantity"] += element["quantity"]
        line["elementCount"] += 1
        source = element.get("quantity_source")
        if source and source not in line["quantitySources"]:
            line["quantitySources"].append(source)
        mapping_source = element.get("mapping_source")
        if mapping_source and mapping_source not in line["mappingSources"]:
            line["mappingSources"].append(mapping_source)
        line["evidenceElementIds"].append(element.get("id") or f"row:{element.get('rowid_pk')}")

    lines: list[dict[str, Any]] = []
    for line in grouped.values():
        if line["quantity"] is not None:
            line["quantity"] = round(line["quantity"], 3)
            price, price_source = _price_for(line["costCode"], line["discipline"], line["unit"], pricebook)
        else:
            price, price_source = None, "quantity-unresolved"
        if price is None:
            line.update({"materialRate": None, "laborRate": None, "equipmentRate": None,
                         "unitRate": None, "totalCost": None, "priceSource": price_source})
            if line["quantity"] is not None:
                issues.append({"severity": "warning", "code": "MISSING_PRICE", "costCode": line["costCode"],
                               "message": f"ไม่พบราคาสาธิตสำหรับ {line['costCode']} หน่วย {line['unit']}"})
        else:
            material_rate = float(price.get("materialRate", 0))
            labor_rate = float(price.get("laborRate", 0))
            equipment_rate = float(price.get("equipmentRate", 0))
            unit_rate = material_rate + labor_rate + equipment_rate
            line.update({"materialRate": material_rate, "laborRate": labor_rate,
                         "equipmentRate": equipment_rate, "unitRate": unit_rate,
                         "totalCost": round(line["quantity"] * unit_rate, 2), "priceSource": price_source})
        lines.append(line)
    lines.sort(key=lambda x: (x["discipline"], x["costCode"], x["type"], x["unit"] or ""))
    event("PRICE", len(grouped), len(lines), "จับคู่ pricebook สาธิตและคำนวณ Quantity x Unit Rate")

    duplicate_ids = sum(count - 1 for value, count in Counter(
        e.get("id") for e in measured if e.get("id")
    ).items() if count > 1)
    if duplicate_ids:
        issues.append({"severity": "warning", "code": "DUPLICATE_ELEMENT_ID", "count": duplicate_ids,
                       "message": "พบ InstanceGuid ซ้ำ ระบบใช้ row id เป็นหลักฐานเสริม"})
    event("VERIFY", len(lines), len(lines), "ตรวจราคาหาย ปริมาณติดลบ รหัสซ้ำ และความสอดคล้องของยอดรวม")

    # Many elements can produce the same issue.  Group them so the UI remains
    # readable while preserving a count and representative element ids.
    grouped_issues: dict[tuple[Any, ...], dict[str, Any]] = {}
    for issue in issues:
        key = (issue.get("severity"), issue.get("code"), issue.get("message"),
               issue.get("ruleId"), issue.get("costCode"), issue.get("elementType"), issue.get("stage"),
               tuple(issue.get("candidateCodes", [])), tuple(issue.get("missingFields", [])),
               tuple(issue.get("missingAttributes", [])))
        summary = grouped_issues.setdefault(key, {
            k: v for k, v in issue.items() if k != "elementId"
        } | {"count": 0, "exampleElementIds": []})
        summary["count"] += int(issue.get("count", 1))
        reference = issue.get("elementId")
        if reference and len(summary["exampleElementIds"]) < 20:
            summary["exampleElementIds"].append(reference)
    issues = list(grouped_issues.values())

    priced = [line for line in lines if line["totalCost"] is not None]
    totals = {
        "lineCount": len(lines), "pricedLineCount": len(priced),
        "unpricedLineCount": len(lines) - len(priced),
        "elementCount": sum(line["elementCount"] for line in lines),
        "totalCost": round(sum(line["totalCost"] for line in priced), 2),
        "currency": pricebook.get("currency", "THB"),
    }
    event("GENERATE", len(lines), len(lines), "สร้าง BOQ summary quality issues และ audit trail")

    return {
        "status": "COMPLETED_WITH_ISSUES" if issues else "COMPLETED",
        "model": model,
        "versions": {"mapping": mapping["version"], "measurement": measurement["version"],
                     "pricebook": pricebook["version"],
                     **{key: bundle[key]["version"] for key in ("elementRules", "eitReference", "eitMapping")
                        if key in bundle}},
        "stages": stages,
        "summary": totals,
        "boq": {"lines": lines, "totals": totals, "currency": totals["currency"],
                "disclaimer": pricebook["disclaimer"]},
        "issues": issues,
        "elements": [{k: v for k, v in element.items() if k != "element_rule"} for element in measured],
        "classifiedElements": [{k: v for k, v in element.items() if k != "element_rule"} for element in classified],
        "auditTrail": audit,
    }
