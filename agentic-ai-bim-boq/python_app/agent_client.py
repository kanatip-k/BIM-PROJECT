"""
agent_client.py
-----------------
ตัว "AI Agent" ที่คุยกับ mcp_server.py (ในโฟลเดอร์เดียวกันนี้) ผ่าน Official MCP Python SDK
แล้วให้ Claude (ผ่าน Anthropic API) เป็นคนตัดสินใจว่าจะเรียก tool ไหน ด้วย tool-use loop มาตรฐาน

ใช้คู่กับระบบเดิม: start.ps1 เปิด json_bridge (port 8765) ให้ทำงานอยู่ก่อน (หรือ bridge_mock.py
สำหรับ dev/test) แล้วค่อยรันสคริปต์นี้/run_uniformat_takeoff.py — agent จะ spawn mcp_server.py
เป็น subprocess ของตัวเอง (เหมือนที่ web_app.py ทำอยู่แล้วตอนเรียก call_mcp_tool)

ติดตั้ง:
    pip install -r requirements.txt

ตั้งค่า:
    export ANTHROPIC_API_KEY=sk-ant-...   (หรือ set บน Windows)
    export NAVIS_BRIDGE_URL=http://127.0.0.1:8765   (ค่า default อยู่แล้ว ไม่ต้องตั้งก็ได้)
"""

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODEL = "claude-sonnet-4-6"  # เปลี่ยนเป็นรุ่นที่ต้องการได้
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class MCPAgent:
    """
    ห่อ MCP session + Anthropic client ไว้ในตัวเดียว:
      1. connect()  -> เปิด subprocess ของ mcp_server.py แล้ว list_tools()
      2. run(task)   -> ส่ง task ให้ Claude พร้อม tool schema, วน tool-use loop
                        จนกว่า Claude จะตอบจบ (stop_reason == "end_turn")
    """

    def __init__(self):
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[os.path.join(BASE_DIR, "mcp_server.py")],
            env={**os.environ, "NAVIS_BRIDGE_URL": os.environ.get("NAVIS_BRIDGE_URL", "http://127.0.0.1:8765")},
        )
        self.anthropic = anthropic.Anthropic()
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.tools_anthropic_schema: list[dict] = []

    async def connect(self) -> None:
        read, write = await self._stack.enter_async_context(stdio_client(self.server_params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

        listed = await self.session.list_tools()
        self.tools_anthropic_schema = [
            {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
            for t in listed.tools
        ]
        print(f"[connected] tools available: {[t['name'] for t in self.tools_anthropic_schema]}")

    async def _call_tool(self, name: str, arguments: dict) -> str:
        result = await self.session.call_tool(name, arguments)
        parts = [b.text for b in result.content if hasattr(b, "text")]
        return "\n".join(parts) if parts else "(empty tool result)"

    async def run(self, task: str, max_turns: int = 12) -> dict[str, Any]:
        """
        วน tool-use loop จนกว่า Claude จะตอบจบ คืนทั้ง:
          - final_text: สรุปภาษาธรรมชาติ (ไว้อ่านเล่น)
          - tool_calls: raw output ของทุก tool call ที่เกิดขึ้นจริง (source of truth
            สำหรับตัวเลข — อย่า parse ตัวเลขจาก final_text เพราะ Claude อาจพิมพ์/ปัดเศษผิด)
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        tool_calls: list[dict[str, Any]] = []

        for turn in range(max_turns):
            response = self.anthropic.messages.create(
                model=MODEL, max_tokens=4096, tools=self.tools_anthropic_schema, messages=messages
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                final_text = "".join(b.text for b in response.content if b.type == "text")
                return {"final_text": final_text, "tool_calls": tool_calls}

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                print(f"[turn {turn}] calling tool: {block.name}({block.input})")
                tool_output = await self._call_tool(block.name, block.input)
                tool_calls.append({"name": block.name, "input": block.input, "output": tool_output})
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": tool_output}
                )

            messages.append({"role": "user", "content": tool_results})

        return {
            "final_text": "(หยุดเพราะครบ max_turns โดยยังไม่ได้คำตอบสุดท้าย — ปรับ max_turns หรือทำ task ให้แคบลง)",
            "tool_calls": tool_calls,
        }

    async def close(self) -> None:
        await self._stack.aclose()


async def main():
    agent = MCPAgent()
    await agent.connect()
    try:
        result = await agent.run(
            "เรียก get_health ก่อนเพื่อยืนยันว่า Bridge อ่านโมเดลได้ "
            "จากนั้นเรียก get_category_type_summary เพื่อดูสรุปทั้งโมเดล "
            "สรุปเป็นข้อความสั้นๆ ว่ามี Category หลักอะไรบ้าง และมี elementsWithoutCategory เท่าไหร่"
        )
        print("\n=== AGENT ANSWER ===\n", result["final_text"])
        print("\n=== RAW TOOL CALLS (source of truth) ===")
        for call in result["tool_calls"]:
            print("-", call["name"], call["input"])
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
