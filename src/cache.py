"""簡易 query result 快取(加分項)。

以「正規化後的 SQL 字串」為 key,快取執行結果,避免重複查詢重跑。
純記憶體、行程內、LRU 上限;測試友善且無外部依賴。
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any, Optional


class QueryCache:
    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        self._store: "OrderedDict[str, Any]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(sql: str) -> str:
        # 正規化:小寫 + 壓縮空白 + 去尾端分號,讓等價 SQL 命中同一 key
        s = re.sub(r"\s+", " ", sql.strip().lower()).rstrip(";").strip()
        return s

    def get(self, sql: str) -> Optional[Any]:
        key = self._key(sql)
        if key in self._store:
            self._store.move_to_end(key)
            self.hits += 1
            return self._store[key]
        self.misses += 1
        return None

    def set(self, sql: str, value: Any) -> None:
        key = self._key(sql)
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()
        self.hits = self.misses = 0

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses,
                "size": len(self._store),
                "hit_rate": round(self.hits / total, 3) if total else 0.0}
