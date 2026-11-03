"""
run_takeoff_direct.py
---------------------
Bypass Claude/MCP agent entirely.
Calls the bridge REST API directly, builds the Excel, writes a result log.
Run this script — it writes results to takeoff_result.txt and Uniformat_Takeoff.xlsx
"""

import json
import os
import sys
import traceback
import urllib.request
from pathlib import Path

LOG = Path(__file__).parent / "takeoff_result.txt"

def log(msg):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def main():
    LOG.unlink(missing_ok=True)
    log("=== run_takeoff_direct.py START ===")

    bridge_url = os.environ.get("NAVIS_BRIDGE_URL", "http://127.0.0.1:8765")

    # 1. Health check
    try:
        r = urllib.request.urlopen(f"{bridge_url}/health", timeout=10)
        health = json.loads(r.read())
        log(f"[health] status={health.get('status')} modelName={health.get('modelName')} elementCount={health.get('elementCount')}")
    except Exception as e:
        log(f"[ERROR] Cannot reach bridge at {bridge_url}/health: {e}")
        sys.exit(1)

    # 2. Fetch summary
    try:
        r = urllib.request.urlopen(f"{bridge_url}/api/summary", timeout=60)
        summary = json.loads(r.read())
        log(f"[summary] totalElements={summary['totalElementsInFile']} classifiable={summary['classifiableElements']} without_category={summary.get('elementsWithoutCategory',0)} groups={summary['distinctGroups']}")
    except Exception as e:
        log(f"[ERROR] Cannot fetch summary: {e}")
        traceback.print_exc()
        sys.exit(1)

    if summary["classifiableElements"] == 0:
        log("[WARNING] classifiableElements=0 — no Element.Category in export. Rebuild plugin and re-export.")
        sys.exit(1)

    # 3. Build Excel
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

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

        groups = [(g["category"], g["type"], g["count"]) for g in summary["groups"]]
        classifiable = sum(g[2] for g in groups)
        groups_sorted = sorted(groups, key=lambda g: (g[0], -g[2]))

        wb = openpyxl.Workbook()
        FONT = "Arial"
        header_font  = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        header_fill  = PatternFill("solid", fgColor="2F5597")
        title_font   = Font(name=FONT, bold=True, size=14)
        note_font    = Font(name=FONT, italic=True, size=9, color="C00000")
        thin         = Side(style="thin", color="B7B7B7")
        border       = Border(left=thin, right=thin, top=thin, bottom=thin)

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
        end_row   = start_row + len(groups_sorted) - 1
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

        out_path = Path(__file__).parent / "Uniformat_Takeoff.xlsx"
        wb.save(out_path)
        log(f"[OK] Saved: {out_path}")
        log(f"[OK] Rows written: {len(groups_sorted)}")
        log("=== DONE ===")

    except Exception as e:
        log(f"[ERROR] Excel build failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
