"""schema-aware SQL 欄名修復(repair_no_such_column)測試。

情境:小模型(temperature=0)可能確定性拼錯欄名(如 branch → brancch),
重試回饋無法自我修正;需以 schema fuzzy match 修復。
"""
import pytest

from config import Config
from src.agent.deps import Deps
from src.agent.nodes.sql_validator import make_sql_validator
from src.agent.sql_repair import repair_no_such_column
from src.db.init_db import init_db

COLUMNS = [
    "invoice_id", "branch", "city", "customer_type", "gender", "product_line",
    "unit_price", "quantity", "tax_5pct", "sales", "date", "time", "payment",
    "cogs", "gross_margin_percentage", "gross_income", "rating",
]


class TestRepairNoSuchColumn:
    def test_repairs_typo_column_everywhere(self):
        sql = "SELECT brancch, ROUND(SUM(sales), 2) FROM sales GROUP BY brancch"
        fixed = repair_no_such_column(sql, "brancch", COLUMNS)
        assert fixed == "SELECT branch, ROUND(SUM(sales), 2) FROM sales GROUP BY branch"

    def test_repairs_underscore_variant(self):
        sql = "SELECT productline, COUNT(*) FROM sales GROUP BY productline"
        fixed = repair_no_such_column(sql, "productline", COLUMNS)
        assert fixed == "SELECT product_line, COUNT(*) FROM sales GROUP BY product_line"

    def test_no_close_match_returns_none(self):
        sql = "SELECT zzz_unknown FROM sales"
        assert repair_no_such_column(sql, "zzz_unknown", COLUMNS) is None

    def test_word_boundary_only(self):
        # bad col "ales" 不應把 sales 內文改壞;且 "ales" 與 sales 很近,允許修復
        sql = "SELECT ales FROM sales"
        fixed = repair_no_such_column(sql, "ales", COLUMNS)
        assert fixed == "SELECT sales FROM sales"

    def test_already_valid_column_returns_none(self):
        # bad_col 本身就在 schema 裡 → 不是拼字問題,不要亂改
        sql = "SELECT branch FROM sales"
        assert repair_no_such_column(sql, "branch", COLUMNS) is None

    def test_case_insensitive_match(self):
        sql = "SELECT Brancch FROM sales GROUP BY Brancch"
        fixed = repair_no_such_column(sql, "Brancch", COLUMNS)
        assert fixed == "SELECT branch FROM sales GROUP BY branch"


class TestValidatorAutoRepair:
    """SQL Validator 在 EXPLAIN 抓到 no such column 時應自動修復再驗證。"""

    @pytest.fixture
    def cfg(self, tmp_path):
        c = Config()
        db = tmp_path / "repair.db"
        init_db(csv_path=c.csv_path, db_path=str(db), table="sales")
        c.db_path = str(db)
        return c

    def test_validator_repairs_typo_and_passes(self, cfg):
        deps = Deps(llm=None, cfg=cfg)
        validator = make_sql_validator(deps)
        state = {"sql": "SELECT brancch, ROUND(SUM(sales), 2) FROM sales GROUP BY brancch",
                 "retry_count": 0}
        out = validator(state)
        assert out.get("sql_error") is None
        assert out.get("sql") == "SELECT branch, ROUND(SUM(sales), 2) FROM sales GROUP BY branch"

    def test_validator_still_fails_on_unrepairable(self, cfg):
        deps = Deps(llm=None, cfg=cfg)
        validator = make_sql_validator(deps)
        state = {"sql": "SELECT zzz_unknown FROM sales", "retry_count": 0}
        out = validator(state)
        assert out.get("sql_error")
        assert out.get("retry_count") == 1
