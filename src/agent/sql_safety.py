"""SQL 安全驗證(僅允許唯讀 SELECT)。

雙層防護的第一層(靜態):
- 僅允許單一語句
- 僅允許 SELECT 或 WITH...SELECT
- 阻擋任何寫入/DDL/危險關鍵字
- 阻擋註解(避免以 -- 或 /* */ 夾帶注入)

與 sqlparse 搭配,獨立於 LLM 與 DB,故可完整單元測試。
"""
from __future__ import annotations

import re

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Comment, DML, Keyword

# 明確禁止的關鍵字(大小寫不敏感)
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
    "TRUNCATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX",
    "GRANT", "REVOKE", "MERGE", "UPSERT", "COMMIT", "ROLLBACK",
}


def _strip_statements(sql: str) -> list[Statement]:
    parsed = sqlparse.parse(sql)
    # 過濾掉僅含空白的空語句
    return [s for s in parsed if s.token_first(skip_cm=True) is not None]


def validate_sql(sql: str) -> tuple[bool, str]:
    """回傳 (是否安全, 錯誤訊息)。安全時錯誤訊息為空字串。"""
    if not sql or not sql.strip():
        return False, "SQL 為空。"

    stripped = sql.strip()

    # 阻擋註解(在 tokenize 前先用字面偵測,涵蓋 -- 與 /* */)
    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        return False, "基於安全考量,SQL 不允許包含註解。"

    statements = _strip_statements(stripped)
    if len(statements) == 0:
        return False, "SQL 為空。"
    if len(statements) > 1:
        return False, "基於安全考量,僅允許單一 SELECT 語句(偵測到多個語句)。"

    stmt = statements[0]

    # 首個有意義 token 必須是 SELECT 或 WITH(CTE)
    first = stmt.token_first(skip_cm=True)
    first_val = first.value.upper() if first else ""
    stmt_type = stmt.get_type()  # 'SELECT' / 'INSERT' / 'UNKNOWN' ...
    is_select = stmt_type == "SELECT" or first_val == "WITH"
    if not is_select:
        return False, f"僅允許 SELECT 查詢(偵測到 {stmt_type or first_val or '未知'} 操作)。"

    # 逐 token 掃描禁止關鍵字與註解 token
    for token in stmt.flatten():
        if token.ttype in Comment or token.ttype in (Comment.Single, Comment.Multiline):
            return False, "基於安全考量,SQL 不允許包含註解。"
        if token.ttype in (Keyword, DML, Keyword.DDL, Keyword.DML):
            word = token.value.upper()
            if word in FORBIDDEN_KEYWORDS:
                return False, f"偵測到禁止的操作: {word}。僅允許唯讀 SELECT 查詢。"

    # 保險:整段以字界比對禁止關鍵字(涵蓋 sqlparse 未歸類的情況)
    upper = stripped.upper()
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            return False, f"偵測到禁止的操作: {kw}。僅允許唯讀 SELECT 查詢。"

    return True, ""
