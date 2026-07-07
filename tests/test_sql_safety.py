"""SQL 安全驗證測試(安全關鍵)。"""
import pytest

from src.agent.sql_safety import validate_sql


@pytest.mark.parametrize("sql", [
    "SELECT * FROM sales",
    "SELECT branch, SUM(sales) FROM sales GROUP BY branch",
    "select count(*) from sales where rating > 9",
    "WITH t AS (SELECT branch, SUM(sales) s FROM sales GROUP BY branch) SELECT * FROM t",
    "SELECT product_line, SUM(sales) FROM sales GROUP BY product_line ORDER BY 2 DESC LIMIT 5",
])
def test_valid_select_allowed(sql):
    ok, err = validate_sql(sql)
    assert ok, err


@pytest.mark.parametrize("sql", [
    "INSERT INTO sales VALUES (1)",
    "UPDATE sales SET rating = 10",
    "DELETE FROM sales",
    "DROP TABLE sales",
    "ALTER TABLE sales ADD COLUMN x TEXT",
    "CREATE TABLE hack (id INT)",
    "PRAGMA table_info(sales)",
    "ATTACH DATABASE 'evil.db' AS e",
])
def test_write_and_ddl_blocked(sql):
    ok, err = validate_sql(sql)
    assert not ok
    assert err


def test_multiple_statements_blocked():
    ok, err = validate_sql("SELECT * FROM sales; DROP TABLE sales")
    assert not ok


def test_injection_via_second_statement_blocked():
    ok, _ = validate_sql("SELECT 1; DELETE FROM sales")
    assert not ok


@pytest.mark.parametrize("sql", [
    "SELECT * FROM sales -- comment",
    "SELECT * FROM sales /* block */",
    "SELECT * FROM sales WHERE 1=1 --",
])
def test_comments_blocked(sql):
    ok, err = validate_sql(sql)
    assert not ok
    assert "註解" in err


def test_empty_blocked():
    ok, _ = validate_sql("")
    assert not ok
    ok, _ = validate_sql("   ")
    assert not ok
