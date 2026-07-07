# Text2SQL AI Agent（地端模型 · LangGraph · LangSmith）

用自然語言查詢超市銷售數據。Agent 會自動把問題轉成 SQL、安全地執行查詢，
並依「意圖 + 結果特徵」**自主決定回覆格式**（口語 / 列表 / 圖表），最後給出完整回覆。

- **地端 LLM**：完全在本機推論（Ollama 或 LM Studio），不呼叫雲端 LLM API
- **LangGraph**：以 StateGraph 編排 7 個節點的工作流，含 SQL 驗證失敗自動重試
- **LangSmith**：可觀測性 / Tracing（可選開關）
- **安全**：SQL 僅允許唯讀 `SELECT`，雙層防注入
- **加分項**：多輪對話、中英雙語、Gradio Web UI、查詢快取、單元測試

---

## 目錄結構

```
text2sql-agent/
├── setup.py / setup.sh          # 環境檢測與安裝腳本（跨平台）
├── requirements.txt
├── config.py                    # 集中設定（讀 .env）
├── app.py                       # Gradio Web UI
├── .env.example
├── data/
│   └── SuperMarket Analysis.csv # 樣本資料（合成，見下方說明）
├── scripts/generate_sample_csv.py
├── src/
│   ├── db/{init_db.py, schema.py}
│   ├── llm/{client.py, parsing.py}
│   ├── agent/
│   │   ├── state.py             # AgentState
│   │   ├── graph.py             # LangGraph 工作流
│   │   ├── agent.py             # 高階封裝（多輪對話）
│   │   ├── sql_safety.py        # SQL 安全驗證
│   │   ├── format_rules.py      # 回覆格式決策規則
│   │   └── nodes/               # 7 個節點
│   ├── visualization/chart_generator.py
│   ├── cache.py
│   └── main.py                  # CLI 入口
├── tests/                       # 單元 + 端到端測試（不需真模型）
└── docs/architecture.md         # 架構設計文件
```

---

## 先決條件

- Python 3.10+
- 以下**擇一** LLM 後端：
  - **Ollama**（建議，可被 setup 腳本自動安裝）
  - **LM Studio**（GUI，需手動安裝並啟動 Local Server）
- 硬體：Gemma 3n E4B（INT4 約 5 GB / INT8 約 7.5 GB 記憶體）

### ⚠️ 關於模型名稱（重要）

試題寫的是「Gemma 4 E4B」與 `ollama pull gemma4:e4b`，但 **Ollama 並沒有 `gemma4` 這個 tag**。
依試題描述（E4B / 4B 有效參數 / 128k 上下文 / 內建函式呼叫），實際對應的是
**Gemma 3n 的 `gemma3n:e4b`**（推測為出題筆誤）。本專案預設使用可實際 pull 的
`gemma3n:e4b`，並可用環境變數 `LLM_MODEL` 更換。詳見 `docs/architecture.md`。

---

## 快速開始

```bash
# 1) 複製環境設定
cp .env.example .env        # Windows: copy .env.example .env

# 2) 一鍵環境準備（偵測平台 → 裝 Ollama → 拉模型 → 驗證 → 裝套件 → 建 DB）
python setup.py             # macOS/Linux 亦可 ./setup.sh

# 3) 執行
python -m src.main          # 互動式 CLI
python app.py               # Gradio Web UI（瀏覽器開啟顯示的網址）
```

`setup.py` 具備冪等性：已完成的步驟（Ollama 已裝、模型已下載）會自動跳過。
可用 `--skip-model` / `--skip-deps` 分段執行。

### 手動安裝（若不使用 setup 腳本）

```bash
pip install -r requirements.txt
# Ollama 後端：
ollama pull gemma3n:e4b
python -m src.db.init_db     # CSV → SQLite
python -m src.main
```

---

## 切換 LLM 後端

於 `.env` 設定：

```ini
# Ollama（預設）
LLM_BACKEND=ollama
LLM_MODEL=gemma3n:e4b
OLLAMA_BASE_URL=http://localhost:11434

# 或 LM Studio（先在 LM Studio 載入模型並啟動 Local Server）
LLM_BACKEND=lmstudio
LLM_MODEL=gemma3n-e4b          # 依 LM Studio 內顯示的模型名
LMSTUDIO_BASE_URL=http://localhost:1234/v1
```

兩種後端皆為地端推論，`temperature=0` 讓 SQL 生成穩定。

