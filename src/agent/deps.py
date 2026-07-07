"""節點共用依賴容器。

以依賴注入方式把 LLM、設定、快取傳給各節點,避免全域狀態,
並讓測試能注入 mock LLM。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from config import CONFIG, Config
from src.cache import QueryCache


@dataclass
class Deps:
    llm: Any                       # LangChain BaseChatModel(或測試用 mock)
    cfg: Config = field(default_factory=lambda: CONFIG)
    cache: Optional[QueryCache] = None

    def __post_init__(self):
        if self.cache is None:
            self.cache = QueryCache()
