# คู่มือติดตั้งและรัน Navisworks MCP Web Prototype บนเครื่องใหม่

เอกสารนี้สำหรับเครื่อง Windows ที่ยังไม่เคยติดตั้งหรือรันโปรเจกต์นี้มาก่อน ตั้งแต่คัดลอกโปรเจกต์ ติดตั้งปลั๊กอิน สร้าง Python environment ไปจนถึงเปิด Dashboard และตรวจว่าข้อมูลมาจาก Navisworks จริง

## ภาพรวมระบบ

```text
Navisworks Manage 2027
        ↓
Navis MCP Bridge Plug-in (.NET Framework 4.8)
        ↓
Local Bridge: http://127.0.0.1:8765/api/elements
        ↓
MCP Server: get_navisworks_elements
        ↓
FastAPI Web Backend
        ↓
Dashboard: http://127.0.0.1:8000
```

MCP ไม่ได้เปิดหรืออ่านไฟล์ Navisworks โดยตรง ปลั๊กอิน C# จะอ่านข้อมูลจาก Navisworks .NET API และเก็บ Snapshot ไว้ใน RAM ก่อน จากนั้น MCP Server จึงเรียกข้อมูลผ่าน Local Bridge

---

## 1. โปรแกรมที่ต้องมี

เครื่องใหม่ต้องมี:

1. Windows 10 หรือ Windows 11 แบบ 64-bit
2. Autodesk Navisworks Manage 2027
3. Python 3.11–3.13 แบบ 64-bit
4. Internet สำหรับติดตั้ง Python packages ครั้งแรก
5. Browser เช่น Microsoft Edge หรือ Google Chrome

> DLL ที่ให้มาในโปรเจกต์คอมไพล์กับ `Autodesk.Navisworks.Api.dll` ของ Navisworks Manage 2027 หากใช้ Navisworks เวอร์ชันอื่นต้องคอมไพล์ปลั๊กอินใหม่กับ API ของเวอร์ชันนั้น

ตรวจสอบ Python:

```powershell
py --version
```

หรือ:

```powershell
python --version
```

ถ้าไม่พบคำสั่ง ให้ติดตั้ง Python จากเว็บไซต์ทางการและเลือก **Add Python to PATH** ระหว่างติดตั้ง

---

## 2. คัดลอกโปรเจกต์

คัดลอกโฟลเดอร์ทั้งหมดไปยังเครื่องใหม่ เช่น:

```text
D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype
```

โครงสร้างที่ต้องมี:

```text
Navisworks_MCP_Web_Prototype\
├── navisworks_plugin\
│   ├── NavisMcpBridge.dll
│   ├── NavisMcpBridgePlugin.cs
│   └── NavisMcpBridge.csproj
├── python_app\
│   ├── bridge_mock.py
│   ├── mcp_server.py
│   ├── requirements.txt
│   ├── web_app.py
│   └── templates\
│       └── index.html
└── README_NEW_MACHINE_TH.md
```

### อย่าคัดลอก `.venv` มาใช้ข้ามเครื่อง

Python virtual environment มี path และ executable ที่ผูกกับเครื่องเดิม ให้สร้าง `.venv` ใหม่ตามขั้นตอนถัดไป แม้ในโฟลเดอร์ที่คัดลอกมาจะมี `.venv` อยู่แล้วก็ไม่ควรนำมาใช้

---

## 3. สร้าง Python environment ใหม่

เปิด PowerShell แล้วเข้าโฟลเดอร์ `python_app`:

```powershell
cd D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype\python_app
```

สร้าง virtual environment:

```powershell
py -m venv .venv
```

