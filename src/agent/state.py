"""LangGraph Agent State 定義。

State 貫穿整個工作流,每個節點讀取所需欄位、寫回其產出。
使用 total=False 讓節點只需回傳自己更新的欄位(LangGraph 會 merge)。
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class Intent(TypedDict, total=False):
    query_type: str      # aggregate_single | detail | group_stat | trend | comparison | unsupported
    entities: dict       # 抽取的實體: 日期範圍、分店、產品線等
    language: str        # 'zh' | 'en'
    hints: list          # 語意暗示關鍵詞
    supported: bool      # 是否為資料集可回答的查詢(如「預測」為 False)


class QueryResult(TypedDict, total=False):
    columns: list         # 欄位名
    rows: list            # list of tuple/list
    row_count: int


class ChartSpec(TypedDict, total=False):
    chart_type: str       # bar | line | pie
    x: str
    y: str
    title: str


class AgentState(TypedDict, total=False):
    # 輸入 / 對話
    user_input: str
    history: list                       # [{role, content}, ...] 多輪上下文

    # 各節點產出
    intent: Intent
    schema: str
    sql: str
    sql_error: Optional[str]
    retry_count: int
    query_result: QueryResult
    response_format: str                # speech | list | chart
    chart_spec: Optional[ChartSpec]
    chart_path: Optional[str]

    # 輸出
    final_answer: str
    error_message: Optional[str]        # 面向使用者的失敗訊息(如無法理解、不支援)

    # 診斷 / metadata
    meta: dict[str, Any]


def new_state(user_input: str, history: Optional[list] = None) -> AgentState:
    """建立一輪查詢的初始 state。"""
    return {
        "user_input": user_input,
        "history": history or [],
        "retry_count": 0,
        "sql_error": None,
        "error_message": None,
        "meta": {},
    }
