"""最終回覆組合節點 (Response Composer)。

無論決策結果為何,一律先產生自然、口語化的文字回覆(非直接把 SQL 結果轉字串);
若為 list/chart,再把表格或圖表附加在文字之後。
也負責處理不支援查詢與重試耗盡的友善訊息。
"""
from __future__ import annotations

from src.agent.deps import Deps
from src.agent.state import AgentState
from src.visualization.chart_generator import generate_chart

MAX_ROWS_IN_PROMPT = 30      # 餵給 LLM 摘要的最大列數
MAX_ROWS_IN_TABLE = 20       # markdown 表格顯示上限

SPEECH_SYSTEM = """你是一個友善的資料分析助理。根據使用者問題與查詢結果,用「自然、口語」的方式回答。
規則:
1. 用使用者的語言回答(中文問就用中文,英文問就用英文)。
2. 直接講重點與洞察,不要複述 SQL,也不要說「根據查詢結果」這類贅語太多。
3. 數字適度四捨五入、加上千分位更好讀。
4. 若有多筆或分組資料,做簡短歸納(如誰最高、整體趨勢)。
5. 回答簡潔,2-4 句即可。"""


def _markdown_table(columns: list, rows: list, limit: int = MAX_ROWS_IN_TABLE) -> str:
    if not columns:
        return ""
    header = "| " + " | ".join(str(c) for c in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body_rows = rows[:limit]
    lines = [header, sep]
    for r in body_rows:
        lines.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    table = "\n".join(lines)
    if len(rows) > limit:
        table += f"\n\n_(僅顯示前 {limit} 筆,共 {len(rows)} 筆)_"
    return table


def _result_preview(columns: list, rows: list) -> str:
    preview = rows[:MAX_ROWS_IN_PROMPT]
    lines = ["欄位: " + ", ".join(str(c) for c in columns)]
    for r in preview:
        lines.append(str(list(r)))
    if len(rows) > MAX_ROWS_IN_PROMPT:
        lines.append(f"...(共 {len(rows)} 筆)")
    return "\n".join(lines)


def _fallback_speech(state: AgentState) -> str:
    result = state.get("query_result") or {}
    cols, rows = result.get("columns", []), result.get("rows", [])
    n = result.get("row_count", len(rows))
    if n == 0:
        return "查無符合條件的資料。"
    if n == 1 and len(cols) == 1:
        return f"查詢結果:{cols[0]} = {rows[0][0]}。"
    return f"查詢共回傳 {n} 筆資料,詳見下方。"


def make_response_composer(deps: Deps):
    def response_composer(state: AgentState) -> dict:
        # 1) 不支援 / 重試耗盡:直接給預先準備好的友善訊息
        if state.get("error_message"):
            return {"final_answer": state["error_message"]}

        result = state.get("query_result") or {}
        columns = result.get("columns", [])
        rows = result.get("rows", [])
        fmt = state.get("response_format", "speech")

        # 2) 口語回覆(LLM 生成,失敗則 fallback)
        prompt = (
            f"{SPEECH_SYSTEM}\n\n使用者問題: {state['user_input']}\n\n"
            f"查詢結果:\n{_result_preview(columns, rows)}\n\n請用口語回答:"
        )
        try:
            resp = deps.llm.invoke(prompt)
            speech = getattr(resp, "content", str(resp)).strip()
            if not speech:
                speech = _fallback_speech(state)
        except Exception:  # noqa: BLE001
            speech = _fallback_speech(state)

        out: dict = {"final_answer": speech}
        meta = dict(state.get("meta", {}))

        # 3) 附加列表
        if fmt == "list":
            table = _markdown_table(columns, rows)
            if table:
                out["final_answer"] = f"{speech}\n\n{table}"

        # 4) 附加圖表
        elif fmt == "chart":
            chart_spec = state.get("chart_spec") or {}
            try:
                chart = generate_chart(chart_spec, result, filename="chart.html")
                meta["figure"] = chart["figure"]
                out["chart_path"] = chart["path"]
                ctype = chart_spec.get("chart_type", "bar")
                note = f"\n\n[已生成{ {'bar':'長條圖','line':'折線圖','pie':'圓餅圖'}.get(ctype, '圖表') }]"
                out["final_answer"] = f"{speech}{note}"
            except Exception as e:  # noqa: BLE001 — 圖表失敗退回口語+表格
                table = _markdown_table(columns, rows)
                out["final_answer"] = f"{speech}\n\n(圖表生成失敗: {e})\n\n{table}"

        out["meta"] = meta
        return out

    return response_composer
