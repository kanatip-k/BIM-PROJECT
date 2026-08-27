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

@app.get("/api/elements")
def elements():
    return SAMPLE

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
