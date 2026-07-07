"""DB 匯入與 Schema 讀取測試(使用臨時 DB,不依賴 LLM)。"""
import sqlite3

import pytest

from config import CONFIG
from src.db.init_db import init_db
from src.db.schema import get_schema_prompt


@pytest.fixture
def tmp_db(tmp_path):
    db = tmp_path / "test.db"
    summary = init_db(csv_path=CONFIG.csv_path, db_path=str(db), table="sales")
    return str(db), summary


def test_import_row_count(tmp_db):
    _, summary = tmp_db
    assert summary["rows"] == 1000
    assert summary["table"] == "sales"


def test_column_types(tmp_db):
    db, _ = tmp_db
    conn = sqlite3.connect(db)
    info = {r[1]: r[2] for r in conn.execute('PRAGMA table_info("sales")')}
    conn.close()
    assert info["unit_price"] == "REAL"
    assert info["quantity"] == "INTEGER"
    assert info["branch"] == "TEXT"
    assert info["date"] == "TEXT"


def test_date_is_iso(tmp_db):
    db, _ = tmp_db
    conn = sqlite3.connect(db)
    dates = [r[0] for r in conn.execute('SELECT DISTINCT date FROM sales LIMIT 5')]
    conn.close()
    for d in dates:
        assert len(d) == 10 and d[4] == "-" and d[7] == "-"  # YYYY-MM-DD


def test_schema_prompt_contains_columns(tmp_db):
    db, _ = tmp_db
    prompt = get_schema_prompt(db_path=db, table="sales")
    for col in ["branch", "product_line", "sales", "rating", "date"]:
        assert col in prompt
    assert "1000" in prompt  # 總筆數
