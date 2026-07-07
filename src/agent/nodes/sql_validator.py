"""SQL 驗證/修正節點 (SQL Validator)。

兩層驗證:
1. 靜態安全驗證(sql_safety.validate_sql):僅允許唯讀 SELECT。
2. 語法驗證:對 SQLite 執行 EXPLAIN,確認語法與欄位可解析。

驗證失敗時設定 sql_error 並遞增 retry_count;是否重試由 graph 條件邊決定。
"""
from __future__ import annotations

import sqlite3

from src.agent.deps import Deps
from src.agent.state import AgentState
from src.agent.sql_safety import validate_sql


def _explain_ok(sql: str, db_path: str) -> tuple[bool, str]:
    """用 EXPLAIN 驗證語法/欄位;不實際取資料。"""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute(f"EXPLAIN {sql}")
            return True, ""
        finally:
            conn.close()
    except sqlite3.Error as e:
        return False, f"SQL 語法/欄位錯誤: {e}"


def make_sql_validator(deps: Deps):
    def sql_validator(state: AgentState) -> dict:
        sql = state.get("sql", "")
        retry = state.get("retry_count", 0)

        safe, err = validate_sql(sql)
        if not safe:
            return {"sql_error": err, "retry_count": retry + 1}

        ok, err = _explain_ok(sql, deps.cfg.db_path)
        if not ok:
            return {"sql_error": err, "retry_count": retry + 1}

        return {"sql_error": None}

    return sql_validator
