"""
inspect_json.py — แสดง element ตัวอย่าง 3 ตัวแรกจาก JSON เพื่อดูว่า properties มีอะไรบ้าง
"""
import json
from pathlib import Path

LOG = Path(__file__).parent / "inspect_result.txt"

def log(msg):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

LOG.unlink(missing_ok=True)

json_path = Path(__file__).resolve().parent.parent / "data" / "export" / "CASE2_AR.json"
log(f"Reading {json_path} ...")

with json_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

elements = data["elements"]
log(f"Total elements: {len(elements)}")
log("")

# Show first 3 elements in full detail
for i, el in enumerate(elements[:3]):
    log(f"--- Element {i+1} ---")
    log(f"  id: {el.get('id')}")
    log(f"  displayName: {el.get('displayName')}")
    log(f"  classDisplayName: {el.get('classDisplayName')}")
    log(f"  hasGeometry: {el.get('hasGeometry')}")
    props = el.get("properties", {})
    log(f"  properties ({len(props)} keys):")
    for k, v in list(props.items())[:30]:
        log(f"    {k}: {v}")
    log("")

# Show unique classDisplayName values
class_names = {}
for el in elements:
    cn = el.get("classDisplayName", "(none)")
    class_names[cn] = class_names.get(cn, 0) + 1

log("classDisplayName distribution:")
for name, count in sorted(class_names.items(), key=lambda x: -x[1])[:20]:
    log(f"  {name}: {count}")

# Show all unique property key prefixes (category names)
prefixes = {}
for el in elements[:500]:  # sample first 500
    for k in el.get("properties", {}).keys():
        prefix = k.split(".")[0]
        prefixes[prefix] = prefixes.get(prefix, 0) + 1

log("")
log("Property category prefixes (sample of first 500 elements):")
for name, count in sorted(prefixes.items(), key=lambda x: -x[1]):
    log(f"  {name}: {count}")

log("")
log("=== DONE ===")
