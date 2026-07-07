"""地端 LLM 後端抽象。

支援兩種本地後端(env `LLM_BACKEND` 切換):
- "ollama"   → langchain-ollama.ChatOllama
- "lmstudio" → LM Studio 的 OpenAI 相容端點,經 langchain-openai.ChatOpenAI

所有推論皆在本機執行,不呼叫雲端 LLM API(符合試題「地端執行」要求)。
LLM 物件透過 get_llm() 建立,可在測試中以 mock 取代(見 tests/)。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import CONFIG, Config  # noqa: E402


def get_llm(cfg: Config = CONFIG, **overrides: Any):
    """依設定建立本地 LLM chat 模型(LangChain BaseChatModel)。

    lazy import:未安裝對應套件時只在實際使用該後端才報錯。
    """
    backend = overrides.get("backend", cfg.llm_backend)
    model = overrides.get("model", cfg.llm_model)
    temperature = overrides.get("temperature", cfg.llm_temperature)

    if backend == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:
            raise ImportError(
                "需要 langchain-ollama。請執行: pip install langchain-ollama"
            ) from e
        return ChatOllama(
            model=model,
            base_url=cfg.ollama_base_url,
            temperature=temperature,
            num_ctx=cfg.llm_num_ctx,
        )

    if backend == "lmstudio":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise ImportError(
                "需要 langchain-openai。請執行: pip install langchain-openai"
            ) from e
        return ChatOpenAI(
            model=model,
            base_url=cfg.lmstudio_base_url,
            api_key=cfg.lmstudio_api_key,  # LM Studio 不驗證,任意字串即可
            temperature=temperature,
        )

    raise ValueError(
        f"未知的 LLM_BACKEND: '{backend}'。請設為 'ollama' 或 'lmstudio'。"
    )


def check_llm_available(cfg: Config = CONFIG) -> tuple[bool, str]:
    """輕量健康檢查:嘗試對本地模型發一次極短推論。

    回傳 (是否可用, 訊息)。供 setup 腳本與 UI 啟動時診斷。
    """
    try:
        llm = get_llm(cfg)
        resp = llm.invoke("Reply with the single word: OK")
        text = getattr(resp, "content", str(resp))
        return True, f"LLM 可用 (backend={cfg.llm_backend}, model={cfg.llm_model}): {text[:60]}"
    except Exception as e:  # noqa: BLE001
        return False, f"LLM 不可用 (backend={cfg.llm_backend}, model={cfg.llm_model}): {e}"


if __name__ == "__main__":
    from config import enable_utf8_console
    enable_utf8_console()
    ok, msg = check_llm_available()
    print(("✅ " if ok else "❌ ") + msg)
