"""集中式設定。從環境變數 / .env 讀取,提供給全專案使用。"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def enable_utf8_console() -> None:
    """讓 stdout/stderr 使用 UTF-8,避免 Windows cp950 主控台印中文/emoji 崩潰。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv 為選用;未安裝時直接讀 os.environ
    pass

ROOT = Path(__file__).resolve().parent


def _abs(p: str) -> str:
    """相對路徑一律解析成以專案根目錄為基準的絕對路徑。"""
    path = Path(p)
    return str(path if path.is_absolute() else ROOT / path)


@dataclass
class Config:
    # LLM
    llm_backend: str = os.getenv("LLM_BACKEND", "ollama").lower()
    llm_model: str = os.getenv("LLM_MODEL", "gemma3n:e4b")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    lmstudio_base_url: str = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    lmstudio_api_key: str = os.getenv("LMSTUDIO_API_KEY", "lm-studio")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0"))
    llm_num_ctx: int = int(os.getenv("LLM_NUM_CTX", "8192"))

    # DB
    db_path: str = field(default_factory=lambda: _abs(os.getenv("DB_PATH", "data/supermarket.db")))
    csv_path: str = field(default_factory=lambda: _abs(os.getenv("CSV_PATH", "data/SuperMarket Analysis.csv")))
    table_name: str = os.getenv("TABLE_NAME", "sales")

    # SQL 安全
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "1000"))
    sql_timeout_seconds: int = int(os.getenv("SQL_TIMEOUT_SECONDS", "10"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))

    # LangSmith
    langsmith_tracing: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    langsmith_api_key: str = os.getenv("LANGSMITH_API_KEY", "")
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "text2sql-agent")
    langsmith_endpoint: str = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    # 圖表輸出目錄
    chart_dir: str = field(default_factory=lambda: _abs("data/charts"))


CONFIG = Config()


def setup_langsmith(cfg: Config = CONFIG) -> bool:
    """依設定初始化 LangSmith Tracing。

    回傳 True 表示已啟用。未設 key 時安靜停用,不影響 Agent 執行。
    LangChain 生態透過這些環境變數自動接上 tracing。
    """
    if cfg.langsmith_tracing and cfg.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_TRACING_V2"] = "true"  # 相容舊變數名
        os.environ["LANGSMITH_API_KEY"] = cfg.langsmith_api_key
        os.environ["LANGCHAIN_API_KEY"] = cfg.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = cfg.langsmith_project
        os.environ["LANGCHAIN_PROJECT"] = cfg.langsmith_project
        os.environ["LANGSMITH_ENDPOINT"] = cfg.langsmith_endpoint
        return True
    # 明確關閉,避免殘留環境變數誤觸發
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    return False