ติดตั้งและอัปเดต `pip`:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
```

ติดตั้ง packages จากไฟล์ของโปรเจกต์:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

Packages หลักที่ติดตั้ง:

```text
mcp
fastapi
uvicorn
httpx
jinja2
```

ตรวจสอบว่าติดตั้งครบ:

```powershell
& ".\.venv\Scripts\python.exe" -c "import mcp, fastapi, uvicorn, httpx, jinja2; print('Python dependencies OK')"
```

ผลที่ถูกต้อง:

```text
Python dependencies OK
```

---

## 4. ติดตั้ง Navisworks Plug-in

ไฟล์ปลั๊กอินที่พร้อมใช้อยู่ที่:

```text
<PROJECT>\navisworks_plugin\NavisMcpBridge.dll
```

### 4.1 หาโฟลเดอร์ติดตั้ง Navisworks

ตำแหน่งปกติคือ:

```text
C:\Program Files\Autodesk\Navisworks Manage 2027
```

หากติดตั้งไว้ไดรฟ์อื่น ให้ค้นหาไฟล์:

```text
Roamer.exe
```

โฟลเดอร์ที่มี `Roamer.exe` คือโฟลเดอร์ติดตั้ง Navisworks

### 4.2 ปิด Navisworks ก่อนติดตั้ง

ถ้า Navisworks เปิดอยู่ DLL จะถูกล็อกและคัดลอกทับไม่ได้ ให้บันทึกงานและปิด Navisworks ให้หมดก่อน

### 4.3 สร้างโฟลเดอร์ปลั๊กอิน

เปิด PowerShell แบบ **Run as Administrator** แล้วปรับ `$navisInstall` ให้ตรงกับเครื่อง:

```powershell
$navisInstall = "C:\Program Files\Autodesk\Navisworks Manage 2027"
$projectRoot = "D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype"

New-Item -ItemType Directory -Path "$navisInstall\Plugins\NavisMcpBridge" -Force
Copy-Item -LiteralPath "$projectRoot\navisworks_plugin\NavisMcpBridge.dll" -Destination "$navisInstall\Plugins\NavisMcpBridge\NavisMcpBridge.dll" -Force
```

ไฟล์ปลายทางต้องเป็น:

```text
<NAVISWORKS_INSTALL>\Plugins\NavisMcpBridge\NavisMcpBridge.dll
```

> ไม่ควรใช้ `INSTALL_PLUGIN_UPDATE.ps1` จากเครื่องเดิมบนเครื่องใหม่ เพราะสคริปต์นั้นอาจมี path ของเครื่องเดิม ให้ใช้คำสั่งด้านบนและกำหนด path ให้ตรงกับเครื่องใหม่

---

## 5. เปิด Navisworks และสร้าง Snapshot

1. เปิด Autodesk Navisworks Manage 2027
2. เปิดไฟล์ `.NWD`, `.NWF` หรือ `.NWC`
3. รอให้โมเดลแสดงครบ
4. ไปที่ **Add-Ins**
5. กด **Navis MCP Bridge**

ปลั๊กอินรุ่นปัจจุบันจะนับเฉพาะ `ModelItem` ที่มี Geometry จริง เพื่อตัด Root, Group, Layer และ Container ออกจากจำนวนหลัก

หน้าต่าง Progress จะแสดง:

```text
Counting physical elements...
Reading physical element properties...
```

รอจนขึ้น:

```text
Navisworks snapshot ready.
```

หลังจากนั้นต้องเปิด Navisworks ค้างไว้ขณะใช้ Dashboard

### ตรวจสอบ Bridge

เปิด PowerShell แล้วรัน:

```powershell
$bridge = Invoke-RestMethod "http://127.0.0.1:8765/api/elements"
$bridge | Select-Object source, modelName, elementCount
```

ค่าที่ถูกต้องควรมีลักษณะดังนี้:

```text
source       : Autodesk Navisworks .NET API
modelName    : path ของโมเดลจริง
elementCount : จำนวนชิ้นงานที่มี Geometry
```

---

## 6. เปิด Web Server

เปิด PowerShell อีกหน้าต่าง โดยปล่อย Navisworks เปิดค้างไว้ แล้วรัน:

```powershell
cd D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype\python_app
& ".\.venv\Scripts\python.exe" -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

ผลที่ถูกต้อง:

