"""SQLite 連線與 schema — 收藏與月度摘要快取。

單一檔案 data/tech_intel.db，使用 stdlib sqlite3，不引入 ORM。
schema 採 IF NOT EXISTS 風格，server 啟動時呼叫 init_schema() 即可。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_DIR = PROJECT_ROOT / "data"
DB_PATH = DB_DIR / "tech_intel.db"

_lock = threading.Lock()
_initialized = False


def get_conn() -> sqlite3.Connection:
    """回傳每次呼叫獨立的 connection（短交易模式，搭配 WAL）。

    呼叫端負責 commit + close（或用 with 區塊）。
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookmarks (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  event_uid        TEXT    NOT NULL UNIQUE,
  source           TEXT    NOT NULL,
  title            TEXT    NOT NULL,
  url              TEXT    NOT NULL,
  ai_summary       TEXT,
  body             TEXT,
  origin           TEXT,
  classification   TEXT,
  impact_level     TEXT,
  event_created_at TEXT    NOT NULL,
  bookmarked_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  raw_json         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookmarks_month ON bookmarks(substr(bookmarked_at, 1, 7));
CREATE INDEX IF NOT EXISTS idx_bookmarks_source ON bookmarks(source);

CREATE TABLE IF NOT EXISTS monthly_digests (
  collection_key TEXT NOT NULL,
  month          TEXT NOT NULL,
  digest_text    TEXT NOT NULL,
  model          TEXT,
  source_count   INTEGER NOT NULL,
  generated_at   TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (collection_key, month)
);
"""


def init_schema() -> None:
    """建立資料表；多次呼叫無害，採 process-local once 旗標避免重複跑。"""
    global _initialized
    with _lock:
        if _initialized:
            return
        conn = get_conn()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True
