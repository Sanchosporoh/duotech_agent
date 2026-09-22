from __future__ import annotations

import json
import sys
from pathlib import Path
from src.pipeline import execute


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result, folder = execute(Path(__file__).resolve().parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Результат сохранён: {folder}")
