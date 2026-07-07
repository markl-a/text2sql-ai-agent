"""Schema 讀取工具:自動從 SQLite 取得欄位資訊 + 範例值,組成給 LLM 的 Prompt 片段。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import CONFIG  # noqa: E402

# 欄位人類可讀說明(協助 LLM 將自然語言對應到正確欄位)
COLUMN_DESCRIPTIONS: dict[str, str] = {
    "invoice_id": "交易唯一識別碼 (例: 750-67-8428)",
    "branch": "超市分店代號 (Alex / Giza / Cairo)",
    "city": "分店所在城市 (Yangon / Naypyitaw / Mandalay)",
    "customer_type": "客戶類型 (Member / Normal)",
    "gender": "客戶性別 (Male / Female)",
    "product_line": "產品線類別 (Health and beauty, Electronic accessories, "
                    "Home and lifestyle, Sports and travel, Food and beverages, "
                    "Fashion accessories)",
    "unit_price": "單價",
    "quantity": "購買數量",
    "tax_5pct": "5% 稅額 (原欄名 'Tax 5%')",
    "sales": "銷售總額(含稅)",
    "date": "交易日期,ISO 格式 'YYYY-MM-DD' (資料範圍 2019-01 ~ 2019-03)",
    "time": "交易時間,24 小時制 'HH:MM:SS'",
    "payment": "付款方式 (Ewallet / Cash / Credit card)",
    "cogs": "銷貨成本 (Cost of Goods Sold)",
    "gross_margin_percentage": "毛利率(固定約 4.7619%)",
    "gross_income": "毛利",
    "rating": "顧客滿意度評分 (1-10)",
}


def get_table_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    """回傳欄位 metadata: name, type, notnull, pk。"""
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [
        {"name": r[1], "type": r[2], "notnull": bool(r[3]), "pk": bool(r[5])}
        for r in rows
    ]


def get_sample_values(conn: sqlite3.Connection, table: str, column: str, limit: int = 3) -> list:
    """取某欄位的去重範例值。"""
    try:
        rows = conn.execute(
            f'SELECT DISTINCT "{column}" FROM "{table}" '
            f'WHERE "{column}" IS NOT NULL LIMIT ?', (limit,)
        ).fetchall()
        return [r[0] for r in rows]
    except sqlite3.Error:
        return []


def get_schema_prompt(db_path: str | None = None, table: str | None = None) -> str:
    """組出給 LLM 參考的 schema 描述(欄名 + 型別 + 說明 + 範例值)。"""
    db_path = db_path or CONFIG.db_path
    table = table or CONFIG.table_name

    if not Path(db_path).exists():
        raise FileNotFoundError(f"找不到資料庫: {db_path},請先執行 init_db。")

    conn = sqlite3.connect(db_path)
    try:
        columns = get_table_columns(conn, table)
        if not columns:
            raise ValueError(f"資料表 '{table}' 不存在或無欄位。")

        lines = [f"資料表名稱: {table}", "欄位:"]
        for col in columns:
            name = col["name"]
            desc = COLUMN_DESCRIPTIONS.get(name, "")
            samples = get_sample_values(conn, table, name)
            sample_str = ", ".join(str(s) for s in samples)
            lines.append(
                f'  - "{name}" ({col["type"]}) — {desc}'
                + (f" | 範例: {sample_str}" if sample_str else "")
            )
        row_count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        lines.append(f"總筆數: {row_count}")
        return "\n".join(lines)
    finally:
        conn.close()


if __name__ == "__main__":
    from config import enable_utf8_console
    enable_utf8_console()
    print(get_schema_prompt())
