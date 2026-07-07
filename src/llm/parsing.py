"""從 LLM 文字輸出穩健抽取結構化內容(JSON / SQL)。

Gemma 經 Ollama 的 native function-calling 不穩定,故改以強約束 prompt
搭配這裡的容錯解析:處理 ```json 圍欄、思考前綴、多餘文字等常見雜訊。
"""
from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    """從文字中抽出第一個 JSON 物件並解析。找不到則回傳 {}。"""
    if not text:
        return {}

    # 1) 去除 ```json ... ``` 或 ``` ... ``` 圍欄
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else text

    # 2) 直接嘗試整段解析
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass

    # 3) 以括號配對掃描出第一個完整 JSON 物件
    start = candidate.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        blob = candidate[start:i + 1]
                        try:
                            obj = json.loads(blob)
                            if isinstance(obj, dict):
                                return obj
                        except json.JSONDecodeError:
                            break  # 這個起點失敗,換下一個 '{'
        start = candidate.find("{", start + 1)

    return {}


def extract_sql(text: str) -> str:
    """從 LLM 輸出抽出 SQL 查詢字串。

    處理 ```sql 圍欄、'SQL:' 前綴、思考文字等;回傳去除尾端分號的單一查詢。
    """
    if not text:
        return ""

    # 1) ```sql ... ``` 圍欄優先
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        sql = fenced.group(1).strip()
    else:
        sql = text.strip()
        # 去除常見前綴
        sql = re.sub(r"^\s*(sql\s*[:：]|query\s*[:：])", "", sql, flags=re.IGNORECASE).strip()
        # 從第一個 SELECT / WITH 開始擷取
        m = re.search(r"\b(SELECT|WITH)\b", sql, re.IGNORECASE)
        if m:
            sql = sql[m.start():]

    # 只取第一個語句(分號前),並去尾端分號
    sql = sql.split(";")[0].strip()
    return sql
