"""Pipeline 進度跨進程 IPC — pipeline 是 server 的 subprocess，
in-memory dict 兩邊看不到，所以用一個 JSON 檔當共享狀態。
寫入是 best-effort，失敗不影響 pipeline 主流程。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROGRESS_FILE = Path(
    os.environ.get("PIPELINE_PROGRESS_FILE", "/tmp/finance-scraper-progress.json")
)


def write(progress: dict[str, Any]) -> None:
    """覆寫整份進度 — pipeline 各階段呼叫前先 read() 拿回現有 dict 再覆寫。"""
    try:
        PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False))
    except Exception:
        pass


def read() -> dict[str, Any] | None:
    try:
        return json.loads(PROGRESS_FILE.read_text())
    except Exception:
        return None


def clear() -> None:
    try:
        PROGRESS_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def update(patch: dict[str, Any]) -> None:
    """Merge patch into existing progress(若無檔則建一個)。subprocess 內最常用。"""
    cur = read() or {}
    cur.update(patch)
    write(cur)
