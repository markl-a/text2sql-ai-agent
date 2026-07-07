"""端到端工作流測試:以 Mock LLM 驗證整條 LangGraph(不需真模型)。

涵蓋:意圖→schema→SQL→驗證→執行→格式決策→組合,以及重試與不支援分支。
"""
import pytest

from config import Config
from src.agent.agent import Text2SQLAgent
from src.agent.deps import Deps
from src.agent.graph import build_graph
from src.agent.state import new_state
from src.db.init_db import init_db


class MockResp:
    def __init__(self, content):
        self.content = content


class MockLLM:
    """依 prompt 內容回傳對應假輸出;可注入固定 SQL / intent 以測不同情境。"""
    def __init__(self, sql="SELECT branch, ROUND(SUM(sales),2) AS total FROM sales GROUP BY branch",
                 query_type="group_stat", supported=True, hints=None, language="zh"):
        self.sql = sql
        self.query_type = query_type
        self.supported = supported
        self.hints = hints or []
        self.language = language
        self.calls = []

    def invoke(self, prompt):
        self.calls.append(prompt)
        if "意圖分析器" in prompt:
            import json
            return MockResp(json.dumps({
                "query_type": self.query_type,
                "entities": {}, "language": self.language,
                "hints": self.hints, "supported": self.supported,
            }))
        if "Text2SQL 專家" in prompt:
            return MockResp(f"```sql\n{self.sql}\n```")
        if "資料分析助理" in prompt:
            return MockResp("這是根據資料整理出的口語化回覆。")
        return MockResp("OK")


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    db = tmp_path / "e2e.db"
    init_db(csv_path=c.csv_path, db_path=str(db), table="sales")
    c.db_path = str(db)
    return c


def _run(cfg, llm, question):
    deps = Deps(llm=llm, cfg=cfg)
    graph = build_graph(deps, cfg)
    return graph.invoke(new_state(question))


def test_group_stat_end_to_end_produces_chart(cfg):
    llm = MockLLM()
    final = _run(cfg, llm, "各分店的總銷售額是多少?")
    assert final["response_format"] == "chart"
    assert final["query_result"]["row_count"] == 3
    assert final["final_answer"]
    assert final["chart_spec"]["chart_type"] == "bar"


def test_single_scalar_is_speech(cfg):
    llm = MockLLM(sql="SELECT COUNT(*) AS n FROM sales", query_type="aggregate_single")
    final = _run(cfg, llm, "總共有多少筆交易?")
    assert final["response_format"] == "speech"
    assert final["query_result"]["rows"][0][0] == 1000


def test_unsupported_query_short_circuits(cfg):
    llm = MockLLM(query_type="unsupported", supported=False)
    final = _run(cfg, llm, "預測下個月的銷售額")
    assert final.get("error_message")
    assert "無法" in final["final_answer"] or "sorry" in final["final_answer"].lower()
    # 不應該執行到查詢
    assert not final.get("query_result")


def test_invalid_sql_triggers_retry_then_exhausts(cfg):
    # 一直回傳危險 SQL → 應重試至上限後給「無法理解」訊息
    llm = MockLLM(sql="DROP TABLE sales")
    final = _run(cfg, llm, "刪掉資料")
    assert final.get("error_message")
    assert final["retry_count"] >= cfg.max_retries


def test_multi_turn_history_via_agent(cfg):
    llm = MockLLM(sql="SELECT COUNT(*) AS n FROM sales", query_type="aggregate_single")
    agent = Text2SQLAgent(llm=llm, cfg=cfg)
    agent.ask("總共有多少筆交易?")
    agent.ask("那 Giza 分店呢?")
    assert len(agent.history) == 4  # 2 輪 × (user + assistant)


def test_cache_hit_on_repeat(cfg):
    llm = MockLLM(sql="SELECT COUNT(*) AS n FROM sales", query_type="aggregate_single")
    agent = Text2SQLAgent(llm=llm, cfg=cfg)
    agent.ask("總共有多少筆交易?")
    res2 = agent.ask("總共有多少筆交易?")
    assert res2["cache_hit"] is True
