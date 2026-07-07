"""SQL 執行節點 (SQL Executor)。

以「唯讀連線」安全執行已驗證的 SELECT,套用結果列數上限與逾時保護,
並使用 query cache 避免重複查詢。回傳結構化結果。
"""
from __future__ import annotations

import sqlite3

from src.agent.deps import Deps
from src.agent.state import AgentState


def _ensure_limit(sql: str, max_rows: int) -> str:
    """若查詢沒有 LIMIT,補上上限,避免結果過大。"""
    lowered = sql.lower()
    if " limit " in f" {lowered} ":
        return sql
    return f"{sql.rstrip().rstrip(';')} LIMIT {max_rows}"


def make_sql_executor(deps: Deps):
    def sql_executor(state: AgentState) -> dict:
        sql = state.get("sql", "")
        retry = state.get("retry_count", 0)
        bounded_sql = _ensure_limit(sql, deps.cfg.max_result_rows)

        # 快取命中
        cached = deps.cache.get(bounded_sql)
        if cached is not None:
            return {"query_result": cached, "sql_error": None,
                    "meta": {**state.get("meta", {}), "cache_hit": True}}

        try:
            conn = sqlite3.connect(f"file:{deps.cfg.db_path}?mode=ro", uri=True)
            conn.execute("PRAGMA query_only = ON")
            try:
                cur = conn.execute(bounded_sql)
                columns = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchmany(deps.cfg.max_result_rows)
                rows = [list(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.Error as e:
            return {"sql_error": f"SQL 執行錯誤: {e}", "retry_count": retry + 1}

        result = {"columns": columns, "rows": rows, "row_count": len(rows)}
        deps.cache.set(bounded_sql, result)
        return {"query_result": result, "sql_error": None,
                "meta": {**state.get("meta", {}), "cache_hit": False}}

    return sql_executor
