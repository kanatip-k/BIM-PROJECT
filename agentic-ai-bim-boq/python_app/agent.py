"""Small tool-using workflow agent for the local research prototype.

The agent chooses a local tool from the user's request.  Engineering results
remain deterministic and auditable; language input never performs quantity or
price arithmetic itself.
"""
from __future__ import annotations

from typing import Any

from boq_workflow import list_workflows, run_boq_workflow_from_payload

BOQ_INTENTS = (
    "boq", "quantity", "takeoff", "cost", "estimate", "ราคา",
    "ถอดปริมาณ", "ปริมาณ", "ประมาณราคา", "รายการปริมาณ",
)
HISTORY_INTENTS = ("history", "previous", "ล่าสุด", "ประวัติ", "ผลก่อน")


def _contains(text: str, words: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(word.casefold() in folded for word in words)


def handle_agent_request(
    message: str,
    payload: dict[str, Any],
    disciplines: list[str] | None = None,
) -> dict[str, Any]:
    text = (message or "").strip()
    if not text:
        raise ValueError("message is required")

    if _contains(text, HISTORY_INTENTS):
        workflows = list_workflows(10)
        return {
            "action": "list_boq_workflows",
            "message": f"พบผล BOQ ที่บันทึกไว้ {len(workflows)} งาน",
            "workflows": workflows,
        }

    if _contains(text, BOQ_INTENTS):
        result = run_boq_workflow_from_payload(payload, disciplines)
        summary = result.get("summary", {})
        return {
            "action": "run_boq_workflow",
            "message": (
                f"สร้าง BOQ {summary.get('lineCount', 0)} บรรทัดจาก "
                f"{summary.get('elementCount', 0)} elements; "
                f"มี {summary.get('unpricedLineCount', 0)} บรรทัดที่ยังไม่มีราคา"
            ),
            "jobId": result.get("jobId"),
            "status": result.get("status"),
            "summary": summary,
            "issues": result.get("issues", []),
        }

    return {
        "action": "describe_model",
        "message": (
            f"โมเดล {payload.get('modelName', 'ไม่ทราบชื่อ')} มี "
            f"{len(payload.get('elements') or [])} records พร้อมให้ Agent เรียก BOQ workflow "
            "ลองสั่งว่า ‘สร้าง BOQ’ หรือ ‘ถอดปริมาณ Architecture’"
        ),
        "model": payload.get("modelName"),
        "elementCount": len(payload.get("elements") or []),
    }
