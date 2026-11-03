import json
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse


# โฟลเดอร์ data/export/ ที่อยู่ระดับเดียวกับ python_app/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_EXPORT_DIR = _PROJECT_ROOT / "data" / "export"

MAX_PAGE_SIZE = 5000


def _find_default_json() -> Path:
    """หา JSON ล่าสุดใน data/export/ อัตโนมัติ ถ้าไม่ได้ set NAVIS_JSON_PATH"""
    if _DATA_EXPORT_DIR.is_dir():
        candidates = sorted(
            (p for p in _DATA_EXPORT_DIR.glob("*.json")
             if not p.name.casefold().endswith((".status.json", ".manifest.json"))),
            key=lambda p: (
                p.name.casefold().endswith(".classified-source.json"),
                p.name.casefold().endswith(".boq.json"),
                p.stat().st_mtime,
            ),
            reverse=True,
        )
        if candidates:
            return candidates[0]
    # fallback path เดิม
    return Path(
        r"D:\BIM-PROJECT\Case Study\Case2\01_ARCHITECTURE\03_EXPORT\CASE2_AR.json"
    )


class JsonSnapshotStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._payload: dict[str, Any] | None = None
        self._modified_ns: int | None = None

    def _read_file(self) -> tuple[dict[str, Any], int]:
        if not self.path.is_file():
            raise FileNotFoundError(f"Navisworks JSON file not found: {self.path}")

        modified_ns = self.path.stat().st_mtime_ns

        with self.path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)

        if not isinstance(payload, dict):
            raise ValueError("The Navisworks JSON root must be an object")

        elements = payload.get("elements")
        if not isinstance(elements, list):
            raise ValueError("The Navisworks JSON must contain an elements array")

        payload["elementCount"] = int(payload.get("elementCount", len(elements)))
        return payload, modified_ns

    def ensure_loaded(self) -> dict[str, Any]:
        with self._lock:
            current_modified_ns = (
                self.path.stat().st_mtime_ns if self.path.is_file() else None
            )

            if (
                self._payload is None
                or current_modified_ns is None
                or current_modified_ns != self._modified_ns
            ):
                self._payload, self._modified_ns = self._read_file()

            return self._payload

    def summary(self) -> dict[str, Any]:
        payload = self.ensure_loaded()
        elements = payload["elements"]

        return {
            "status": "ok",
            "jsonPath": str(self.path),
            "modelName": payload.get("modelName", self.path.name),
            "elementCount": payload.get("elementCount", len(elements)),
            "loadedInMemory": len(elements),
            "snapshotUtc": payload.get("snapshotUtc", ""),
        }

    def category_type_summary(self) -> dict[str, Any]:
        """
        รวมยอด element ทั้งหมด กลุ่มตาม Element.Category + Element.Type ในคำเรียกเดียว —
        เทียบเท่า count_items(group_by=[Category,Type]) ของ AUTOM8LABS แต่ทำฝั่ง Bridge
        เพื่อไม่ต้องส่ง element ทั้งหมด (อาจหลักแสน) ผ่าน HTTP ทุกครั้งที่ต้องการแค่ยอดรวม
        """
        payload = self.ensure_loaded()
        elements = payload["elements"]

        counts: dict[tuple[str, str], int] = {}
        no_category = 0
        for el in elements:
            props = el.get("properties", {})
            category = props.get("Element.Category")
            if not category:
                no_category += 1
                continue
            type_name = props.get("Element.Type") or props.get("Item.Type") or "<none>"
            key = (category, type_name)
            counts[key] = counts.get(key, 0) + 1

        groups = [
            {"category": cat, "type": typ, "count": cnt}
            for (cat, typ), cnt in sorted(counts.items(), key=lambda kv: -kv[1])
        ]
        classifiable = sum(g["count"] for g in groups)

        return {
            "totalElementsInFile": len(elements),
            "classifiableElements": classifiable,
            "elementsWithoutCategory": no_category,
            "distinctGroups": len(groups),
            "groups": groups,
        }

    def page(self, limit: int, offset: int) -> dict[str, Any]:
        payload = self.ensure_loaded()
        elements = payload["elements"]
        selected = elements[offset : offset + limit]

        result = {key: value for key, value in payload.items() if key != "elements"}
        result.update(
            {
                "elements": selected,
                "elementCount": payload.get("elementCount", len(elements)),
                "returnedCount": len(selected),
                "offset": offset,
                "limit": limit,
                "hasMore": offset + len(selected) < len(elements),
                "source": payload.get(
                    "source", "Autodesk Navisworks .NET API (NoGui)"
                ),
                "transport": "Headless JSON -> JSON Bridge",
                "jsonPath": str(self.path),
            }
        )
        return result


_env_path = os.environ.get("NAVIS_JSON_PATH", "")
json_path = Path(_env_path) if _env_path else _find_default_json()
store = JsonSnapshotStore(json_path)

app = FastAPI(title="Navisworks Headless JSON Bridge")


@app.get("/health")
def health() -> JSONResponse:
    try:
        return JSONResponse(store.summary())
    except Exception as exc:
        return JSONResponse(
            {
                "status": "error",
                "jsonPath": str(store.path),
                "error": str(exc),
            },
            status_code=503,
        )


@app.get("/api/elements")
def elements(
    limit: int = Query(default=1000, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    try:
        return JSONResponse(store.page(limit=limit, offset=offset))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not load Navisworks JSON: {exc}",
        ) from exc


@app.get("/api/summary")
def summary() -> JSONResponse:
    try:
        return JSONResponse(store.category_type_summary())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not summarize Navisworks JSON: {exc}",
        ) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
