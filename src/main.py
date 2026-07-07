"""CLI 入口:互動式自然語言問答。

用法:
  python -m src.main            # 進入互動模式
  python -m src.main "各分店的總銷售額是多少?"   # 單次查詢
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import CONFIG, enable_utf8_console  # noqa: E402


def ensure_db() -> None:
    """DB 不存在時自動從 CSV 匯入。"""
    if not Path(CONFIG.db_path).exists():
        print("資料庫不存在,正在從 CSV 匯入...")
        from src.db.init_db import init_db
        summary = init_db()
        print(f"✅ 已匯入 {summary['rows']} 筆資料。\n")


def _print_result(res: dict) -> None:
    print("\n🤖 " + (res.get("answer") or ""))
    if res.get("sql"):
        print(f"\n   [SQL] {res['sql']}")
    if res.get("chart_path"):
        print(f"   [圖表已存至] {res['chart_path']}")
    fmt = res.get("response_format")
    if fmt:
        extra = " (cache hit)" if res.get("cache_hit") else ""
        print(f"   [格式] {fmt}{extra}")
    print()


def main() -> None:
    enable_utf8_console()
    ensure_db()

    from src.agent.agent import Text2SQLAgent
    print("正在初始化 Agent(連線地端 LLM)...")
    try:
        agent = Text2SQLAgent()
    except Exception as e:  # noqa: BLE001
        print(f"❌ Agent 初始化失敗: {e}")
        print("請確認已啟動 Ollama / LM Studio 並下載模型,詳見 README。")
        sys.exit(1)

    # 單次查詢模式
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        _print_result(agent.ask(question))
        return

    # 互動模式
    print("\n=== Text2SQL AI Agent ===")
    print("輸入自然語言問題(輸入 'exit' / 'quit' 離開,'reset' 清除對話記憶)\n")
    while True:
        try:
            question = input("💬 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再見!")
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print("再見!")
            break
        if question.lower() == "reset":
            agent.reset()
            print("(已清除對話記憶)\n")
            continue
        try:
            _print_result(agent.ask(question))
        except Exception as e:  # noqa: BLE001
            print(f"❌ 發生錯誤: {e}\n")


if __name__ == "__main__":
    main()
