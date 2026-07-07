"""環境準備腳本(必做)。

自動完成:
  1. 檢測系統平台 (Windows / macOS)
  2. 檢查 Ollama 是否已安裝 → 未安裝則嘗試自動安裝
  3. 檢查地端模型是否已下載 → 不存在則 ollama pull
  4. 驗證模型可正常推論
  5. 安裝 Python 相依套件
  6. 從 CSV 初始化 SQLite 資料庫

用法:
  python setup.py                 # 完整流程
  python setup.py --skip-deps     # 跳過 pip 安裝
  python setup.py --skip-model    # 跳過模型下載/驗證(僅裝套件+建 DB)

設計:清楚的進度提示與錯誤處理;LLM_BACKEND=lmstudio 時,因 LM Studio 為 GUI
應用,腳本改為偵測與指引(不自動安裝)。
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 讓 Windows 主控台可印中文/emoji
try:
    from config import enable_utf8_console
    enable_utf8_console()
except Exception:  # noqa: BLE001
    pass


# ── 輸出小工具 ────────────────────────────────────────────────
def info(msg): print(f"   {msg}")
def ok(msg): print(f"✅ {msg}")
def warn(msg): print(f"⚠️  {msg}")
def err(msg): print(f"❌ {msg}")
def step(n, msg): print(f"\n[{n}] {msg}")


def run(cmd: list[str], timeout: int | None = None, capture: bool = True) -> tuple[int, str]:
    """執行外部命令,回傳 (returncode, output)。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=capture, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out
    except FileNotFoundError:
        return 127, f"找不到命令: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"命令逾時: {' '.join(cmd)}"


# ── 各步驟 ────────────────────────────────────────────────────
def detect_platform() -> str:
    system = platform.system()  # 'Windows' / 'Darwin' / 'Linux'
    label = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(system, system)
    ok(f"偵測到系統平台: {label} ({platform.machine()})")
    if system not in ("Windows", "Darwin"):
        warn("本腳本主要支援 Windows / macOS;其他平台可能需手動安裝 Ollama。")
    return system