```text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

> ไม่ต้องรัน `mcp_server.py` แยก เพราะ `web_app.py` จะเปิด MCP Server เป็น subprocess และเรียก MCP Tool ให้อัตโนมัติ

> ห้ามรัน `bridge_mock.py` เมื่อต้องการใช้ข้อมูลจริง เพราะ Mock Bridge กับ Navisworks Plug-in ใช้พอร์ต 8765 เดียวกัน

---

## 7. เปิด Dashboard

เปิด Browser ที่:

```text
http://127.0.0.1:8000
```

หน้าเว็บจะโหลดข้อมูลอัตโนมัติ หรือกด **Refresh from MCP**

ตรวจสอบ:

```text
Data source : Autodesk Navisworks .NET API
Model file  : ชื่อโมเดลจริงที่เปิดอยู่
Transport   : Navisworks Bridge -> MCP Tool
```

ถ้าขึ้น `Navisworks Bridge Demo` หรือ `Demo_Model.nwd` แสดงว่ากำลังใช้ Mock Data

### มุมมอง BOQ Preparation

Dashboard แสดงคอลัมน์สำคัญสำหรับเตรียม BOQ:

```text
BOQ Code
Description
Category
Family and Type
Type
Level
Material
Unit
Quantity
Count
Length
Area
Volume
Unit Cost
Mark
```

หลักการเลือก Quantity:

1. ถ้ามี Volume ใช้ Volume
2. ถ้าไม่มี Volume แต่มี Area ใช้ Area
3. ถ้าไม่มี Area แต่มี Length ใช้ Length
4. ถ้าไม่มีทั้งหมด ใช้ Count = 1 และ Unit = `ea`

ช่องที่ไม่มีข้อมูลจริงใน Navisworks Properties จะแสดงเป็น `—` ระบบจะไม่สร้างค่าปลอม

Dashboard ปัจจุบันรับ 1,000 Elements ต่อคำขอ แม้ Snapshot จะมีมากกว่านั้น เพื่อป้องกัน Browser ค้าง ข้อมูลนี้เป็นระดับ Element สำหรับเตรียม BOQ ยังไม่ได้จัดกลุ่มหรือรวมยอดเป็น BOQ สุดท้าย

---

## 8. ลำดับเปิดระบบหลังจากติดตั้งสำเร็จแล้ว

ครั้งต่อไปหลังเปิดเครื่อง ไม่ต้องติดตั้งใหม่ ให้ทำเพียง:

```text
1. เปิด Navisworks Manage 2027
2. เปิดโมเดล
3. Add-Ins → Navis MCP Bridge
4. รอ Snapshot เสร็จ
5. เปิด PowerShell ที่ python_app
6. รัน Web Server ด้วย Python ใน .venv
7. เปิด http://127.0.0.1:8000
8. ตรวจ Source และชื่อโมเดล
```

คำสั่งเปิด Web Server:

```powershell
cd D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype\python_app
& ".\.venv\Scripts\python.exe" -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

---

## 9. วิธีอัปเดต Snapshot

เมื่อเปลี่ยนโมเดลหรือโมเดลมีการแก้ไข:

1. กลับไป Navisworks
2. กด **Add-Ins → Navis MCP Bridge** ใหม่
3. รอจนเสร็จ 100%
4. กลับหน้าเว็บ
5. กด **Refresh from MCP**

Snapshot ใหม่จะแทน Snapshot เก่าใน RAM แต่ไม่แก้ไขโมเดลต้นฉบับ

---

## 10. วิธีปิดระบบ

1. ที่ Terminal ของ Web Server กด `Ctrl+C`
2. ปิด Browser
3. ปิด Navisworks

เมื่อปิด Navisworks Snapshot ใน RAM จะหาย ครั้งถัดไปต้องกดปลั๊กอินเพื่อสร้าง Snapshot ใหม่

---

## 11. แก้ปัญหาที่พบบ่อย

### `ModuleNotFoundError: No module named 'mcp'`

สาเหตุ: ใช้ Python หลักของเครื่องแทน `.venv`

ใช้คำสั่งนี้จากโฟลเดอร์ `python_app`:

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

### `python.exe is not recognized`

ตรวจว่าอยู่ในโฟลเดอร์ `python_app` และ path ต้องเป็น:

```text
.\.venv\Scripts\python.exe
```

ไม่ใช่:

```text
..venv\Scripts\python.exe
```

### ไม่เห็น Navis MCP Bridge ใน Add-Ins

ตรวจสอบ:

