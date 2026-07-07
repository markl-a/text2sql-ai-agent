"""Text2SQL Agent 高階封裝。

綁定 compiled LangGraph + 依賴 + 多輪對話 history,提供簡單的 ask() API。
"""
from __future__ import annotations

from typing import Any, Optional

from config import CONFIG, Config, setup_langsmith
from src.agent.deps import Deps
from src.agent.graph import build_graph
from src.agent.state import new_state
from src.cache import QueryCache
from src.llm.client import get_llm


class Text2SQLAgent:
    def __init__(self, llm: Any = None, cfg: Config = CONFIG,
                 cache: Optional[QueryCache] = None):
        setup_langsmith(cfg)  # 依 env 啟用/停用 LangSmith tracing
        self.cfg = cfg
        self.deps = Deps(llm=llm or get_llm(cfg), cfg=cfg, cache=cache or QueryCache())
        self.graph = build_graph(self.deps, cfg)
        self.history: list[dict] = []

    def ask(self, question: str, use_history: bool = True) -> dict:
        """執行一輪查詢。回傳含 final_answer、sql、圖表等的結果 dict。"""
        state = new_state(question, history=self.history if use_history else [])
        final = self.graph.invoke(state)

        answer = final.get("final_answer", "")
        if use_history:
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": answer})

        return {
            "answer": answer,
            "sql": final.get("sql"),
            "response_format": final.get("response_format"),
            "chart_spec": final.get("chart_spec"),
            "chart_path": final.get("chart_path"),
            "figure": (final.get("meta") or {}).get("figure"),
            "query_result": final.get("query_result"),
            "intent": final.get("intent"),
            "error_message": final.get("error_message"),
            "retry_count": final.get("retry_count", 0),
            "cache_hit": (final.get("meta") or {}).get("cache_hit", False),
        }

    def reset(self) -> None:
        self.history.clear()

    def cache_stats(self) -> dict:
        return self.deps.cache.stats()
