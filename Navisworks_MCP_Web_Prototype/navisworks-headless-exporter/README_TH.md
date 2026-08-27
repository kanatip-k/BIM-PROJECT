# Navisworks Headless JSON Exporter

ชุดโค้ดนี้อ่านข้อมูลจากไฟล์ NWD/NWF/NWC โดยไม่แสดงหน้าต่าง Navisworks จากนั้นส่งออกข้อมูลวัตถุและ Properties เป็น JSON

## ข้อเท็จจริงสำคัญ

- เครื่องต้องติดตั้ง Autodesk Navisworks Manage หรือ Simulate รุ่นที่รองรับ
- Navisworks จะยังทำงานเป็นโปรเซสเบื้องหลัง เพราะการอ่านไฟล์ใช้ Navisworks .NET API
- ต้องมีสิทธิ์ใช้งานและไลเซนส์ Navisworks ที่ถูกต้อง
- ไม่สามารถนำ `Autodesk.Navisworks.Api.dll` ไปอ่าน NWD โดยลำพังบนเครื่องที่ไม่มี Navisworks
- โค้ดตัวอย่างตั้งค่าเริ่มต้นเป็น Navisworks Manage 2027 ที่ `D:\Navisworks Manage 2027`

## โครงสร้าง

```text
navisworks-headless-exporter\
├── NavisHeadlessExporter.Plugin\
│   ├── NavisHeadlessExporter.Plugin.csproj
│   └── NavisHeadlessExporterPlugin.cs
├── NavisHeadlessRunner\
│   ├── NavisHeadlessRunner.csproj
│   └── Program.cs
├── dist\
│   ├── NavisHeadlessExporter.dll
│   └── NavisHeadlessRunner.exe
└── README_TH.md
```

## วิธีใช้แบบเร็วที่สุด

โฟลเดอร์ `dist` มีไฟล์ที่คอมไพล์และตรวจสอบกับ Navisworks Manage 2027 แล้ว จึงทดลองรันได้โดยไม่ต้องคอมไพล์ใหม่:

```powershell
cd .\dist

.\NavisHeadlessRunner.exe `
  "D:\Models\Building.nwd" `
  "D:\Export\building.json" `
  "D:\Navisworks Manage 2027"
```

เปลี่ยน `D:\Models\Building.nwd` เป็นพาธโมเดลจริง และเปลี่ยน `D:\Export\building.json` เป็นตำแหน่งผลลัพธ์ที่ต้องการ

## หลักการทำงาน

```text
NavisHeadlessRunner.exe
        ↓
roamer.exe -NoGui
        ↓
เปิด NWD / NWF / NWC ในเบื้องหลัง
        ↓
ExecuteAddInPlugin: NavisHeadlessExporter.KNTI
        ↓
กรองเฉพาะ ModelItem ที่ HasGeometry = true
        ↓
อ่าน ID, Display Name, Class และ Properties
        ↓
เขียน output.json และ output.json.status.json
        ↓
ปิด Navisworks อัตโนมัติ
```

## สิ่งที่ต้องติดตั้งสำหรับคอมไพล์

1. Navisworks Manage 2027
2. .NET Framework 4.8 Developer Pack
3. Visual Studio 2022 หรือ Build Tools ที่มี MSBuild

## คอมไพล์ Plug-in

เปิด Developer PowerShell for Visual Studio ที่โฟลเดอร์ชุดโค้ด แล้วรัน:

```powershell
msbuild .\NavisHeadlessExporter.Plugin\NavisHeadlessExporter.Plugin.csproj `
  /p:Configuration=Release `
  /p:NavisworksInstall="D:\Navisworks Manage 2027"
```

ไฟล์ที่ได้:

```text
NavisHeadlessExporter.Plugin\bin\Release\net48\NavisHeadlessExporter.dll
```

## คอมไพล์ Runner

```powershell
msbuild .\NavisHeadlessRunner\NavisHeadlessRunner.csproj `
  /p:Configuration=Release
```

คัดลอกไฟล์ Plug-in DLL ไปไว้ข้าง Runner:

```powershell
Copy-Item `
  .\NavisHeadlessExporter.Plugin\bin\Release\net48\NavisHeadlessExporter.dll `
  .\NavisHeadlessRunner\bin\Release\net48\
```

## วิธีรัน

```powershell
cd .\NavisHeadlessRunner\bin\Release\net48

.\NavisHeadlessRunner.exe `
  "D:\Models\Building.nwd" `
  "D:\Export\building.json" `
  "D:\Navisworks Manage 2027"
```

หาก DLL ไม่ได้อยู่ข้าง Runner สามารถระบุพาธเป็นอาร์กิวเมนต์ลำดับที่ 4:

```powershell
.\NavisHeadlessRunner.exe `
  "D:\Models\Building.nwd" `
  "D:\Export\building.json" `
  "D:\Navisworks Manage 2027" `
  "D:\MyPlugin\NavisHeadlessExporter.dll"
```

## ไฟล์ผลลัพธ์

`building.json` มีโครงสร้าง:

```json
{
  "source": "Autodesk Navisworks .NET API (NoGui)",
  "modelName": "D:\\Models\\Building.nwd",
  "snapshotUtc": "2026-08-24T08:00:00.0000000Z",
  "elementCount": 44514,
  "elements": [
    {
      "id": "...",
      "displayName": "Wall-001",
      "classDisplayName": "Wall",
      "properties": {
        "Element.Category": "Walls"
      }
    }
  ]
}
```

`building.json.status.json` ใช้ตรวจความคืบหน้า:

```json
{
  "phase": "reading",
  "processed": 22000,
  "total": 44514,
  "percent": 49,
  "message": "Reading element properties",
  "updatedUtc": "2026-08-24T08:00:00.0000000Z"
}
```

เว็บสามารถอ่านไฟล์สถานะนี้เป็นระยะเพื่อแสดงเปอร์เซ็นต์ได้

## นำไปต่อกับ MCP

วิธีที่ปลอดภัยคือให้ MCP Tool เรียก `NavisHeadlessRunner.exe` พร้อมพาธโมเดลและพาธไฟล์ JSON รอจน Runner จบ แล้วอ่าน JSON ส่งกลับให้ Web Backend

ไม่ควรให้ผู้ใช้ส่งพาธไฟล์ใดก็ได้จากอินเทอร์เน็ตโดยตรง ควรกำหนดโฟลเดอร์โมเดลที่อนุญาตและตรวจสอบพาธก่อนเรียก Runner

## ถ้าไม่ต้องการติดตั้ง Navisworks จริง ๆ

ต้องเปลี่ยนไปใช้บริการ Autodesk Platform Services เช่น Model Derivative API โดยอัปโหลดโมเดลขึ้น Cloud แล้วอ่าน Metadata/Properties ผ่าน REST API แนวทางนั้นไม่ใช้ Navisworks .NET API และต้องมีบัญชี APS, Authentication และพื้นที่จัดเก็บไฟล์บน Cloud
