# คู่มือเปิดระบบเพื่อ Demo: Navisworks → MCP → Web

เอกสารนี้ใช้สำหรับเปิดระบบใหม่หลังปิดเครื่อง โดยระบบจะอ่านข้อมูลจากโมเดล Navisworks จริงผ่าน Navisworks .NET API ส่งผ่าน MCP และแสดงบน Web Dashboard

## สิ่งที่ระบบทำ

```text
Navisworks Model
    ↓
Navis MCP Bridge Plug-in
    ↓
Local Bridge: http://127.0.0.1:8765
    ↓
MCP Tool: get_navisworks_elements
    ↓
Web Dashboard: http://127.0.0.1:8000
```

MCP ไม่ได้อ่านไฟล์ Navisworks โดยตรง ปลั๊กอิน C# จะอ่านโมเดลผ่าน Navisworks .NET API ก่อน แล้ว MCP จึงเรียกข้อมูลจาก Bridge อีกทอดหนึ่ง

---

## ก่อนเริ่ม Demo

ตรวจสอบว่ามีสิ่งต่อไปนี้:

- Autodesk Navisworks Manage 2027
- โมเดล `.NWD`, `.NWF` หรือ `.NWC` ที่ต้องการสาธิต
- โปรเจกต์อยู่ที่ `D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype`
- ปลั๊กอินอยู่ที่ `D:\Navisworks Manage 2027\Plugins\NavisMcpBridge\NavisMcpBridge.dll`

> สำหรับการดึงข้อมูลจริง ห้ามเปิด `bridge_mock.py` เพราะ Mock Bridge และปลั๊กอิน Navisworks ใช้พอร์ต 8765 เดียวกัน

---

## ขั้นตอนเปิดระบบหลังเปิดคอมใหม่

### 1. เปิด Navisworks

เปิด **Autodesk Navisworks Manage 2027** แล้วเปิดโมเดลที่ต้องการ Demo

ตัวอย่างโมเดลที่เคยทดสอบ:

```text
D:\BIM-PROJECT\Case Study\Case2\01_ARCHITECTURE\02_NWC\CASE2_AR.nwc
```

รอให้โมเดลแสดงใน Navisworks เรียบร้อยก่อนดำเนินการต่อ

### 2. สร้าง Snapshot จากโมเดลจริง

ใน Navisworks ไปที่:

```text
Add-Ins → Navis MCP Bridge
```

ปลั๊กอินจะแสดงความคืบหน้า 2 ช่วง:

1. `Counting model elements...` — กำลังนับจำนวน Element ทั้งหมด
2. `Reading element properties...` — แสดงจำนวนที่อ่านแล้วและเปอร์เซ็นต์

รอจนขึ้นข้อความ:

```text
Navisworks snapshot ready.
```

เมื่อเสร็จแล้วต้องเปิด Navisworks ค้างไว้ตลอดการ Demo

### 3. เปิด Web Server

เปิด PowerShell หรือ Terminal ใหม่ แล้วใช้คำสั่งต่อไปนี้ทีละบรรทัด:

```powershell
cd D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype\python_app
.\.venv\Scripts\Activate.ps1
uvicorn web_app:app --reload --port 8000
```

ถ้าสำเร็จ Terminal จะแสดงประมาณนี้:

```text
Uvicorn running on http://127.0.0.1:8000
```

ปล่อย Terminal นี้เปิดค้างไว้

> ไม่ต้องเปิด `mcp_server.py` แยก เพราะ Web Backend จะเปิด MCP Server และเรียก MCP Tool ให้อัตโนมัติ

### 4. เปิด Dashboard

เปิด Browser ที่:

```text
http://127.0.0.1:8000
```

หน้าเว็บจะโหลดข้อมูลอัตโนมัติ หรือกด **Refresh from MCP** อีกครั้งก็ได้

---

## วิธีตรวจว่าเป็นข้อมูล Navisworks จริง

บน Dashboard ให้ตรวจสอบข้อมูลต่อไปนี้:

```text
Data source: Autodesk Navisworks .NET API
Model file: ชื่อโมเดลจริงที่เปิดอยู่
Transport: Navisworks Bridge -> MCP Tool
```

ถ้าขึ้น `Navisworks Bridge Demo` หรือ `Demo_Model.nwd` แสดงว่าระบบกำลังใช้ Mock Data ให้หยุด `bridge_mock.py` แล้วกด **Navis MCP Bridge** ใน Navisworks ใหม่

Dashboard แยกจำนวนเป็น 2 ค่า:

- **Total elements** คือจำนวน Element ทั้งหมดใน Snapshot
- **Loaded to web** คือจำนวนที่ MCP ส่งมาให้เว็บในรอบนั้น ปัจจุบันจำกัดไว้ 1,000 รายการเพื่อไม่ให้ Browser ค้าง

ตัวอย่างผลทดสอบกับ `CASE2_AR.nwc`:

```text
Total elements: 70,030
Loaded to web: 1,000
```

---

## สิ่งที่สาธิตบน Dashboard ได้

