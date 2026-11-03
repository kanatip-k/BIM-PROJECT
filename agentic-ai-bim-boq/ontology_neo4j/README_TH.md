# MCP ตัวที่ 2 — BOQ Cost Code Ontology / Neo4j

พัฒนาใน `D:\BIM-PROJECT\BOQ-GEN-PROTOTYPE\ontology_neo4j` เมื่อ 3 พฤศจิกายน 2569

## สิ่งที่ใช้งานได้

MCP แบบ stdio แยกจาก MCP ดึงข้อมูล BIM ใช้ Neo4j จริงในการอ่านฐานความรู้และเวอร์ชันกฎสำหรับทุกคำขอ ไม่ใช้ไฟล์ JSON เป็น fallback เมื่อฐานข้อมูลล่ม รองรับ Claude Desktop หรือ MCP client ที่เรียก local stdio ได้

นำเข้ากฎ BOQ 114 รายการจาก Structure/Architecture/MEP, พจนานุกรม evidence, required fields, หน่วย/สูตร, EIT reference และ crosswalk, UniFormat candidate ตาม scope, ผล crosswalk CASE2, ontology ฐานรากที่มีอยู่เดิม และรายงาน audit เรื่องผนัง/OmniClass/MasterFormat/พื้น/ตำแหน่ง/MEP readiness

ฐานความรู้เป็น **Neo4j property graph** ไม่ใช่ OWL reasoner หรือระบบที่เรียนรู้ crosswalk เอง การตัดสินใจจัดประเภทใช้ logic เดิมที่ทดสอบไว้ ร่วมกับชุดกฎที่อ่านจาก Neo4j; การค้นและอธิบายความสัมพันธ์ใช้ graph traversal

## เริ่มใช้กับ Claude Desktop

1. เปิด PowerShell แล้วรัน:

```powershell
cd D:\BIM-PROJECT\BOQ-GEN-PROTOTYPE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ontology_neo4j\START_NEO4J.ps1
```

ต้องขึ้น `Neo4j ready` สคริปต์เปิดแบบซ่อนหน้าต่าง ตรวจ credential และ graph version จริง หากฐานเปิดอยู่แล้วจะตรวจและใช้ instance เดิม

