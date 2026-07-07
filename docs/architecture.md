# 架構設計文件（Architecture）

Text2SQL AI Agent — 基於地端模型、LangGraph、LangSmith。

---

## 1. 整體設計思路

核心目標是把「自然語言 → 洞察」拆成一條**可觀測、可重試、可測試**的工作流，
而不是一次性丟給 LLM 生一段 SQL 就結束。因此採用 LangGraph 的 StateGraph，把責任
切成單一職責的節點，節點間以明確的 State 溝通。這樣的分割帶來三個好處：

1. **可觀測**：每個節點的輸入/輸出在 LangSmith 上獨立呈現，debug 時能精準定位是
   「意圖判斷錯」還是「SQL 生成錯」還是「格式決策錯」。
2. **可重試**：SQL 驗證/執行失敗時，能帶著錯誤訊息回到生成節點重試，而非整條重跑。
3. **可測試**：把「決策邏輯」與「LLM 呼叫」解耦，純邏輯（安全驗證、格式決策、解析）
   可用單元測試覆蓋，整條 graph 可用 Mock LLM 端到端測試，不依賴真實模型。

---

## 2. 工作流與節點分割

```
START
  → Intent Parser      意圖理解（查詢類型 / 實體 / 語言 / 語意暗示 / 是否可支援）
  → [supported?] ──No──→ Unsupported Handler ─┐
  → Schema Fetcher     自動讀取 DB schema     │
  → Text2SQL           LLM 生成 SELECT        │
  → SQL Validator      安全 + 語法驗證         │
       ├ valid    → SQL Executor              │
       ├ retry    → Text2SQL（帶錯誤回饋，上限 3）
       └ exhausted→ Retry-Exhausted Handler ──┤
  → SQL Executor       唯讀執行 + LIMIT + 快取  │
       ├ ok       → Response Router           │
       ├ retry    → Text2SQL                  │
       └ exhausted→ Retry-Exhausted Handler ──┤
  → Response Router    決定 speech/list/chart  │
  → Response Composer  ←───────────────────────┘  口語 + 列表/圖表
  → END
```

**為什麼這樣切？**

| 節點 | 單一職責 | 為何獨立 |
|---|---|---|
| Intent Parser | 理解「使用者想要什麼」 | 意圖是後續 SQL 與格式決策的共同輸入；也在此攔截「預測」等不支援查詢，避免浪費後續運算 |
| Schema Fetcher | 提供「資料庫長怎樣」 | 與 LLM 無關的純 DB 讀取，schema 動態注入 prompt，換資料集不需改 prompt |
| Text2SQL | 只做「NL→SQL」 | 保持 prompt 聚焦；重試時只重跑這一節點 |
| SQL Validator | 只做「安全 + 語法」 | 安全是硬需求，抽成純函式可完整測試；語法用 EXPLAIN 不動資料 |
| SQL Executor | 只做「安全執行 + 取數」 | 唯讀連線、列數上限、快取都封裝在此 |
| Response Router | 只做「選格式」 | 核心差異化能力，規則化後可預期、可測 |
| Response Composer | 只做「組回覆」 | 一律口語化，list/chart 疊加在後 |

不支援查詢與重試耗盡各由一個極小的 handler 節點設定友善訊息後匯流到 Composer，
讓「終點只有一個」（Composer → END），輸出路徑統一。

---

## 3. LangGraph State 設計

State 是一個 `TypedDict(total=False)`（見 `src/agent/state.py`），關鍵欄位：

| 欄位 | 寫入者 | 用途 |
|---|---|---|
| `user_input`, `history` | 入口 | 本輪問題與多輪上下文 |
| `intent` | Intent Parser | query_type / entities / language / hints / supported |
| `schema` | Schema Fetcher | 注入 Text2SQL prompt 的 schema 描述 |
| `sql`, `sql_error`, `retry_count` | Text2SQL / Validator / Executor | 生成的 SQL、錯誤、重試計數 |
| `query_result` | Executor | columns / rows / row_count |
| `response_format`, `chart_spec`, `chart_path` | Router / Composer | 格式決策與圖表 |
| `final_answer`, `error_message` | Composer / handlers | 最終回覆與失敗訊息 |
| `meta` | 多個 | cache_hit、figure 等診斷資訊 |