---

## LangSmith（可觀測性）

1. 註冊免費帳號取得 API key：<https://smith.langchain.com/>
2. 於 `.env` 設定：

```ini
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-api-key>
LANGSMITH_PROJECT=text2sql-agent
```

啟用後可在 LangSmith 看到：每個 LangGraph 節點的輸入/輸出、LLM 的 prompt/response、
SQL 生成與執行、重試流程、整體 latency 與 token 使用量。
**未設 key 時會自動安靜停用，不影響 Agent 執行。**

---

## 範例問答場景

| 提問 | 預期回覆格式 |
|---|---|
| 這個超市總共有多少筆交易？ | 口語（單一數值） |
| 各分店的總銷售額是多少？ | 口語 + 圖表（長條圖） |
| 比較各產品線的銷售佔比 | 口語 + 圖表（圓餅圖） |
| 各月份的銷售趨勢 | 口語 + 圖表（折線圖） |
| 列出所有評分高於 9 分的會員交易 | 口語 + 列表 |
| 預測下個月的銷售額 | 口語（禮貌說明無法預測） |

支援多輪追問，例如先問「各分店的總銷售額」再問「那 Giza 呢？」。

---

## 資料集

`data/SuperMarket Analysis.csv` 內附的是**合成樣本**（1,000 筆，欄位/型別/值域對齊
試題規格，固定亂數種子可重現），讓專案在未下載真實資料時也能離線端到端運行與測試。

換成真實 Kaggle 資料：
1. 下載 <https://www.kaggle.com/datasets/faresashraf1001/supermarket-sales>
2. 覆蓋 `data/SuperMarket Analysis.csv`
3. 重新初始化：`python -m src.db.init_db`

匯入時會將欄名正規化為 snake_case（如 `Tax 5%` → `tax_5pct`）、日期轉 ISO
`YYYY-MM-DD`、時間轉 24 小時制，並以正確型別（REAL/INTEGER/TEXT）建表。

---

## 測試

```bash
pip install pytest
python -m pytest -q
```

涵蓋：SQL 安全驗證、回覆格式決策、LLM 輸出解析、DB 匯入/Schema，以及
**以 Mock LLM 跑完整 LangGraph 的端到端測試**（含重試與不支援分支）。
測試不需要真實模型即可全數通過。

---

## 驗收狀態（誠實揭露）

| 項目 | 狀態 |
|---|---|
| DB 匯入、Schema 讀取、型別轉換 | ✅ 已實跑驗證 |
| SQL 安全驗證、格式決策、解析器 | ✅ 單元測試通過（44 項） |
| 完整 LangGraph 工作流（Mock LLM） | ✅ 端到端測試通過 |
| 圖表生成（HTML 互動圖，bar/line/pie） | ✅ 已實跑驗證 |
| setup 腳本（平台偵測、建 DB） | ✅ 已實跑驗證 |
| **真實 Gemma 端到端推論** | ✅ 已用地端 `gemma3:12b`(Ollama)實跑五大場景 + 多輪對話,格式決策全判對 |
| LangSmith 實際 trace | ⏳ 需你的 API key（程式已整合，設 key 即生效） |

> 實測後端為本機 Ollama 的 `gemma3:12b`（因本機未安裝 `gemma3n:e4b`；兩者皆為地端
> Gemma 系列，用 `LLM_MODEL` 即可切換）。冷載入首問約 20s，其後每問約 10–15s。

> 圖表預設輸出為**互動式 HTML**（可靠、跨平台）。PNG 靜態匯出為選用，需
> `kaleido==0.2.1`（`kaleido` 1.x 與 `plotly` 5.x 不相容，且部分 Windows 環境會卡住）。

---

## 疑難排解

- **`ollama` 指令找不到**：確認已安裝並重開終端；Windows 安裝後 Ollama 於背景執行。
- **模型下載很慢/失敗**：`gemma3n:e4b` 約數 GB，確認網路；或改 `LLM_MODEL` 為較小模型測試。
- **LM Studio 連不上**：確認已於「Local Server」分頁按下 Start，且埠為 1234。
- **回覆偶爾格式不如預期**：小模型 SQL 生成有隨機性；本專案已用 `temperature=0`、
  重試修正、規則化格式決策降低不穩定。

架構設計、決策邏輯與技術取捨詳見 [`docs/architecture.md`](docs/architecture.md)。