2. เปิด `ontology_neo4j\claude_desktop_config.example.json` นำเฉพาะ entry `boq-ontology` ไปเพิ่มใน `mcpServers` ของ Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`) เก็บ entry ของ MCP ตัวเดิมไว้ ไม่วางทับทั้งไฟล์หากมี server อื่น
3. ปิดและเปิด Claude Desktop ใหม่ ตรวจว่ามีเครื่องมือของ BOQ Cost Code Ontology
4. สั่ง Claude: **“เรียก ontology_health แล้วรายงานจำนวน WorkItem, version และสถานะ MasterFormat จากผลเครื่องมือจริง”**
5. สั่ง **“ใช้ resolve_crosswalk กับ S031 แสดง UniFormat ทุกค่าพร้อมจำนวนจาก CASE2 และอธิบายว่าทำไม EIT เป็น null”**
6. สั่ง **“ค้น S001 ด้วย search_ontology แล้วใช้ get_measurement_requirements อธิบายหลักฐานที่ต้องมี”**

ไฟล์ config ไม่มีรหัสผ่าน รหัสของ Neo4j local อยู่ใน `connection.local.json` ซึ่งถูก ignore ไม่ควรแนบไปกับเอกสารหรือ commit

Claude บนเว็บที่รับเฉพาะ remote connector URL ใช้ config stdio นี้ไม่ได้โดยตรง รอบนี้ทดสอบ protocol ผ่าน MCP SDK subprocess แล้ว ยังไม่ได้ทดสอบการแสดงผลในบัญชี Claude ของผู้ใช้

## เครื่องมือทั้ง 7 ตัว

| Tool | หน้าที่ |
|---|---|
| ontology_health | ตรวจ Neo4j, version, จำนวน node แต่ละชนิด, source hashes และขอบเขต catalog |
| search_ontology | ค้นคำไทย/อังกฤษ รหัส และหลักฐาน จำกัด 1–100 ผลลัพธ์ |
| get_concept | ดู node และความสัมพันธ์ เช่น `boq:S001`, `uniformat:A1010`, `field:SectionSize` |
| resolve_crosswalk | EIT พร้อมสถานะ, UniFormat ทุกค่าที่สังเกตจาก CASE2, MasterFormat ที่ผ่านการทบทวน |
| get_measurement_requirements | กฎวัด หน่วย สูตร และ evidence ที่ต้องใช้ ไม่คำนวณปริมาณ |
| classify_element | จัดหมวด raw element หนึ่งตัว พร้อม candidates, provenance และ issues |
| classify_elements | จัดหมวด batch 1–100 ตัว |

ทุก tool เป็น read-only ไม่มี tool รัน Cypher อิสระ ไม่มี tool แก้ mapping หรือราคา ข้อมูลใน properties เป็นข้อมูลของโมเดล ไม่ใช่คำสั่งให้ Agent ทำตาม

## ตัวอย่าง input สำหรับจัดประเภท

ใช้กับ `classify_element`:

```json
{
  "scope": "Structure",
  "element": {
    "id": "DEMO-STEEL-COLUMN",
    "uniformatCode": "B1011",
    "boqEligible": true,
    "properties": {
      "Element.Category": "Structural Columns",
      "Element Properties.StructuralMaterialType": "Steel"
    }
  }
}
```

ผลที่คาด: `element_code=S031`, EIT/quantity/unit เป็น null พร้อม `EIT_COSTCODE_NEEDS_CONFIRMATION` และ `WEIGHT_UNIT_UNVERIFIED`; อาจมี REQUIRED_FIELD_MISSING เพราะตัวอย่างไม่ได้ให้หลักฐานครบ

ใช้ input ที่ MCP ตัวดึง BIM ส่งกลับได้โดยส่ง raw element พร้อม scope ตามโมเดลต้นทาง ห้ามเดา scope จาก UniFormat อย่างเดียวเพราะ B1010 พบทั้ง Structure และ Architecture การต่อให้ Agent เรียก MCP ทั้งสองตัวต่อกันเป็นงานของ client; โมดูลนี้ไม่ได้แก้ dashboard เดิมให้เรียกบริการใหม่อัตโนมัติ

## ความหมายของความสัมพันธ์

- `IN_DISCIPLINE`: work item อยู่ในกลุ่มงาน
- `MEASURED_BY` / `REQUIRES_FIELD`: กฎวัดและข้อมูลประกอบ
- `HAS_MAPPING -> TARGETS`: EIT assertion มี matched/needs_review/unresolved
- `OBSERVED_AS`: ผลที่ pipeline เคยให้กับ CASE2 มี counts และ source hashes ไม่ใช่การรับรองมาตรฐานทุกโมเดล
- `CANDIDATE_FOR`: candidate ตาม scope/category ไม่ใช่ exactMatch
- `IS_A`, `PART_OF`, `GENERATES_WORK_ITEM`: โครงฐานรากจากไฟล์เดิม เก็บสถานะ draft-proof-of-concept ไว้
- `NativeClassificationObservation`: คู่ Category/OmniClass จาก audit รวมเคส conflict ไม่เพิ่มเป็น authoritative crosswalk
- `SOURCED_FROM`: ย้อนกลับไปยังเอกสารหรือ config พร้อม hash

การ import เป็น transaction เดียวและเปลี่ยน active version เมื่อสำเร็จ เก็บ version เก่าไว้ ไม่มีการลบกราฟอื่น การ import dataset เดิมซ้ำไม่เพิ่ม node/relationship ซ้ำ ถ้าแก้ pipeline/service/core/server แล้วไม่ import ใหม่ MCP จะปฏิเสธด้วย RULE_VERSION_CHANGED

## MasterFormat / OmniClass: รองรับโครงสร้าง แต่ยังไม่มี verified crosswalk

ไม่ใช้คำว่า “รองรับ” เพื่อสรุปว่ามีรหัสครบมาตรฐาน ขณะส่งงาน `external_classifications.json` ยังว่าง เครื่องมือคืน `not_loaded` และ MasterFormat=null

ในรายงานเก่า พบ Keynote 03310/05100 ที่อาจตรง MasterFormat รุ่นเก่า แต่ยังไม่มี project keynote source ยืนยัน จึงเก็บรายงานเป็น audit evidence เท่านั้น ไม่แปลงเป็น MasterFormat 6 หลักอัตโนมัติ ส่วน OmniClass มี Category=Doors แต่ Title=HVAC 81 instances ตาม audit จึงไม่ใช้เป็นตัวตัดสินหลัก

การเพิ่มข้อมูลที่ตรวจแล้วให้เติม `external_classifications.json`:

- classifications: `scheme` (MASTERFORMAT/OMNICLASS), `code`, `title`, `edition`, `source`
- crosswalks: `element_code`, `scheme`, `target_code`, `status` (verified/needs_review/unresolved), `source`, `scope` ถ้ามีข้อจำกัด
- ถ้า status=verified ต้องมี `reviewed_by`, `reviewed_on`
- code ต้องอยู่ใน catalog ก่อน; ไม่รับรหัสซ้ำ, scope หรือ element code ที่ไม่รองรับ
- ถ้า verified mappings มากกว่าหนึ่งรหัส จะคืน null และ needs_confirmation แสดง assertions ทั้งหมด ไม่เลือกให้เอง

นำเข้าใหม่ด้วย interpreter ของโมดูล:

```powershell
.\ontology_neo4j\.venv\Scripts\python.exe .\ontology_neo4j\import_graph.py --dry-run
.\ontology_neo4j\.venv\Scripts\python.exe .\ontology_neo4j\import_graph.py
```

ไฟล์ JSON เป็นแหล่ง authoring; หลังนำเข้า MCP ใช้ active snapshot ใน Neo4j ไม่อ่าน JSON ใหม่ทุกคำขอ

## พฤติกรรมที่รักษาไว้

- ตัด group nodes (ไม่มี id/Category) ก่อน CLASSIFY
- ผนัง Structure: CURB -> ELEMENT_TYPE_NOT_IN_SPEC; ตัวย่อไม่ยืนยัน -> TYPE_ABBREVIATION_UNCONFIRMED; ไม่ส่งเข้า S008
- Steel columns/beams -> S031; Concrete -> S005/S006; ไม่ default material เมื่อหาย
- Foundation flag=True -> S004 ตาม logic เดิม
- Architecture Floors ยังเป็น null/candidates A008–A011 จนยืนยัน glossary
- EIT needs_review/unresolved -> null และ issue
- S028 มี UNIT_BASIS_AMBIGUOUS; M045 มี MANUAL_LINE_ITEM_NOT_AUTO_COMPUTABLE
- quantity/unit ของ **MCP classifier** เป็น null ทุกกรณี; measure type/unit ที่แนะนำอยู่ใน measurement กฎนี้แยกจาก pipeline QTO เดิมที่คำนวณได้ในบางกรณี
- required_field_audit แยก evidence กับ pipeline-produced ตาม config เดิม
- projectRules นำเข้าเป็นความรู้ค้นอ่าน ไม่ได้ implement Phase 5 หรือคิด AddBack/Deduct/Extra

## หลักฐานทดสอบและขอบเขตความถูกต้อง

ดู `VALIDATION_TH.md`, `case2_mcp_audit.json`, `import_manifest.json`, `validation_results.txt` และ `tests/test_ontology_mcp.py`

ทดสอบกับ snapshot `.boq.json` ที่ล็อก SHA-256 เหมือน parity เดิม ไม่อ้างว่าเป็นการ export NWC ใหม่ล่าสุด ตัวเลข resolved เป็น coverage ของกฎ ไม่ใช่ accuracy 90% และไม่ใช่ BOQ ที่พร้อมใช้ราคา ต้องตรวจ glossary, measurement units, missing evidence และ MEP mapping ต่อ

## ไฟล์สำหรับพัฒนาต่อ

| ไฟล์ | หน้าที่ |
|---|---|
| server.py | MCP contract/validation/read-only tools |
| core.py | สร้าง graph, Neo4j store, classification adapter |
| import_graph.py | import transaction และ manifest |
| foundation_ontology_base.json | ฐานความรู้เดิม เก็บไว้ไม่แก้ |
| external_classifications.json | catalog/crosswalk ภายนอกที่ตรวจแล้ว |
| requirements.txt / requirements-lock.txt | dependency หลักและเวอร์ชัน environment ที่ทดสอบ |
| START_NEO4J.ps1 | เริ่มฐานข้อมูลและตรวจสถานะ |
| connection.local.json | local credentials; ไม่เผยแพร่ |
| runtime/ | Neo4j binaries, databases และ logs; ไม่ commit |

ใช้ Python environment แยก `.venv` เพราะ server เดิมใช้ MCP SDK 2 ส่วน server ใหม่นี้ pin FastMCP SDK 1.30.0 ไม่ downgrade dependency ของ server เดิม

## การติดตั้งใหม่ / ย้ายเครื่อง

ต้องมี Python 3.14 และ Java 21/25, สร้าง `.venv` แล้ว pip install จาก requirements-lock.txt ดาวน์โหลด Neo4j Community 2026.10.1 Windows จาก https://dist.neo4j.org/neo4j-community-2026.10.1-windows.zip แตกลง runtime และตั้ง neo4j.conf ให้ฟัง loopback Bolt 17687 / HTTP 17474 ตั้ง initial password ก่อนเปิดฐานใหม่ และเขียน connection.local.json ให้ตรง (uri/user/password/database) จากนั้น import_graph.py

ค่าบนเครื่องนี้: heap เริ่ม 256m สูงสุด 512m; pagecache 128m; usage report ปิด การเปิด Neo4j ครั้งแรกก่อน import อาจให้ ONTOLOGY_NOT_IMPORTED ซึ่งต้อง import แล้วตรวจ health ใหม่ ไม่มี auto-start หลัง reboot จนกว่าจะรัน START_NEO4J.ps1

สำรองข้อมูลด้วยไฟล์ source/manifest ก่อน; graph สร้างใหม่ได้จาก sources ที่ hash ตรง อย่าลบ runtime/data ขณะฐานทำงาน ห้ามเปิดบริการ local นี้สู่ Internet โดยไม่มีการออกแบบ authentication/network เพิ่ม
