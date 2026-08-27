# Navisworks MCP Web Prototype

## Value Proposition

ช่วยผู้ใช้งาน BIM อ่านข้อมูล Elements และ Properties จากไฟล์ Navisworks และเปิดดูผ่าน Web Dashboard โดยไม่ต้องเปิดหน้าต่าง Navisworks ระหว่างการใช้งานเว็บ

**Core actions**: ส่งออกโมเดลเป็น JSON แบบ NoGui, เรียกข้อมูลผ่าน MCP, ค้นหาและตรวจข้อมูลสำหรับเตรียม BOQ

## Why MCP

MCP ทำหน้าที่เป็นขอบเขตเครื่องมือระหว่าง Web Backend กับแหล่งข้อมูล Navisworks ทำให้เปลี่ยนแหล่งข้อมูลจาก Live Plug-in เป็น Headless JSON ได้โดยหน้าเว็บไม่ต้องรู้รายละเอียดการอ่าน NWD/NWC

## UI Overview

- ผู้ใช้เปิด Dashboard และกด Refresh from MCP
- Web Backend เรียก MCP Tool `get_navisworks_elements`
- MCP เรียก Local JSON Bridge พร้อม `limit` และ `offset`
- Dashboard แสดงชื่อโมเดล จำนวนทั้งหมด จำนวนที่โหลด และ Properties

## Product Context

- Navisworks Manage 2027 และ C# Headless Exporter สร้าง JSON
- JSON Bridge ใช้ FastAPI ที่ `127.0.0.1:8765`
- MCP Server ทำงานผ่าน stdio
- FastAPI Web Dashboard ทำงานที่ `127.0.0.1:8000`
- ระบบเป็น Local prototype ไม่มี Authentication และไม่เปิดรับการเชื่อมต่อจากภายนอกเครื่อง

## Data and Performance Decisions

- JSON Bridge โหลดไฟล์ขนาดใหญ่หนึ่งครั้งและเก็บใน RAM
- ตรวจเวลาแก้ไขไฟล์และ Reload เมื่อ Headless Exporter สร้าง JSON รุ่นใหม่
- Endpoint จำกัดผลลัพธ์สูงสุด 5,000 รายการต่อคำขอ
- Web โหลดเริ่มต้น 1,000 รายการเพื่อไม่ให้ Browser และ MCP รับ payload ขนาดใหญ่เกินไป