1. ใช้ Navisworks Manage 2027
2. DLL อยู่ใน `<NAVISWORKS_INSTALL>\Plugins\NavisMcpBridge\`
3. ชื่อไฟล์คือ `NavisMcpBridge.dll`
4. ปิดและเปิด Navisworks ใหม่หลังคัดลอก DLL

### ปลั๊กอินแจ้งว่าพอร์ต 8765 ใช้งานอยู่

ตรวจสอบว่าไม่ได้เปิด `bridge_mock.py` หรือ Navisworks อีก instance หนึ่ง

```powershell
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
```

ปิดโปรแกรมที่ใช้พอร์ตแล้วกด Navis MCP Bridge ใหม่

### `Access is denied` ตอนเปิด Bridge

ทดสอบเปิด Navisworks แบบ **Run as Administrator** หากทำงานได้ แสดงว่าเป็นสิทธิ์ของ HTTP URL reservation

วิธีตั้งค่าถาวร ให้เปิด PowerShell แบบ Administrator แล้วรัน:

```powershell
netsh http add urlacl url=http://127.0.0.1:8765/ user="$env:USERDOMAIN\$env:USERNAME"
```

จากนั้นเปิด Navisworks แบบปกติและลองใหม่

### เปิดเว็บแล้วขึ้น 500

ตรวจตามลำดับ:

1. Navisworks เปิดอยู่
2. มีโมเดลเปิดอยู่
3. กด Navis MCP Bridge และ Snapshot เสร็จแล้ว
4. Bridge ตอบที่ `http://127.0.0.1:8765/api/elements`
5. Web Server รันด้วย Python จาก `.venv`

### หน้าเว็บยังเป็นรูปแบบเก่า

กด:

```text
Ctrl+F5
```

### จำนวนในเว็บไม่เท่ากับ Find Items

ปลั๊กอินรุ่นปัจจุบันกรองเฉพาะรายการที่ `HasGeometry = true` ส่วน Find Items อาจใช้นิยามการเลือกต่างกัน ตัวเลขจึงอาจไม่ตรงกันทั้งหมด ห้ามกำหนดจำนวน 44,514 แบบตายตัว เพราะจำนวนต้องเปลี่ยนตามโมเดลจริง

### ช่อง Material, Area, Volume หรือ Cost เป็น `—`

หมายความว่า Property นั้นไม่มีใน Element หรือไม่ได้ถูก Export มาจากโปรแกรมต้นทาง โค้ดจะไม่คำนวณ Geometry หรือเดาค่าแทนโดยอัตโนมัติ

---

## 12. ใช้กับ Navisworks เวอร์ชันอื่น

DLL ที่ให้มารองรับ Navisworks Manage 2027 หากเครื่องปลายทางใช้ 2026, 2025 หรือเวอร์ชันอื่น ต้อง:

1. ติดตั้ง .NET Framework 4.8 Developer Pack หรือ Visual Studio Build Tools
2. แก้ `NAVISWORKS_INSTALL` ใน `NavisMcpBridge.csproj`
3. อ้างอิง `Autodesk.Navisworks.Api.dll` จาก Navisworks เวอร์ชันนั้น
4. คอมไพล์ DLL ใหม่
5. ติดตั้งลงโฟลเดอร์ `Plugins\NavisMcpBridge` ของเวอร์ชันนั้น

ไม่ควรนำ DLL ของ 2027 ไปใช้กับเวอร์ชันอื่นโดยไม่ทดสอบ

---

## Checklist ก่อน Demo

```text
[ ] Navisworks Manage 2027 เปิดอยู่
[ ] โมเดลจริงเปิดเรียบร้อย
[ ] Navis MCP Bridge สร้าง Snapshot สำเร็จ
[ ] ไม่ได้เปิด bridge_mock.py
[ ] Web Server ใช้ .venv ของโปรเจกต์
[ ] http://127.0.0.1:8000 เปิดได้
[ ] Data source เป็น Autodesk Navisworks .NET API
[ ] Model file ตรงกับไฟล์ที่กำลัง Demo
[ ] ทดลองค้นหาและเปิดดู Properties ได้
[ ] BOQ Preparation แสดงข้อมูลจาก Property จริง
```

## สถานะระบบปัจจุบัน

- อ่านข้อมูลจาก Navisworks Manage 2027 ผ่าน .NET API
- กรองรายการหลักตาม `HasGeometry`
- เก็บ Snapshot ใน RAM
- เปิดข้อมูลผ่าน Local Bridge พอร์ต 8765
- เปิด MCP Tool `get_navisworks_elements`
- Web Backend ทำหน้าที่เป็น MCP Client
- Dashboard แสดงข้อมูลและมุมมอง BOQ Preparation
- ยังไม่ใช่ระบบ BOQ สรุปราคาแบบ Production
