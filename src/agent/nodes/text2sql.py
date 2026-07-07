"""SQL 生成節點 (Text2SQL)。

將使用者意圖 + Schema 組成 Prompt,呼叫地端 LLM 生成 SQLite SELECT 查詢。
重試時會把上一輪的錯誤訊息回饋給模型以修正。
"""
from __future__ import annotations

from src.agent.deps import Deps
from src.agent.state import AgentState
from src.llm.parsing import extract_sql

SYSTEM_PROMPT = """你是一個 SQLite Text2SQL 專家。根據提供的資料表 Schema,將使用者問題轉為「一條」SQLite SELECT 查詢。

嚴格規則:
1. 只能產生 SELECT 查詢,絕不可用 INSERT/UPDATE/DELETE/DROP 等。
2. 只輸出 SQL 本身,用 ```sql ``` 包起來,不要解釋。
3. 欄位名有底線(如 product_line、unit_price),請使用 Schema 中的實際欄名。
4. 日期欄 date 為 'YYYY-MM-DD' 字串;時間欄 time 為 'HH:MM:SS'。
5. 分組統計請善用 GROUP BY;趨勢查詢可用 strftime('%Y-%m', date) 取月份。
6. 需要比較/佔比時,SELECT 分組維度與對應彙總值。
7. 金額類請用 ROUND(SUM(sales), 2) 這類讓結果易讀。"""


def _build_prompt(state: AgentState) -> str:
    schema = state.get("schema", "")
    user_input = state["user_input"]
    intent = state.get("intent") or {}
    prev_error = state.get("sql_error")
    prev_sql = state.get("sql")

    parts = [SYSTEM_PROMPT, "", "資料表 Schema:", schema, ""]
    if intent:
        parts.append(f"查詢意圖: {intent.get('query_type')};實體: {intent.get('entities')}")
    parts.append(f"使用者問題: {user_input}")

    if prev_error and prev_sql:
        parts += [
            "",
            "⚠️ 上一次生成的 SQL 驗證/執行失敗,請修正後重新生成:",
            f"錯誤的 SQL: {prev_sql}",
            f"錯誤訊息: {prev_error}",
        ]
    parts += ["", "請輸出修正後的 SQLite SELECT 查詢:"]
    return "\n".join(parts)


def make_text2sql(deps: Deps):
    def text2sql(state: AgentState) -> dict:
        prompt = _build_prompt(state)
        try:
            resp = deps.llm.invoke(prompt)
            text = getattr(resp, "content", str(resp))
            sql = extract_sql(text)
        except Exception as e:  # noqa: BLE001
            return {"sql": "", "sql_error": f"LLM 生成 SQL 失敗: {e}"}
        return {"sql": sql, "sql_error": None}

    return text2sql