- ดูชื่อโมเดลและจำนวน Element
- ค้นหาจากชื่อ, Element ID, Class, Category และ Properties
- กรองข้อมูลตาม Class
- กรองข้อมูลตาม Category
- เลือกแสดง 25, 50 หรือ 100 แถวต่อหน้า
- กด **ดู Properties** เพื่อดู Property ทั้งหมดของ Element
- แสดง Category, Level และจำนวน Properties แยกเป็นคอลัมน์

---

## หากเปลี่ยนหรือแก้ไขโมเดล

Snapshot จะไม่เปลี่ยนเอง ถ้ามีการแก้โมเดลหรือเปิดไฟล์ใหม่ ให้ทำดังนี้:

1. กลับไปที่ Navisworks
2. กด **Add-Ins → Navis MCP Bridge** อีกครั้ง
3. รอจน Snapshot เสร็จ 100%
4. กลับมาที่ Dashboard
5. กด **Refresh from MCP**

Snapshot ใหม่จะแทน Snapshot เก่าใน RAM แต่ไม่แก้ไขหรือลบข้อมูลภายในโมเดล Navisworks

---

## วิธีปิดระบบหลัง Demo

1. ที่ Terminal ของ Web Server กด `Ctrl+C`
2. ปิด Browser
3. ปิด Navisworks

เมื่อปิด Navisworks Snapshot ที่อยู่ใน RAM จะหายไป ครั้งถัดไปต้องกด **Navis MCP Bridge** เพื่ออ่านโมเดลใหม่

---

## แก้ปัญหาที่พบบ่อย

### เปิดเว็บไม่ได้

ตรวจว่า Terminal แสดง:

```text
Uvicorn running on http://127.0.0.1:8000
```

และตรวจว่าเรียกคำสั่งจากโฟลเดอร์ `python_app`

### เว็บขึ้น 500 หรือเชื่อมต่อไม่สำเร็จ

ตรวจตามลำดับ:

1. Navisworks ยังเปิดอยู่หรือไม่
2. เปิดโมเดลแล้วหรือไม่
3. กด **Navis MCP Bridge** และอ่านเสร็จแล้วหรือไม่
4. เผลอเปิด `bridge_mock.py` อยู่หรือไม่

### Navis MCP Bridge ไม่ปรากฏใน Add-Ins

ตรวจไฟล์:

```text
D:\Navisworks Manage 2027\Plugins\NavisMcpBridge\NavisMcpBridge.dll
```

จากนั้นปิดและเปิด Navisworks ใหม่

### Navisworks ดูเหมือนค้างระหว่างอ่าน

ดูหน้าต่าง Progress ของปลั๊กอิน:

- ช่วงนับ Element จะแสดงจำนวนที่พบ
- ช่วงอ่าน Properties จะแสดงเปอร์เซ็นต์
- หากต้องการหยุด ให้กด **Cancel**

โมเดลขนาดใหญ่อาจใช้เวลาหลายนาที แต่ไม่ควรกดปลั๊กอินซ้ำระหว่างที่กำลังอ่าน

### หน้าเว็บยังเป็นหน้ารูปแบบเก่า

กด:

```text
Ctrl+F5
```

เพื่อบังคับให้ Browser โหลดหน้าใหม่

### พอร์ต 8765 ถูกใช้งานอยู่

สาเหตุที่พบบ่อยคือ `bridge_mock.py` ยังเปิดอยู่ ให้กลับไปที่ Terminal ของ Mock Bridge แล้วกด `Ctrl+C` จากนั้นกด **Navis MCP Bridge** ใหม่

---

## ลำดับสั้น ๆ ก่อนเริ่มนำเสนอ

```text
1. เปิด Navisworks Manage 2027
2. เปิดโมเดลจริง
3. Add-Ins → Navis MCP Bridge
4. รอ Snapshot 100%
5. เปิด Terminal และรัน Web Server
6. เปิด http://127.0.0.1:8000
7. ตรวจ Source และชื่อโมเดล
8. ทดลองค้นหา กรอง และเปิดดู Properties
```

---

## คำอธิบายสำหรับอาจารย์

> ระบบนี้ไม่ได้อ้างว่า Navisworks มี MCP ในตัวครับ เราพัฒนาปลั๊กอินด้วย Navisworks .NET API เพื่ออ่าน Elements และ Properties จากโมเดลจริง จากนั้นเปิดข้อมูลผ่าน Local Bridge และสร้าง MCP Tool ชื่อ `get_navisworks_elements` ให้ Web หรือ AI เรียกใช้งาน ปัจจุบันสามารถดึงข้อมูลโมเดลจริงผ่านเส้นทาง Navisworks → Bridge → MCP → Web Dashboard ได้แล้วครับ

## สถานะปัจจุบัน

- อ่าน Element และ Properties จาก Navisworks จริงได้
- มี Progress และเปอร์เซ็นต์ระหว่างสร้าง Snapshot
- ส่งข้อมูลผ่าน MCP Tool ได้
- แสดงข้อมูลบน Dashboard พร้อมค้นหา กรอง แบ่งหน้า และดู Properties ได้
- Snapshot ยังเก็บใน RAM และหายเมื่อปิด Navisworks
- หน้าเว็บโหลดสูงสุด 1,000 Elements ต่อรอบในเวอร์ชันปัจจุบัน