**設計取捨**：使用 `total=False` 讓每個節點只回傳自己更新的欄位，由 LangGraph 合併，
節點函式因此純粹（讀所需、寫所產），也更好測試。`retry_count` 放在 State 而非閉包，
是為了讓條件邊能依它做路由決策，且重試歷程在 trace 上可見。

依賴（LLM、設定、快取）不放進 State，而是透過 `Deps`（`src/agent/deps.py`）在建圖時
注入各節點閉包（`make_xxx_node(deps)`）——這讓測試能注入 Mock LLM 與獨立 cache。

---

## 4. 回覆格式決策邏輯（核心考核）

決策在 `src/agent/format_rules.decide_format()`，**以規則為主**（可預期、可測試），
綜合三個訊號：

1. **意圖類型**（`intent.query_type`）
2. **結果形狀**（列數、欄數、維度欄 vs 數值欄的組成）
3. **語意暗示**（`intent.hints` 關鍵詞）

| 判斷依據 | → 口語 (speech) | → 列表 (list) | → 圖表 (chart) |
|---|---|---|---|
| 意圖類型 | aggregate_single | detail | group_stat / trend / comparison |
| 結果形狀 | 1 列 1 欄 | 多列多欄、無明顯可比較數值群 | 有分組維度 + 可比較數值欄，2–30 組 |
| 語意暗示 | 告訴我 / 多少 | 列出 / 哪些 / 明細 | 比較 / 趨勢 / 佔比 / 分佈 |

**圖表類型再細分**：

- **折線圖 (line)**：結果含時間維度欄（date/month/year…）或意圖為 trend
- **圓餅圖 (pie)**：語意含「佔比 / 分佈 / proportion / share」且單一分類維度、類別數 ≤ 8
- **長條圖 (bar)**：其餘分組比較

**衝突處理**：當「列出」等明確明細意圖與圖表訊號同時出現時，優先尊重使用者明講的
「列出」→ list（見 `test_format_rules.test_list_hint_overrides_to_list...`）。

**為何規則為主、LLM 為輔**：格式決策若完全交給小模型，結果不穩定且難測。規則化能對
考題五大場景給出確定行為；未來若要處理更模糊的語意，可在 Router 節點接上 LLM 做
tie-break（節點介面已預留）。無論決策為何，Composer **一律先產生口語回覆**（試題硬性
要求），且口語由 LLM 依結果自然生成，而非把 SQL 結果硬轉字串。

---

## 5. 安全性設計

生成式 SQL 無法參數化，因此採**雙層防護**：

1. **靜態白名單驗證**（`src/agent/sql_safety.validate_sql`，純函式、完整單元測試）
   - 僅允許**單一**語句（多語句直接拒絕，擋 `SELECT ...; DROP ...` 注入）
   - 首個 token 必須是 `SELECT` 或 `WITH`
   - 以 sqlparse 逐 token 掃描，阻擋 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/
     ATTACH/PRAGMA/… 等關鍵字
   - 阻擋任何註解（`--`、`/* */`），避免以註解夾帶 payload
2. **執行期唯讀隔離**（`sql_executor` / `sql_validator`）
   - 連線以 `file:...?mode=ro` URI 開唯讀模式，並 `PRAGMA query_only=ON`
   - 未含 LIMIT 時自動補上 `MAX_RESULT_ROWS` 上限，避免結果過大
   - 語法先以 `EXPLAIN` 驗證，不實際觸資料

即使 LLM 被誘導生成破壞性語句，第一層攔截、第二層連線本身也無寫入權限。

---

## 6. 可觀測性（LangSmith）

`config.setup_langsmith()` 依環境變數啟用 tracing；LangGraph/LangChain 生態會自動把
每個節點與 LLM 呼叫上報。Tracing 的價值在本專案特別明顯：

- **重試可視化**：SQL 驗證失敗 → 重新生成的迴圈，在 trace 上是清楚的節點序列，能看到
  每次修正前後的 SQL 與錯誤訊息。
