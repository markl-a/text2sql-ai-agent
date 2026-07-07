"""回覆格式決策測試(核心考核邏輯)。"""
from src.agent.format_rules import decide_format


def test_single_scalar_is_speech():
    intent = {"query_type": "aggregate_single", "hints": ["告訴我"]}
    result = {"columns": ["total"], "rows": [[1000]], "row_count": 1}
    fmt, spec = decide_format(intent, result)
    assert fmt == "speech"
    assert spec is None


def test_group_stat_is_chart_bar():
    intent = {"query_type": "group_stat", "hints": []}
    result = {
        "columns": ["branch", "total_sales"],
        "rows": [["Alex", 106200.37], ["Giza", 106197.67], ["Cairo", 110568.71]],
        "row_count": 3,
    }
    fmt, spec = decide_format(intent, result)
    assert fmt == "chart"
    assert spec["chart_type"] == "bar"
    assert spec["x"] == "branch"
    assert spec["y"] == "total_sales"


def test_proportion_is_pie():
    intent = {"query_type": "comparison", "hints": ["佔比", "比較"]}
    result = {
        "columns": ["product_line", "total_sales"],
        "rows": [["Food and beverages", 100], ["Sports and travel", 98],
                 ["Electronic accessories", 96], ["Health and beauty", 90]],
        "row_count": 4,
    }
    fmt, spec = decide_format(intent, result)
    assert fmt == "chart"
    assert spec["chart_type"] == "pie"


def test_time_series_is_line():
    intent = {"query_type": "trend", "hints": ["趨勢"]}
    result = {
        "columns": ["month", "total_sales"],
        "rows": [["2019-01", 100], ["2019-02", 120], ["2019-03", 110]],
        "row_count": 3,
    }
    fmt, spec = decide_format(intent, result)
    assert fmt == "chart"
    assert spec["chart_type"] == "line"


def test_detail_is_list():
    intent = {"query_type": "detail", "hints": ["列出"]}
    result = {
        "columns": ["invoice_id", "product_line", "rating"],
        "rows": [[f"A{i}", "Health and beauty", 9.1] for i in range(10)],
        "row_count": 10,
    }
    fmt, spec = decide_format(intent, result)
    assert fmt == "list"
    assert spec is None


def test_empty_result_is_speech():
    fmt, spec = decide_format({"query_type": "detail"}, {"columns": ["x"], "rows": [], "row_count": 0})
    assert fmt == "speech"


def test_list_hint_overrides_to_list_even_with_multi_numeric():
    # 「列出」明確要求明細,即使多欄也應為 list 而非 chart
    intent = {"query_type": "detail", "hints": ["列出"]}
    result = {
        "columns": ["invoice_id", "unit_price", "quantity"],
        "rows": [["A1", 10.0, 2], ["A2", 20.0, 3]],
        "row_count": 2,
    }
    fmt, _ = decide_format(intent, result)
    assert fmt == "list"
