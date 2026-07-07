"""Schema 擷取節點 (Schema Fetcher)。

自動從 SQLite 讀取資料表 Schema(欄名、型別、範例值、說明),
組成 Prompt 片段供 Text2SQL 節點參考。
"""
from __future__ import annotations

from src.agent.deps import Deps
from src.agent.state import AgentState
from src.db.schema import get_schema_prompt


def make_schema_fetcher(deps: Deps):
    def schema_fetcher(state: AgentState) -> dict:
        schema = get_schema_prompt(deps.cfg.db_path, deps.cfg.table_name)
        return {"schema": schema}

    return schema_fetcher
