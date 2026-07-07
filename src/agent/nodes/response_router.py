"""回覆格式決策節點 (Response Router) — 核心考核。

以 format_rules.decide_format(規則為主)決定 speech / list / chart 與圖表類型。
規則對「單值/明細/分組」等明確情境給出可預期結果;此節點也可在未來接上
LLM 輔助決策(目前規則已涵蓋考題場景,保持可預期與可測試)。
"""
from __future__ import annotations

from src.agent.deps import Deps
from src.agent.format_rules import decide_format
from src.agent.state import AgentState


def make_response_router(deps: Deps):
    def response_router(state: AgentState) -> dict:
        intent = state.get("intent") or {}
        result = state.get("query_result") or {}
        fmt, chart_spec = decide_format(intent, result)
        return {"response_format": fmt, "chart_spec": chart_spec}

    return response_router
