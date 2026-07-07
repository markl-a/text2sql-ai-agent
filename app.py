"""Gradio Web UI(加分項)。

提供聊天式介面:輸入自然語言 → 顯示口語回覆 + SQL + 列表/圖表。
支援多輪對話(記住上下文)與中英雙語。

啟動:
  python app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CONFIG, enable_utf8_console  # noqa: E402

enable_utf8_console()


def ensure_db() -> None:
    if not Path(CONFIG.db_path).exists():
        from src.db.init_db import init_db
        init_db()


def build_ui():
    import gradio as gr

    from src.agent.agent import Text2SQLAgent

    ensure_db()
    agent = Text2SQLAgent()

    def respond(message: str, chat_history: list):
        message = (message or "").strip()
        if not message:
            return chat_history, None, "", gr.update()

        res = agent.ask(message)
        answer = res.get("answer") or ""

        # 詳情面板
        details = []
        if res.get("sql"):
            details.append(f"**SQL**\n```sql\n{res['sql']}\n```")
        if res.get("response_format"):
            cache = " (cache hit)" if res.get("cache_hit") else ""
            details.append(f"**回覆格式**: `{res['response_format']}`{cache}")
        if res.get("intent"):
            details.append(f"**意圖**: `{res['intent'].get('query_type')}`")
        details_md = "\n\n".join(details)

        figure = res.get("figure")
        # Gradio messages 格式:每則為 {"role","content"} 字典
        chat_history = chat_history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ]
        # 有圖表則顯示 Plot,否則隱藏
        plot_update = gr.update(value=figure, visible=figure is not None)
        return chat_history, plot_update, details_md, ""

    def reset():
        agent.reset()
        return [], gr.update(value=None, visible=False), "", ""

    with gr.Blocks(title="Text2SQL AI Agent") as demo:
        gr.Markdown(
            "# 🛒 Text2SQL AI Agent\n"
            "用自然語言查詢超市銷售數據(地端 LLM · LangGraph · LangSmith)。"
            "支援中英雙語與多輪對話。"
        )
        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(height=460, label="對話")
                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="例如:各分店的總銷售額是多少?",
                        label="提問", scale=5,
                    )
                    send = gr.Button("送出", variant="primary", scale=1)
                clear = gr.Button("清除對話")
                gr.Examples(
                    examples=[
                        "這個超市總共有多少筆交易?",
                        "各分店的總銷售額是多少?",
                        "比較各產品線的銷售佔比",
                        "列出所有評分高於 9 分的會員交易",
                        "預測下個月的銷售額",
                    ],
                    inputs=msg,
                )
            with gr.Column(scale=2):
                plot = gr.Plot(label="圖表", visible=False)
                details = gr.Markdown(label="查詢詳情")

        send.click(respond, [msg, chatbot], [chatbot, plot, details, msg])
        msg.submit(respond, [msg, chatbot], [chatbot, plot, details, msg])
        clear.click(reset, None, [chatbot, plot, details, msg])

    return demo


if __name__ == "__main__":
    demo = build_ui()
    demo.launch()
