# การเชื่อม Headless JSON เข้ากับ MCP และ Web Dashboard

## ภาพรวม

```text
ไฟล์ NWD / NWF / NWC
        ↓
NavisHeadlessRunner.exe
        ↓
CASE2_AR.json
        ↓
json_bridge.py : พอร์ต 8765
        ↓
mcp_server.py : MCP Tool
        ↓
web_app.py : พอร์ต 8000
        ↓
Web Dashboard
```

หลังจากสร้าง JSON แล้ว ไม่จำเป็นต้องเปิด Navisworks ระหว่างเปิด Dashboard แต่เครื่องยังต้องมี Navisworks สำหรับการสร้าง JSON รุ่นใหม่

## เปิดระบบ

ห้ามเปิด `bridge_mock.py` และควรปิด Navisworks Plug-in Bridge เพราะใช้พอร์ต 8765 เดียวกัน

### Terminal 1 — เปิด JSON Bridge

```powershell
cd "D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype\python_app"

$env:NAVIS_JSON_PATH="D:\BIM-PROJECT\Case Study\Case2\01_ARCHITECTURE\03_EXPORT\CASE2_AR.json"

& ".\.venv\Scripts\python.exe" -m uvicorn json_bridge:app --host 127.0.0.1 --port 8765
```

ทดสอบใน Browser:

```text
http://127.0.0.1:8765/health
```

ต้องเห็น `status` เป็น `ok` และ `elementCount` เป็น `33755`

### Terminal 2 — เปิด Web Dashboard

```powershell
cd "D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype\python_app"

& ".\.venv\Scripts\python.exe" -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

เปิด:

```text
http://127.0.0.1:8000
```

แล้วกด **Refresh from MCP**

## การทำงานของแต่ละส่วน

### Headless Runner

เปิด Navisworks แบบ `NoGui`, อ่านโมเดลผ่าน C# Plug-in และเขียน Snapshot เป็น JSON เมื่อส่งออกเสร็จ Navisworks จะปิดอัตโนมัติ

### JSON Bridge

อ่าน JSON ขนาดใหญ่ครั้งแรกและเก็บไว้ใน RAM จากนั้นส่งเฉพาะช่วงข้อมูลที่ร้องขอ รองรับ:

```text
/api/elements?limit=1000&offset=0
```

ถ้าไฟล์ JSON ถูกสร้างใหม่ Bridge จะตรวจเวลาแก้ไขและ Reload ให้อัตโนมัติในการเรียกครั้งถัดไป

### MCP Server

เปิด Tool ชื่อ `get_navisworks_elements` รับค่า `limit` และ `offset` แล้วเรียก JSON Bridge ก่อนส่งผลกลับ Web Backend จำกัดสูงสุด 5,000 รายการต่อคำขอ

### Web Backend

เมื่อ Browser เรียก `/api/model` ระบบจะเปิด MCP Client ผ่าน stdio, เรียก Tool และส่ง JSON กลับหน้า Dashboard

## การอัปเดตโมเดล

1. รัน Headless Runner กับไฟล์ NWC/NWD รุ่นใหม่
2. ให้เขียนทับไฟล์ `CASE2_AR.json`
3. กลับหน้าเว็บและกด Refresh from MCP
4. JSON Bridge จะ Reload ไฟล์ใหม่โดยอัตโนมัติ

## ข้อควรทราบ

- JSON ปัจจุบันประมาณ 161 MB และมี 33,755 รายการ การเปิด Bridge ครั้งแรกอาจใช้เวลาหลายวินาที
- Dashboard โหลด 1,000 รายการแรก แต่แสดงจำนวนรวมจาก `elementCount`
- ข้อมูลยังถูกกรองด้วย `HasGeometry = true` และอาจมีรายการระดับ Solid; ก่อนทำ BOQ จริงควรปรับกฎกรองให้เหลือ BIM Elements ระดับที่ต้องการ
- ถ้าพอร์ต 8765 ถูกใช้งาน ให้ปิด `bridge_mock.py`, Navisworks Bridge หรือโปรเซสเดิมก่อน