- **定位錯誤層級**：回覆不對時，能立刻分辨是意圖、SQL、還是格式決策出錯。
- **成本/延遲**：每次 LLM 呼叫的 token 與 latency 一目了然，利於 prompt 優化。

未設 key 時安靜停用，不影響地端執行（符合「LLM 推論完全在本機」的要求，LangSmith
僅為 tracing 例外）。

---

## 7. 地端模型與規格發現

### 7.1 模型命名的規格漏洞
試題指定「Gemma 4 E4B」、`ollama pull gemma4:e4b`，但 **Ollama 沒有 `gemma4` tag**。
從「E4B / 4B 有效參數 / 128k 上下文 / 內建函式呼叫」的描述判斷，這對應的是
**Gemma 3n**（其 `e2b`/`e4b` 變體正是「Effective 2B/4B」命名）。因此本專案預設
`gemma3n:e4b`，並讓 `LLM_MODEL` 可覆寫。這是一個刻意的工程決策：**遵循規格的意圖，
而非照抄一個不存在的 tag**。

### 7.2 不依賴 native function-calling
Gemma 經 Ollama 的原生 tool-calling 穩定度不足。意圖解析與 SQL 生成改用「強約束
prompt + 容錯解析」（`src/llm/parsing.py`：處理 ```json/```sql 圍欄、思考前綴、
括號配對掃描出 JSON），比依賴 native tool-calling 更可靠且後端無關（Ollama 與
LM Studio 通用）。

### 7.3 多模型比較

| 模型 | 有效參數 / 記憶體(約) | Text2SQL 適配度 | 備註 |
|---|---|---|---|
| **Gemma 3n E4B** | 4B / INT4 ~5GB | 中—良，指令遵循佳、上下文大(128k) | 本專案預設；體積小、可跑於一般筆電 |
| **Llama 3.1 8B** | 8B / INT4 ~5–6GB | 良,SQL 生成社群驗證多 | 記憶體/延遲略高;英文能力強 |
| **Qwen2.5-Coder 7B** | 7B / INT4 ~5GB | **佳**,程式/SQL 專長、結構化輸出穩 | 若追求 SQL 準確度的首選;中文亦佳 |

取捨：以「可跑在 Gemma 3n E4B 可負載硬體」為前提，若優先 SQL 準確度，
**Qwen2.5-Coder 7B** 通常是最佳替代（`LLM_MODEL=qwen2.5-coder:7b` 即可切換）；
若優先最小體積與長上下文，維持 Gemma 3n E4B。

---

## 8. 遇到的技術挑戰與解法

| 挑戰 | 解法 |
|---|---|
| 小模型輸出常夾雜思考文字/圍欄,難取結構化結果 | `parsing.py` 容錯抽取 JSON/SQL(括號配對掃描、圍欄剝除、前綴清理) |
| 生成式 SQL 無法參數化,注入風險高 | 白名單靜態驗證 + 唯讀連線雙層防護 |
| 小模型 SQL 偶爾語法錯 | Validator 用 EXPLAIN 驗證,錯誤回饋給 Text2SQL 帶錯重試(上限 3) |
| 格式決策若全交給 LLM 不穩定且難測 | 規則化 `decide_format` 純函式,LLM 僅負責口語化 |
| 使用者尚未安裝模型,仍需能驗證與測試 | LLM 可注入 Mock;附合成樣本 CSV;非 LLM 路徑全單元測試覆蓋 |
| PNG 匯出(kaleido)在 Windows 會卡住/版本不相容 | 預設改用 Plotly **互動式 HTML** 匯出(零外部行程);PNG 降為選用 |
| Windows 主控台 cp950 印 emoji 崩潰 | 入口統一 `enable_utf8_console()` 重設 stdout 為 UTF-8 |

---

## 9. 可延伸方向

- Router 接上 LLM 做格式 tie-break（介面已預留）
- 查詢結果快取改為含 TTL 或持久化
- 加入 few-shot 範例與 schema-linking 提升 Text2SQL 準確度
- 針對 Gemma 3n 的 Thinking Mode 做 prompt 優化
