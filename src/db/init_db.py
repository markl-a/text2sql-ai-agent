"""將 Supermarket CSV 匯入 SQLite,建立型別正確的 Table Schema。

設計重點:
- 原始欄位含空格與 %(如 "Tax 5%"),不利 SQL 生成 → 正規化為 snake_case。
- 日期/時間轉為可排序的 ISO 格式(TEXT),讓 SQLite 日期函式可用。
- 數值欄位以 REAL / INTEGER 明確定型。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

# 專案根匯入
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import CONFIG  # noqa: E402

# 原始欄名 → (正規化欄名, SQLite 型別)
COLUMN_MAP: dict[str, tuple[str, str]] = {
    "Invoice ID": ("invoice_id", "TEXT"),
    "Branch": ("branch", "TEXT"),
    "City": ("city", "TEXT"),
    "Customer type": ("customer_type", "TEXT"),
    "Gender": ("gender", "TEXT"),
    "Product line": ("product_line", "TEXT"),
    "Unit price": ("unit_price", "REAL"),
    "Quantity": ("quantity", "INTEGER"),
    "Tax 5%": ("tax_5pct", "REAL"),
    "Sales": ("sales", "REAL"),
    "Date": ("date", "TEXT"),   # 存 ISO 'YYYY-MM-DD'
    "Time": ("time", "TEXT"),   # 存 24h 'HH:MM:SS'
    "Payment": ("payment", "TEXT"),
    "cogs": ("cogs", "REAL"),
    "gross margin percentage": ("gross_margin_percentage", "REAL"),
    "gross income": ("gross_income", "REAL"),
    "Rating": ("rating", "REAL"),
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """去除欄名前後空白後,依 COLUMN_MAP 重新命名。"""
    df = df.rename(columns=lambda c: str(c).strip())
    missing = [orig for orig in COLUMN_MAP if orig not in df.columns]
    if missing:
        raise ValueError(
            f"CSV 缺少預期欄位: {missing}\n實際欄位: {list(df.columns)}"
        )
    rename = {orig: new for orig, (new, _) in COLUMN_MAP.items()}
    return df[list(COLUMN_MAP.keys())].rename(columns=rename)


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """轉換日期/時間/數值型別。"""
    # 日期: 支援 M/D/YYYY → ISO;無法解析者保留 NaT→None
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    # 時間: 12 小時制(1:08:00 PM)→ 24 小時制 HH:MM:SS
    parsed_time = pd.to_datetime(df["time"], format="%I:%M:%S %p", errors="coerce")
    if parsed_time.isna().any():  # 少數非 12h 格式者才回退,避免整欄觸發 dateutil 警告
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fallback = pd.to_datetime(df["time"], errors="coerce")
        parsed_time = parsed_time.fillna(fallback)
    df["time"] = parsed_time.dt.strftime("%H:%M:%S")

    for orig, (new, typ) in COLUMN_MAP.items():
        if typ == "REAL":
            df[new] = pd.to_numeric(df[new], errors="coerce")
        elif typ == "INTEGER":
            df[new] = pd.to_numeric(df[new], errors="coerce").astype("Int64")
    return df


def _create_table(conn: sqlite3.Connection, table: str) -> None:
    cols_ddl = ",\n  ".join(
        f'"{new}" {typ}' for (new, typ) in COLUMN_MAP.values()
    )
    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.execute(f'CREATE TABLE "{table}" (\n  {cols_ddl}\n)')


def init_db(
    csv_path: str | None = None,
    db_path: str | None = None,
    table: str | None = None,
) -> dict:
    """讀 CSV → 建表 → 匯入。回傳匯入摘要。"""
    csv_path = csv_path or CONFIG.csv_path
    db_path = db_path or CONFIG.db_path
    table = table or CONFIG.table_name

    if not Path(csv_path).exists():
        raise FileNotFoundError(
            f"找不到 CSV: {csv_path}\n"
            "請先下載 Kaggle 資料或執行 scripts/generate_sample_csv.py 產生樣本。"
        )

    df = pd.read_csv(csv_path)
    df = _normalize_columns(df)
    df = _coerce_types(df)

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        _create_table(conn, table)
        df.to_sql(table, conn, if_exists="append", index=False)
        conn.commit()
        count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        conn.close()

    return {"db_path": db_path, "table": table, "rows": int(count),
            "columns": [n for n, _ in COLUMN_MAP.values()]}


if __name__ == "__main__":
    from config import enable_utf8_console
    enable_utf8_console()
    summary = init_db()
    print(f"✅ 匯入完成: {summary['rows']} 筆 → {summary['db_path']} (table: {summary['table']})")
    print(f"   欄位: {', '.join(summary['columns'])}")
