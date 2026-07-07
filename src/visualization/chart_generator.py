"""圖表生成 (Plotly)。

依 chart_spec(bar / line / pie)與查詢結果生成圖表。
- 回傳 Plotly Figure(供 Gradio 內嵌互動顯示)
- 可選存成 PNG(需 kaleido)供 CLI / 附檔

設計成不需 GUI、可在無顯示環境執行。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from config import CONFIG


def _column_index(columns: list, name: str) -> int:
    return columns.index(name) if name in columns else 0


def build_figure(chart_spec: dict, query_result: dict):
    """依 chart_spec 建立 Plotly Figure。回傳 fig(失敗回傳 None)。"""
    try:
        import plotly.graph_objects as go
    except ImportError as e:
        raise ImportError("需要 plotly。請執行: pip install plotly") from e

    columns = query_result.get("columns", [])
    rows = query_result.get("rows", [])
    if not columns or not rows:
        return None

    x_name = chart_spec.get("x", columns[0])
    y_name = chart_spec.get("y", columns[-1])
    chart_type = chart_spec.get("chart_type", "bar")
    title = chart_spec.get("title", f"{y_name} by {x_name}")

    xi = _column_index(columns, x_name)
    yi = _column_index(columns, y_name)
    x_vals = [r[xi] for r in rows]
    y_vals = [r[yi] for r in rows]

    if chart_type == "line":
        # 折線圖依 x 排序(通常為時間)
        pairs = sorted(zip(x_vals, y_vals), key=lambda p: str(p[0]))
        x_vals = [p[0] for p in pairs]
        y_vals = [p[1] for p in pairs]
        fig = go.Figure(go.Scatter(x=x_vals, y=y_vals, mode="lines+markers", name=y_name))
    elif chart_type == "pie":
        fig = go.Figure(go.Pie(labels=[str(v) for v in x_vals], values=y_vals, hole=0.3))
    else:  # bar
        fig = go.Figure(go.Bar(x=[str(v) for v in x_vals], y=y_vals, name=y_name))

    fig.update_layout(
        title=title,
        xaxis_title=None if chart_type == "pie" else x_name,
        yaxis_title=None if chart_type == "pie" else y_name,
        template="plotly_white",
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def save_figure_html(fig, filename: str, chart_dir: Optional[str] = None) -> Optional[str]:
    """存成互動式 HTML(可靠、跨平台、無外部行程)。失敗回傳 None。"""
    if fig is None:
        return None
    chart_dir = chart_dir or CONFIG.chart_dir
    Path(chart_dir).mkdir(parents=True, exist_ok=True)
    if not filename.lower().endswith(".html"):
        filename = Path(filename).stem + ".html"
    path = os.path.join(chart_dir, filename)
    try:
        fig.write_html(path, include_plotlyjs="cdn")
        return path
    except Exception:  # noqa: BLE001
        return None


def save_figure_png(fig, filename: str, chart_dir: Optional[str] = None) -> Optional[str]:
    """存 PNG(需 kaleido)。可能失敗或在部分平台不穩定,故非預設,失敗回傳 None。"""
    if fig is None:
        return None
    chart_dir = chart_dir or CONFIG.chart_dir
    Path(chart_dir).mkdir(parents=True, exist_ok=True)
    if not filename.lower().endswith(".png"):
        filename = Path(filename).stem + ".png"
    path = os.path.join(chart_dir, filename)
    try:
        fig.write_image(path)  # 需要 kaleido(見 README 版本相容說明)
        return path
    except Exception:  # noqa: BLE001
        return None


def generate_chart(chart_spec: dict, query_result: dict,
                   filename: str = "chart.html", fmt: str = "html") -> dict:
    """便利函式:建立 figure 並存檔。回傳 {figure, path}。

    fmt: "html"(預設,可靠) 或 "png"(需 kaleido,部分平台不穩)。
    Gradio 直接使用 figure 互動顯示,不需存檔。
    """
    fig = build_figure(chart_spec, query_result)
    if fig is None:
        return {"figure": None, "path": None}
    path = save_figure_png(fig, filename) if fmt == "png" else save_figure_html(fig, filename)
    return {"figure": fig, "path": path}
