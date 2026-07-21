"""LLM 輸出解析(JSON / SQL 抽取)測試。"""
from src.llm.parsing import extract_json, extract_sql


def test_extract_json_plain():
    assert extract_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_extract_json_fenced():
    text = 'thinking...\n```json\n{"query_type": "detail", "supported": true}\n```\ndone'
    obj = extract_json(text)
    assert obj["query_type"] == "detail"
    assert obj["supported"] is True


def test_extract_json_embedded_with_noise():
    text = 'Here is the result: {"x": {"y": 2}} hope it helps!'
    assert extract_json(text) == {"x": {"y": 2}}


def test_extract_json_none():
    assert extract_json("no json here") == {}
    assert extract_json("") == {}


def test_extract_sql_fenced():
    text = "```sql\nSELECT * FROM sales;\n```"
    assert extract_sql(text) == "SELECT * FROM sales"


def test_extract_sql_prefix():
    assert extract_sql("SQL: SELECT branch FROM sales") == "SELECT branch FROM sales"


def test_extract_sql_with_reasoning():
    text = "我認為應該這樣查詢:\nSELECT COUNT(*) FROM sales WHERE rating > 9"
    assert extract_sql(text).startswith("SELECT COUNT(*)")


def test_extract_sql_strips_trailing_semicolon_and_second_stmt():
    assert extract_sql("SELECT 1; DROP TABLE x") == "SELECT 1"


def test_extract_sql_sanitizes_sentencepiece_underline():
    # gemma3n 偶爾把 sentencepiece 空白記號 ▁(U+2581) 原樣輸出當縮排
    text = "```sql\nSELECT\n▁▁product_line,\n▁▁SUM(sales)\nFROM sales\nGROUP BY product_line\n```"
    sql = extract_sql(text)
    assert "▁" not in sql
    assert "product_line" in sql and "SUM(sales)" in sql


def test_extract_sql_sanitizes_nbsp_and_zero_width():
    text = "```sql\nSELECT COUNT(*)​ FROM sales\n```"
    assert extract_sql(text) == "SELECT COUNT(*) FROM sales"
