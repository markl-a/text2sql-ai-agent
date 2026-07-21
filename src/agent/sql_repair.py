"""Schema-aware SQL 欄名修復。

小型地端模型在 temperature=0 下可能「確定性」拼錯欄名(如 branch → brancch),
把錯誤訊息餵回重試也只會重複同一個錯字。此模組在 SQL 驗證抓到
`no such column: X` 時,將 X 與 schema 實際欄名做 fuzzy match,
無歧義時直接以字面修復,讓重試迴圈不必依賴模型自我修正。
"""
from __future__ import annotations

import difflib
import re

# 相似度門檻:branch/brancch ≈ 0.92、product_line/productline ≈ 0.96,
# 低於此值視為模型幻想出的欄位而非拼字錯誤,不修。
_SIMILARITY_CUTOFF = 0.75


def repair_no_such_column(sql: str, bad_col: str, columns: list[str]) -> str | None:
    """將 SQL 中不存在的欄名 bad_col 修復成 schema 中最相近的欄名。

    回傳修復後 SQL;無法安全修復(無相近欄名、有歧義、bad_col 其實存在)時回傳 None。
    """
    if not sql or not bad_col:
        return None

    lowered = {c.lower(): c for c in columns}
    if bad_col.lower() in lowered:
        return None  # 欄名本身合法 → 錯誤另有原因,不亂改

    matches = difflib.get_close_matches(
        bad_col.lower(), list(lowered), n=2, cutoff=_SIMILARITY_CUTOFF
    )
    if not matches:
        return None
    if len(matches) > 1:
        # 兩個候選相似度太接近 → 有歧義,寧可不修
        s0 = difflib.SequenceMatcher(None, bad_col.lower(), matches[0]).ratio()
        s1 = difflib.SequenceMatcher(None, bad_col.lower(), matches[1]).ratio()
        if s0 - s1 < 0.05:
            return None

    target = lowered[matches[0]]
    pattern = re.compile(rf"\b{re.escape(bad_col)}\b", re.IGNORECASE)
    fixed = pattern.sub(target, sql)
    return fixed if fixed != sql else None
