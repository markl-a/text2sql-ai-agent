# Text2SQL AI Agent — 設計規格 (Design Spec)

- 日期: 2026-07-07
- 目標: 基於地端模型打造 Text2SQL AI Agent(面試 take-home)
- 交付範圍: 完整交付(全節點 + setup + LangSmith + 圖表 + 架構文件 + 部分加分項)

## 1. 目標與需求摘要

使用者用自然語言提問超市銷售數據 → Agent 自動轉 SQL → 執行 → 依意圖與結果**自主決定回覆格式**(口語 / 列表 / 圖表)→ 產生完整回覆。

硬性要求:
- 地端模型(Local LLM),不依賴雲端 LLM API
- LangGraph 作為 Agent 編排框架
- LangSmith 作為 Observability / Tracing
- 自動環境檢測與安裝腳本
- SQL 僅允許 SELECT,嚴格防注入

## 2. 技術選型

| 項目 | 選擇 | 理由 |
|---|---|---|
| Agent 編排 | LangGraph `StateGraph` | 試題要求 |
| 本地 LLM 後端 | Ollama **或** LM Studio(env 切換) | 試題建議 Ollama;LM Studio 為使用者可用替代 |
| LLM 串接 | `langchain-ollama` / `langchain-openai`(LM Studio OpenAI 相容端點) | 官方整合 |
| 資料庫 | SQLite(唯讀查詢連線) | 輕量嵌入式 |
| 圖表 | Plotly | 互動 + Gradio 原生內嵌 |
| Web UI | Gradio | 加分項、Demo 直觀 |
| 追蹤 | LangSmith(env 開關) | 試題要求 |
| SQL 安全 | sqlparse + 白名單 | 防注入 |

### 2.1 模型命名的規格發現(重要)
試題寫「Gemma 4 E4B」與 `ollama pull gemma4:e4b`,但 Ollama 沒有 `gemma4` tag。依「E4B / 4B 有效參數 / 128k 上下文 / 函式呼叫」描述,實際對應 **Gemma 3n 的 `gemma3n:e4b`**(推測為出題筆誤)。
處理:預設用真實可 pull 的 `gemma3n:e4b`,並以環境變數 `LLM_MODEL` 可換。架構文件會記錄此發現。

### 2.2 不依賴 native function-calling
Gemma 經 Ollama 的原生 tool-calling 不穩定。意圖解析與 SQL 生成改用「強約束 prompt + 穩健 JSON 抽取」而非 native tool-calling,提升可靠度。

## 3. 專案結構

```
text2sql-agent/
├── setup.py                 # 跨平台環境檢測與安裝(Windows/macOS)
├── requirements.txt
├── README.md
├── .env.example
├── config.py                # 集中設定(env 讀取)
├── app.py                   # Gradio Web UI
├── data/
│   └── SuperMarket Analysis.csv   # 樣本(合成,標明非真實 Kaggle 資料)
├── src/
│   ├── db/{init_db.py, schema.py}
│   ├── llm/client.py        # 後端抽象 ollama / lmstudio,可注入 mock
│   ├── agent/
│   │   ├── state.py         # AgentState TypedDict
│   │   ├── graph.py         # StateGraph 組裝 + 條件邊
│   │   └── nodes/{intent_parser, text2sql, sql_validator,
│   │                sql_executor, response_router, response_composer}.py
│   ├── visualization/chart_generator.py
│   ├── cache.py             # query result 快取(加分項)
│   └── main.py              # CLI 入口
├── tests/                   # 單元測試(不需真模型)
└── docs/architecture.md     # 架構設計文件
```

## 4. LangGraph State 設計

