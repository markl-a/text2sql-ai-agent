"""意圖理解節點 (Intent Parser)。

分析使用者自然語言:判斷查詢類型、抽取實體、偵測語言與語意暗示,
並判定是否為資料集可回答的查詢(如「預測」屬不支援)。
"""
from __future__ import annotations

from src.agent.deps import Deps
from src.agent.state import AgentState
from src.llm.parsing import extract_json

QUERY_TYPES = {
    "aggregate_single", "detail", "group_stat", "trend", "comparison", "unsupported",
}

SYSTEM_PROMPT = """你是一個資料查詢意圖分析器。分析使用者對「超市銷售資料」的提問,輸出 JSON。

查詢類型 query_type 六選一:
- "aggregate_single": 求單一彙總值(如總筆數、總銷售額、平均評分)
- "detail": 列出符合條件的明細紀錄
- "group_stat": 依某維度分組統計(如各分店/各產品線的銷售額)
- "trend": 隨時間變化的趨勢(含日期/月份維度)
- "comparison": 比較不同類別(常涉及佔比、分佈)
- "unsupported": 資料無法回答(如預測未來、需外部資訊)

只輸出如下 JSON,不要多餘文字:
{
  "query_type": "...",
  "entities": {"branch": null, "product_line": null, "date_range": null, "filters": []},
  "language": "zh 或 en",
  "hints": ["使用者用到的語意暗示詞,如 比較/趨勢/佔比/列出/告訴我"],
  "supported": true 或 false
}"""


def _heuristic_intent(text: str) -> dict:
    """LLM 失敗時的保底啟發式判斷。"""
    lc = text.lower()
    language = "zh" if any("一" <= ch <= "鿿" for ch in text) else "en"
    unsupported_kw = ["預測", "predict", "forecast", "下個月", "未來", "next month", "future"]
    supported = not any(k in lc or k in text for k in unsupported_kw)
    if not supported:
        qtype = "unsupported"
    elif any(k in text or k in lc for k in ["比較", "佔比", "占比", "分佈", "compare", "proportion", "distribution"]):
        qtype = "comparison"
    elif any(k in text or k in lc for k in ["趨勢", "trend", "隨時間", "over time", "每月", "每天"]):
        qtype = "trend"
    elif any(k in text or k in lc for k in ["各", "每個", "分組", "by ", "per ", "group"]):
        qtype = "group_stat"
    elif any(k in text or k in lc for k in ["列出", "哪些", "明細", "list", "show", "which"]):
        qtype = "detail"
    else:
        qtype = "aggregate_single"
    return {
        "query_type": qtype,
        "entities": {},
        "language": language,
        "hints": [],
        "supported": supported,
    }


def make_intent_parser(deps: Deps):
    def intent_parser(state: AgentState) -> dict:
        user_input = state["user_input"]
        history = state.get("history") or []
        context = ""
        if history:
            recent = history[-4:]
            context = "\n先前對話(供指代消解,如『那 Giza 呢?』):\n" + \
                "\n".join(f"{m['role']}: {m['content']}" for m in recent)

        prompt = f"{SYSTEM_PROMPT}\n{context}\n\n使用者提問: {user_input}\n\nJSON:"
        try:
            resp = deps.llm.invoke(prompt)
            text = getattr(resp, "content", str(resp))
            parsed = extract_json(text)
        except Exception:  # noqa: BLE001 — LLM 失敗時走保底
            parsed = {}

        if not parsed or parsed.get("query_type") not in QUERY_TYPES:
            parsed = _heuristic_intent(user_input)

        # 正規化欄位
        intent = {
            "query_type": parsed.get("query_type", "aggregate_single"),
            "entities": parsed.get("entities") or {},
            "language": parsed.get("language") or _heuristic_intent(user_input)["language"],
            "hints": parsed.get("hints") or [],
            "supported": bool(parsed.get("supported", True)),
        }
        if intent["query_type"] == "unsupported":
            intent["supported"] = False

        return {"intent": intent}

    return intent_parser
