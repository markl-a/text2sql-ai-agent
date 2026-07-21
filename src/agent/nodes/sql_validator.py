"""SQL 驗證/修正節點 (SQL Validator)。

三層防護:
1. 靜態安全驗證(sql_safety.validate_sql):僅允許唯讀 SELECT。
2. 語法驗證:對 SQLite 執行 EXPLAIN,確認語法與欄位可解析。
3. 欄名自動修復(sql_repair):小模型在 temperature=0 下可能確定性拼錯欄名
   (如 branch → brancch),重試回饋無法自我修正;此時以 schema fuzzy match
   直接修復欄名再重新驗證,不依賴模型重試。

驗證失敗時設定 sql_error 並遞增 retry_count;是否重試由 graph 條件邊決定。
"""
from __future__ import annotations

import re
import sqlite3

from src.agent.deps import Deps
from src.agent.state import AgentState
from src.agent.sql_repair import repair_no_such_column
from src.agent.sql_safety import validate_sql
from src.db.schema import get_table_columns

_NO_SUCH_COLUMN = re.compile(r"no such column:\s*([\w.]+)")
_MAX_COLUMN_REPAIRS = 3  # 一條 SQL 最多修復 3 個錯欄名,避免無限迴圈


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


def _schema_columns(db_path: str, table: str) -> list[str]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return [c["name"] for c in get_table_columns(conn, table)]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def _try_repair(sql: str, err: str, deps: Deps) -> tuple[str, bool]:
    """EXPLAIN 抓到 no such column 時,以 schema fuzzy match 修復欄名。

    回傳 (可能修復後的 sql, 是否通過驗證)。
    """
    columns = _schema_columns(deps.cfg.db_path, deps.cfg.table_name)
    for _ in range(_MAX_COLUMN_REPAIRS):
        m = _NO_SUCH_COLUMN.search(err)
        if not m or not columns:
            return sql, False
        bad_col = m.group(1).split(".")[-1]  # 支援 table.column 形式
        fixed = repair_no_such_column(sql, bad_col, columns)
        if not fixed:
            return sql, False
        sql = fixed
        ok, err = _explain_ok(sql, deps.cfg.db_path)
        if ok:
            return sql, True
    return sql, False


def make_sql_validator(deps: Deps):
    def sql_validator(state: AgentState) -> dict:
        sql = state.get("sql", "")
        retry = state.get("retry_count", 0)

        safe, err = validate_sql(sql)
        if not safe:
            return {"sql_error": err, "retry_count": retry + 1}

        ok, err = _explain_ok(sql, deps.cfg.db_path)
        if not ok:
            repaired, repaired_ok = _try_repair(sql, err, deps)
            if repaired_ok:
                # 修復後仍需通過安全驗證(字面替換欄名不會引入寫操作,保險再驗一次)
                safe, safety_err = validate_sql(repaired)
                if safe:
                    meta = dict(state.get("meta") or {})
                    meta["sql_repaired_from"] = sql
                    return {"sql": repaired, "sql_error": None, "meta": meta}
                err = safety_err
            return {"sql_error": err, "retry_count": retry + 1}

        return {"sql_error": None}

    return sql_validator