`AgentState` (TypedDict, total=False):
- `user_input: str` — 本輪原始輸入
- `history: list[dict]` — 多輪對話(role/content),供上下文
- `intent: dict` — {query_type, entities, language, hints}
- `schema: str` — DB schema 字串(供 prompt)
- `sql: str` — 生成的 SQL
- `sql_error: str | None` — 驗證/執行錯誤
- `retry_count: int` — 重試次數
- `query_result: dict` — {columns, rows, row_count}
- `response_format: str` — speech / list / chart
- `chart_spec: dict | None` — {chart_type, x, y, title}
- `chart_path: str | None` — 產生的圖檔路徑
- `final_answer: str` — 給使用者的口語回覆
- `error_message: str | None` — 面向使用者的失敗訊息

## 5. 節點與流程

```
User Input
  → Intent Parser      分析查詢類型/實體/語言/語意暗示
  → Schema Fetcher     讀取 SQLite schema + 範例值
  → Text2SQL           LLM 生成 SELECT
  → SQL Validator      sqlparse + 白名單;失敗→(retry<3)回 Text2SQL,否則→無法理解
  → SQL Executor       唯讀執行 + LIMIT + timeout
  → Response Router     依意圖+結果形狀+語意 決定 speech/list/chart(+chart_type)
  → Response Composer   一律口語回覆,必要時附列表/圖表
```

重試迴圈以 LangGraph 條件邊實作,上限 3;超限走 `error_message`「無法理解您的問題,請換個方式提問」。

## 6. 回覆格式決策邏輯(核心考核)

Router 綜合三訊號,規則為主、LLM 輔助:

| 訊號 | speech | list | chart |
|---|---|---|---|
| 意圖類型 | 單值聚合 | 明細查詢 | 分組統計 / 趨勢 / 比較 |
| 結果形狀 | 1 列 1 欄 | 多列(≤20)多欄、無明顯可比較數值群 | 有分組維度 + 可比較數值欄 |
| 語意暗示 | 告訴我 / 多少 | 列出 / 哪些 | 比較 / 趨勢 / 分佈 / 佔比 |

圖表細分:
- 圓餅圖:單一分類維度的佔比(關鍵詞「佔比/分佈」或 ≤8 類且求比例)
- 長條圖:分組聚合比較
- 折線圖:含日期/時間維度的趨勢

一律先產生口語回覆(試題強制);口語需自然,不是把結果直接轉字串。

## 7. 安全性

- 僅允許**單一** `SELECT`;以 sqlparse 解析 token,擋 INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA 寫入/多語句(`;` 分號後有語句)/註解注入。
- 執行使用唯讀連線(`file:...?mode=ro` URI)+ 自動補 `LIMIT`(上限可設)+ 查詢逾時保護。
- 參數化不適用(SQL 由 LLM 生成),故以白名單 + 唯讀連線雙層防護。

## 8. LangSmith 整合

- 由 `config.py` 讀 `LANGSMITH_*` 環境變數;`LANGSMITH_TRACING=true` 且有 key 才啟用。
- LangGraph/LangChain 自動 trace 節點與 LLM 呼叫;重試因走同一 graph 亦會呈現。
- 未設 key 時安靜停用,不影響執行。

## 9. 可驗證性策略(使用者環境尚未安裝模型)

- LLM client 可注入 mock;單元測試不需真模型。
- 附合成樣本 CSV(17 欄,符合 schema,標明非真實 Kaggle 資料)→ DB 匯入、schema 讀取、SQL 驗證、執行、圖表、格式決策皆可離線實跑並過測試。
- README 指引如何換成真正 Kaggle CSV。

## 10. 加分項(納入)

多輪對話(history)、中英雙語、單元測試(SQL 解析 + 格式決策 + 驗證器)、Gradio Web UI、query result 快取、架構文件多模型比較(Gemma3n vs Llama3 vs Qwen)。

## 11. 驗收邊界

- 可離線驗證:非 LLM 程式碼實跑、單元測試、Gradio 啟動、setup 靜態檢查。
- 需使用者機器:真 Gemma 端到端推論、LangSmith 實際 trace(需 API key)。README 附驗收步驟。
