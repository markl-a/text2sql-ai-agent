"""pytest 設定:確保專案根目錄在 sys.path,讓 `import config` / `import src...` 可用。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
