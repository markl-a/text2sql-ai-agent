"""LangGraph 工作流定義 (StateGraph)。

流程:
  START
    → intent_parser        意圖理解
    → (supported?)          不支援 → unsupported_handler → composer
    → schema_fetcher        取得 DB schema
    → text2sql              生成 SQL
    → sql_validator         驗證安全與語法
        ├ valid    → sql_executor
        ├ retry    → text2sql(重試,上限 MAX_RETRIES)
        └ exhausted→ retry_exhausted_handler → composer
    → sql_executor          執行查詢
        ├ ok       → response_router
        ├ retry    → text2sql
        └ exhausted→ retry_exhausted_handler → composer
    → response_router       決定 speech/list/chart
    → response_composer     組合最終回覆
    → END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from config import CONFIG, Config
from src.agent.deps import Deps
from src.agent.nodes.intent_parser import make_intent_parser
from src.agent.nodes.response_composer import make_response_composer
from src.agent.nodes.response_router import make_response_router
from src.agent.nodes.schema_fetcher import make_schema_fetcher
from src.agent.nodes.sql_executor import make_sql_executor
from src.agent.nodes.sql_validator import make_sql_validator
from src.agent.nodes.text2sql import make_text2sql
from src.agent.state import AgentState

UNSUPPORTED_MSG = {
    "zh": "抱歉,目前的資料集僅包含歷史交易紀錄,我無法進行此類分析(如預測或需外部資訊的問題)。"
          "不過我可以協助您查看過去的銷售趨勢。您想了解哪方面的歷史數據呢?",
    "en": "Sorry, this dataset only contains historical transactions, so I can't perform this "
          "kind of analysis (e.g. forecasting or questions needing external data). "
          "I'd be happy to help you explore the historical sales data instead.",
}
EXHAUSTED_MSG = {
    "zh": "抱歉,我無法理解您的問題,請換個方式提問,或提供更具體的條件。",
    "en": "Sorry, I couldn't understand your question. Please rephrase it or give more specific details.",
}


def _lang(state: AgentState) -> str:
    return (state.get("intent") or {}).get("language", "zh") or "zh"


def route_after_intent(state: AgentState) -> str:
    intent = state.get("intent") or {}
    return "supported" if intent.get("supported", True) else "unsupported"


def _make_route_after_validate(cfg: Config):
    def route_after_validate(state: AgentState) -> str:
        if not state.get("sql_error"):
            return "valid"
        if state.get("retry_count", 0) < cfg.max_retries:
            return "retry"
        return "exhausted"
    return route_after_validate


def _make_route_after_execute(cfg: Config):
    def route_after_execute(state: AgentState) -> str:
        if not state.get("sql_error"):
            return "ok"
        if state.get("retry_count", 0) < cfg.max_retries:
            return "retry"
        return "exhausted"
    return route_after_execute


def _unsupported_handler(state: AgentState) -> dict:
    return {"error_message": UNSUPPORTED_MSG.get(_lang(state), UNSUPPORTED_MSG["zh"])}


def _retry_exhausted_handler(state: AgentState) -> dict:
    return {"error_message": EXHAUSTED_MSG.get(_lang(state), EXHAUSTED_MSG["zh"])}


def build_graph(deps: Deps, cfg: Config = CONFIG):
    """組裝並編譯 LangGraph。回傳可 invoke 的 compiled graph。"""
    g = StateGraph(AgentState)

    g.add_node("intent_parser", make_intent_parser(deps))
    g.add_node("schema_fetcher", make_schema_fetcher(deps))
    g.add_node("text2sql", make_text2sql(deps))
    g.add_node("sql_validator", make_sql_validator(deps))
    g.add_node("sql_executor", make_sql_executor(deps))
    g.add_node("response_router", make_response_router(deps))
    g.add_node("response_composer", make_response_composer(deps))
    g.add_node("unsupported_handler", _unsupported_handler)
    g.add_node("retry_exhausted_handler", _retry_exhausted_handler)

    g.add_edge(START, "intent_parser")
    g.add_conditional_edges(
        "intent_parser", route_after_intent,
        {"supported": "schema_fetcher", "unsupported": "unsupported_handler"},
    )
    g.add_edge("unsupported_handler", "response_composer")
    g.add_edge("schema_fetcher", "text2sql")
    g.add_edge("text2sql", "sql_validator")
    g.add_conditional_edges(
        "sql_validator", _make_route_after_validate(cfg),
        {"valid": "sql_executor", "retry": "text2sql", "exhausted": "retry_exhausted_handler"},
    )
    g.add_conditional_edges(
        "sql_executor", _make_route_after_execute(cfg),
        {"ok": "response_router", "retry": "text2sql", "exhausted": "retry_exhausted_handler"},
    )
    g.add_edge("retry_exhausted_handler", "response_composer")
    g.add_edge("response_router", "response_composer")
    g.add_edge("response_composer", END)

    return g.compile()
