"""
run_uniformat_takeoff.py
-------------------------
ใช้ agent_client.MCPAgent ให้ Claude ตัดสินใจเรียก tool ที่ถูกต้อง แล้วโค้ด (ไม่ใช่ LLM)
เป็นคนคำนวณ Excel จาก raw tool output โดยตรง — กันปัญหาตัวเลขคลาดเคลื่อนจากการให้ LLM
พิมพ์ตัวเลขสรุปเป็นข้อความแล้วเราไป parse ต่อ

รัน (ต้องมี json_bridge.py หรือ bridge_mock.py รันอยู่ที่ port 8765 ก่อน):
    python bridge_mock.py            &  # terminal 1 (หรือ json_bridge.py กับข้อมูลจริง)
    python run_uniformat_takeoff.py     # terminal 2
"""

import asyncio
import json

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from agent_client import MCPAgent

UNIFORMAT_MAP = {
    "Walls": ("B2010 / C1010", "Exterior/Interior Walls & Partitions"),
    "Floors": ("B1010", "Floor Construction"),
    "Doors": ("B2030 / C1020", "Exterior/Interior Doors"),
    "Windows": ("B2020", "Exterior Windows"),
    "Railings": ("C2010 / B2010", "Railings (Stair/Balcony/Facade)"),
    "Stairs": ("C2010", "Stair Construction"),
    "Landings": ("C2010", "Stair Construction - Landings"),
    "Runs": ("C2010", "Stair Construction - Stair Runs"),
    "Ceilings": ("C3030", "Ceiling Finishes"),
    "Rooms": ("Z1010", "Space Data (non-physical)"),
    "Levels": ("Z1020", "Reference Datum (non-physical)"),
    "Generic Models": ("B2000", "Exterior Enclosure - Misc/Facade Elements"),
    "Signage": ("E2010", "Furnishings - Signage"),
    "Structural Columns": ("B1010", "Columns (Structural)"),
    "Pipes": ("D2010", "Plumbing Piping"),
}


async def fetch_summary_via_agent() -> dict:
    agent = MCPAgent()
    await agent.connect()
    try:
        result = await agent.run(
            "เรียก get_health ก่อนเพื่อยืนยันว่า Bridge อ่านโมเดลได้ "
            "จากนั้นเรียก get_category_type_summary เพื่อดึงสรุปทั้งโมเดล "
            "ไม่ต้องสรุปตัวเลขเองในคำตอบ แค่ยืนยันว่าดึงสำเร็จและระบุจำนวน distinctGroups"
        )
        for call in result["tool_calls"]:
            if call["name"] == "get_category_type_summary":
                return json.loads(call["output"])
        raise RuntimeError(
            "Agent ไม่ได้เรียก get_category_type_summary เลย — "
            f"final_text ที่ตอบมา: {result['final_text']}"
        )
    finally:
        await agent.close()


def build_excel(summary: dict, out_path: str) -> None:
    groups = [(g["category"], g["type"], g["count"]) for g in summary["groups"]]
    classifiable = sum(g[2] for g in groups)
    assert classifiable == summary["classifiableElements"], "sum(groups) ต้องตรงกับ classifiableElements เสมอ"

    groups_sorted = sorted(groups, key=lambda g: (g[0], -g[2]))

    wb = openpyxl.Workbook()
    FONT = "Arial"
    header_font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill("solid", fgColor="2F5597")
    title_font = Font(name=FONT, bold=True, size=14)
    note_font = Font(name=FONT, italic=True, size=9, color="C00000")
    thin = Side(style="thin", color="B7B7B7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws = wb.active
    ws.title = "Element Detail"
    ws["A1"] = "Element Takeoff by Uniformat Classification"
    ws["A1"].font = title_font
    ws.merge_cells("A1:G1")

    no_cat = summary.get("elementsWithoutCategory", 0)
    ws["A2"] = (
        f"Classifiable: {classifiable:,} | Without Element.Category (excluded): {no_cat:,} "
        f"| Total in export file: {summary.get('totalElementsInFile', classifiable + no_cat):,}"
    )
    ws["A2"].font = note_font
    ws.merge_cells("A2:G2")

    headers = ["No.", "Uniformat Code", "Uniformat System", "Category", "Type", "Count", "% of Total"]
    header_row = 4
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c, value=h)
        cell.font, cell.fill, cell.border = header_font, header_fill, border
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    start_row = header_row + 1
    end_row = start_row + len(groups_sorted) - 1
    total_row = end_row + 1

    for i, (cat, typ, cnt) in enumerate(groups_sorted):
        r = start_row + i
        code, system = UNIFORMAT_MAP.get(cat, ("N/C", "Unclassified — add to UNIFORMAT_MAP"))
        for col, val in enumerate([i + 1, code, system, cat, typ], start=1):
            ws.cell(row=r, column=col, value=val).border = border
        cnt_cell = ws.cell(row=r, column=6, value=cnt)
        cnt_cell.number_format, cnt_cell.border = "#,##0", border
        pct_cell = ws.cell(row=r, column=7, value=f"=F{r}/$F${total_row}")
        pct_cell.number_format, pct_cell.border = "0.00%", border

    ws.cell(row=total_row, column=5, value="TOTAL").font = Font(bold=True)
    tot = ws.cell(row=total_row, column=6, value=f"=SUM(F{start_row}:F{end_row})")
    tot.number_format = "#,##0"

    widths = [6, 16, 30, 20, 46, 12, 11]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = f"A{start_row}"

    wb.save(out_path)


async def main():
    summary = await fetch_summary_via_agent()
    print(
        f"ได้ raw summary: {summary['distinctGroups']} groups, "
        f"classifiable={summary['classifiableElements']}, "
        f"without_category={summary.get('elementsWithoutCategory', 0)}"
    )
    if summary.get("elementsWithoutCategory", 0) > 0 and summary["classifiableElements"] == 0:
        print(
            "\n*** คำเตือน: classifiableElements = 0 — export ไฟล์นี้ไม่มี Element.Category เลย ***\n"
            "*** ต้อง rebuild NavisHeadlessExporter.Plugin (ดู navisworks-headless-exporter/) แล้ว export ใหม่ ***\n"
        )
    build_excel(summary, "Uniformat_Takeoff.xlsx")
    print("บันทึกไฟล์: Uniformat_Takeoff.xlsx")


if __name__ == "__main__":
    asyncio.run(main())