def ensure_ollama_installed(system: str) -> bool:
    if shutil.which("ollama"):
        ok("Ollama 已安裝,跳過。")
        return True

    warn("未偵測到 Ollama,嘗試自動安裝...")
    if system == "Windows":
        if shutil.which("winget"):
            info("使用 winget 安裝 Ollama...")
            code, out = run(["winget", "install", "--id", "Ollama.Ollama",
                             "-e", "--accept-source-agreements",
                             "--accept-package-agreements"], timeout=600, capture=False)
            if code == 0 and shutil.which("ollama"):
                ok("Ollama 安裝完成。")
                return True
        err("自動安裝失敗。請手動下載安裝: https://ollama.com/download")
        return False

    if system == "Darwin":
        if shutil.which("brew"):
            info("使用 Homebrew 安裝 Ollama...")
            code, _ = run(["brew", "install", "ollama"], timeout=600, capture=False)
            if code == 0 and shutil.which("ollama"):
                ok("Ollama 安裝完成。")
                return True
        info("嘗試官方安裝腳本...")
        code, _ = run(["/bin/sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                      timeout=600, capture=False)
        if code == 0 and shutil.which("ollama"):
            ok("Ollama 安裝完成。")
            return True
        err("自動安裝失敗。請手動安裝: https://ollama.com/download")
        return False

    err("此平台不支援自動安裝,請手動安裝 Ollama。")
    return False


def ensure_ollama_running() -> bool:
    code, out = run(["ollama", "list"], timeout=30)
    if code == 0:
        ok("Ollama 服務運作中。")
        return True
    warn("Ollama 服務似乎未啟動。請確認 Ollama 應用已開啟(Windows 會於背景執行),"
         "或於終端執行 `ollama serve` 後重試。")
    info(f"診斷輸出: {out.strip()[:200]}")
    return False


def ensure_model(model: str) -> bool:
    code, out = run(["ollama", "list"], timeout=30)
    if code == 0 and model.split(":")[0] in out:
        ok(f"模型已存在: {model}(跳過下載)。")
        return True

    info(f"未找到模型 {model},執行 ollama pull(可能需數分鐘)...")
    code, _ = run(["ollama", "pull", model], timeout=3600, capture=False)
    if code == 0:
        ok(f"模型下載完成: {model}")
        return True
    err(f"模型下載失敗: {model}。請確認名稱正確(見 README 關於 gemma3n:e4b 的說明)。")
    return False


def verify_inference(model: str) -> bool:
    info("驗證模型可正常推論...")
    code, out = run(["ollama", "run", model, "Reply with the single word: OK"], timeout=180)
    if code == 0 and out.strip():
        ok(f"模型推論正常。回應: {out.strip()[:60]}")
        return True
    err("模型推論驗證失敗。")
    info(f"診斷輸出: {out.strip()[:200]}")
    return False


def install_python_deps() -> bool:
    req = ROOT / "requirements.txt"
    if not req.exists():
        err("找不到 requirements.txt")
        return False
    info("安裝 Python 相依套件(pip install -r requirements.txt)...")
    code, _ = run([sys.executable, "-m", "pip", "install", "-r", str(req)],
                  timeout=1800, capture=False)
    if code == 0:
        ok("Python 套件安裝完成。")
        return True
    err("Python 套件安裝失敗。請檢查網路或 pip 設定。")
    return False


def init_database() -> bool:
    info("從 CSV 初始化 SQLite 資料庫...")
    try:
        from src.db.init_db import init_db
        summary = init_db()
        ok(f"資料庫就緒: {summary['rows']} 筆 → {summary['db_path']}")
        return True
    except Exception as e:  # noqa: BLE001
        err(f"資料庫初始化失敗: {e}")
        info("請確認 data/SuperMarket Analysis.csv 存在,"
             "或先執行 python scripts/generate_sample_csv.py 產生樣本。")
        return False


# ── 主流程 ────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Text2SQL Agent 環境準備腳本")
    parser.add_argument("--skip-deps", action="store_true", help="跳過 pip 安裝")
    parser.add_argument("--skip-model", action="store_true", help="跳過模型下載與驗證")
    args = parser.parse_args()

    from config import CONFIG
    print("=" * 50)
    print("   Text2SQL AI Agent — 環境準備")
    print("=" * 50)
    info(f"LLM 後端: {CONFIG.llm_backend} | 模型: {CONFIG.llm_model}")

    results: dict[str, bool] = {}

    step(1, "檢測系統平台")
    system = detect_platform()

    if not args.skip_model:
        if CONFIG.llm_backend == "lmstudio":
            step(2, "LM Studio 後端偵測")
            warn("目前設定為 LM Studio 後端。LM Studio 為 GUI 應用,無法自動安裝。")
            info("請手動:1) 下載 https://lmstudio.ai/  2) 載入 Gemma 模型  "
                 "3) 於 Local Server 分頁啟動伺服器(預設 http://localhost:1234)。")
            info("啟動伺服器後即可執行 python -m src.main。")
        else:
            step(2, "檢查 / 安裝 Ollama")
            results["ollama"] = ensure_ollama_installed(system)
            if results["ollama"]:
                ensure_ollama_running()
                step(3, "檢查 / 下載地端模型")
                results["model"] = ensure_model(CONFIG.llm_model)
                if results["model"]:
                    step(4, "驗證模型推論")
                    results["inference"] = verify_inference(CONFIG.llm_model)
    else:
        info("(--skip-model:略過 Ollama / 模型步驟)")

    if not args.skip_deps:
        step(5, "安裝 Python 相依套件")
        results["deps"] = install_python_deps()
    else:
        info("(--skip-deps:略過 pip 安裝)")

    step(6, "初始化資料庫")
    results["db"] = init_database()

    # 總結
    print("\n" + "=" * 50)
    if all(v for v in results.values()):
        ok("環境就緒!接著可執行:")
        info("  互動 CLI :  python -m src.main")
        info("  Web UI   :  python app.py")
    else:
        warn("部分步驟未完成,請檢視上方訊息:")
        for k, v in results.items():
            print(f"     {'✅' if v else '❌'} {k}")
        info("修正後可重跑本腳本,已完成的步驟會自動跳過。")
    print("=" * 50)


if __name__ == "__main__":
    main()
