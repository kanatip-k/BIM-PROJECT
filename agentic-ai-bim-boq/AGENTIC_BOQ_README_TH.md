# Agentic BIM-to-BOQ Prototype

โฟลเดอร์นี้รวมระบบเดิม `Navisworks Headless Export -> JSON Bridge -> MCP -> Web`
กับ BOQ workflow ที่พัฒนาจาก task brief โดยไม่ต้องเปิด Navisworks ระหว่างใช้งาน
Dashboard หลังจาก export เสร็จแล้ว

## เปิดระบบ

1. ถ้ามีไฟล์ NWC/NWD ใหม่ ให้วางใน `data/` แล้วรัน `run_export.ps1`
2. รัน `start.ps1`
3. เลือก JSON ที่ลงท้าย `.boq.json` หรือ JSON ที่สร้างด้วย exporter รุ่นปัจจุบัน
4. เปิด `http://127.0.0.1:8000`
5. กด **สร้าง BOQ** หรือพิมพ์คำสั่งในช่อง Agent

ผลแต่ละรอบถูกบันทึกใน `data/boq_results/` และดาวน์โหลด CSV ได้จาก Dashboard
MCP server รวม tools เดิมของ MERGED และ tools BOQ ทั้งหมด:

- `get_health`
- `get_navisworks_elements`
- `get_category_type_summary`
- `run_boq_workflow`
- `get_boq_workflow_result`
- `list_boq_workflows`

ไฟล์ `python_app/agent_client.py` เดิมยังทำงานแบบ Anthropic tool-use และจะค้นพบ
BOQ tools ใหม่อัตโนมัติเมื่อเชื่อมต่อ MCP ส่วน Agent ในหน้าเว็บใช้ local workflow router
จึงทดลองได้โดยไม่ต้องตั้ง API key

## ขอบเขตที่ใช้งานได้ตอนนี้

- ACQUIRE กรอง group node ที่ไม่มี `id` หรือ `Element.Category`
- VALIDATE/NORMALIZE ตรวจหลักฐานจาก property จริงโดยใช้ evidence aliases
- CLASSIFY ใช้ exported UNIFORMAT ร่วมกับ scope/category/material และ guard ที่ตกลงไว้
- QUANTIFY รองรับ Count/Length/Area/Volume ตาม measurement rule และไม่สร้าง BOQ line
  เมื่อ `element_code` ยัง resolve ไม่ได้
- PRICE ใช้ `demo_pricebook.json` เพื่อสาธิตเท่านั้น
- VERIFY/GENERATE สร้าง issue summary, audit trail, JSON และ CSV

## ข้อจำกัดที่ยังตั้งใจคงไว้

- Structure Walls ที่เป็น LB/SW/WR/WTB ยังเป็น
  `TYPE_ABBREVIATION_UNCONFIRMED`; CURB เป็น `ELEMENT_TYPE_NOT_IN_SPEC`
- Architecture Floors ยังไม่เดาวัสดุปูพื้นและคง `element_code=null`
- S031 ยังไม่คำนวณน้ำหนักจนกว่าจะยืนยันหน่วย Length และ kg/m
- ยังไม่มี CASE2 MEP export สำหรับยืนยัน mapping จริง
- Phase 5 project rules และ Phase 6 production verification ยังไม่ implement
- ราคาที่แสดงเป็นข้อมูลสาธิต ไม่ใช่ราคาสัญญาหรือราคากลางสำหรับใช้งานจริง

JSON รุ่นเก่า `data/export/CASE2_AR.json` ไม่มี `id` และ `Element.Category` ระบบจะ
ปฏิเสธด้วย `LEGACY_EXPORT_SCHEMA` แทนการสร้าง BOQ ว่างแบบเงียบ ๆ ให้ใช้ไฟล์
`.boq.json` ที่แนบไว้หรือ export ใหม่ด้วย `run_export.ps1`

## การทดสอบ

```powershell
python -m pytest tests -q
python tests\integration_probe.py
```

`integration_probe.py` ตรวจทั้ง REST API, CSV export และ stdio MCP tools ด้วย sample
ที่คัดจาก CASE2 จริง
