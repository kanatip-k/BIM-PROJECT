from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Mock Navisworks Bridge")

SAMPLE = {
    "source": "Navisworks Bridge Demo",
    "modelName": "Demo_Model.nwd",
    "snapshotUtc": "DEMO",
    "elementCount": 5,
    "elements": [
        {
            "id": "1001",
            "displayName": "Basic Wall - 200mm",
            "classDisplayName": "Wall",
            "properties": {
                "Item.Name": "Basic Wall - 200mm",
                "Element.Category": "Walls",
                "Element.Level": "Level 1",
                "Dimensions.Length": "5200 mm",
                "Dimensions.Height": "3000 mm"
            }
        },
        {
            "id": "1002",
            "displayName": "Concrete Column 400x400",
            "classDisplayName": "Column",
            "properties": {
                "Item.Name": "Concrete Column 400x400",
                "Element.Category": "Structural Columns",
                "Element.Level": "Level 1"
            }
        },
        {
            "id": "1003",
            "displayName": "Floor 150mm",
            "classDisplayName": "Floor",
            "properties": {
                "Element.Category": "Floors",
                "Element.Level": "Level 1",
                "Dimensions.Thickness": "150 mm"
            }
        },
        {
            "id": "1004",
            "displayName": "Door D01",
            "classDisplayName": "Door",
            "properties": {
                "Element.Category": "Doors",
                "Element.Level": "Level 1",
                "Dimensions.Width": "900 mm"
            }
        },
        {
            "id": "1005",
            "displayName": "Pipe 100mm",
            "classDisplayName": "Pipe",
            "properties": {
                "Element.Category": "Pipes",
                "System.Type": "Domestic Cold Water",
                "Dimensions.Diameter": "100 mm"
            }
        }
    ]
}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "jsonPath": "(mock)",
        "modelName": SAMPLE["modelName"],
        "elementCount": SAMPLE["elementCount"],
        "loadedInMemory": len(SAMPLE["elements"]),
        "snapshotUtc": SAMPLE["snapshotUtc"],
    }


@app.get("/api/elements")
def elements():
    return SAMPLE


@app.get("/api/summary")
def summary():
    counts = {}
    no_category = 0
    for el in SAMPLE["elements"]:
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
    return {
        "totalElementsInFile": len(SAMPLE["elements"]),
        "classifiableElements": sum(g["count"] for g in groups),
        "elementsWithoutCategory": no_category,
        "distinctGroups": len(groups),
        "groups": groups,
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
