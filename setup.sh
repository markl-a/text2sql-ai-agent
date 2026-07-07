#!/usr/bin/env bash
# macOS / Linux 便利包裝:實際邏輯在跨平台的 setup.py。
# 用法: ./setup.sh [--skip-deps] [--skip-model]
set -euo pipefail
cd "$(dirname "$0")"

# 選擇 python 直譯器
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "❌ 找不到 python,請先安裝 Python 3.10+。"
  exit 1
fi

exec "$PY" setup.py "$@"
