"""Postgres 連線池 + schema — 所有 storage repository 共用。

連線設定走單一 `PG_DSN` 環境變數，例如 postgresql://user:pass@host:5432/db。
schema 採 IF NOT EXISTS，server / CLI 啟動時呼叫一次 init_schema() 即可。
"""
from __future__ import annotations

import asyncio
import logging
import os

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()
_initialized = False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_runs (
  date          DATE PRIMARY KEY,
  daily_summary TEXT NOT NULL DEFAULT '',
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
  uid             TEXT PRIMARY KEY,
  date            DATE NOT NULL REFERENCES daily_runs(date) ON DELETE CASCADE,
  position        INTEGER NOT NULL,
  source          TEXT NOT NULL,
  repo            TEXT,
  event_type      TEXT NOT NULL,
  classification  TEXT,
  title           TEXT NOT NULL,
  url             TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL,
  impact_level    TEXT,
  ai_summary      TEXT,
  body            TEXT,
  tags            TEXT[] NOT NULL DEFAULT '{}',
  migration_steps TEXT[] NOT NULL DEFAULT '{}',
  feed_name       TEXT,
  score           INTEGER,
  authors         TEXT[] NOT NULL DEFAULT '{}',
  categories      TEXT[] NOT NULL DEFAULT '{}',
  arxiv_id        TEXT
);
CREATE INDEX IF NOT EXISTS events_date_idx ON events(date);
CREATE INDEX IF NOT EXISTS events_source_idx ON events(source);

CREATE TABLE IF NOT EXISTS trending_runs (
  month         TEXT PRIMARY KEY,
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  lookback_days INTEGER NOT NULL,
  count         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trending_repos (
  month       TEXT NOT NULL REFERENCES trending_runs(month) ON DELETE CASCADE,
  rank        INTEGER NOT NULL,
  full_name   TEXT NOT NULL,
  url         TEXT NOT NULL,
  description TEXT,
  language    TEXT,
  stars       INTEGER NOT NULL,
  forks       INTEGER NOT NULL,
  created_at  DATE NOT NULL,
  topics      TEXT[] NOT NULL DEFAULT '{}',
  PRIMARY KEY (month, rank)
);

CREATE TABLE IF NOT EXISTS bookmarks (
  event_uid        TEXT PRIMARY KEY,
  source           TEXT NOT NULL,
  title            TEXT NOT NULL,
  url              TEXT NOT NULL,
  ai_summary       TEXT,
  body             TEXT,
  origin           TEXT,
  classification   TEXT,
  impact_level     TEXT,
  event_created_at TIMESTAMPTZ NOT NULL,
  bookmarked_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS bookmarks_source_idx ON bookmarks(source);

CREATE TABLE IF NOT EXISTS monthly_digests (
  collection_key TEXT NOT NULL,
  month          TEXT NOT NULL,
  digest_text    TEXT NOT NULL,
  model          TEXT,
  source_count   INTEGER NOT NULL,
  generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (collection_key, month)
);
"""


def _dsn() -> str:
    dsn = os.environ.get("PG_DSN")
    if not dsn:
        raise RuntimeError("缺少 PG_DSN 環境變數（例如 postgresql://user:pass@host:5432/db）")
    return dsn


async def get_pool() -> asyncpg.Pool:
    """全域 asyncpg pool — 第一次呼叫時建立並執行 init_schema。"""
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            _pool = await asyncpg.create_pool(_dsn(), min_size=1, max_size=10)
            logger.info("PG 連線池建立完成")
            await _init_schema_with(_pool)
    return _pool


async def close_pool() -> None:
    global _pool, _initialized
    if _pool is not None:
        await _pool.close()
        _pool = None
        _initialized = False


async def _init_schema_with(pool: asyncpg.Pool) -> None:
    global _initialized
    if _initialized:
        return
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA)
    _initialized = True
    logger.info("PG schema 初始化完成")


async def init_schema() -> None:
    pool = await get_pool()
    await _init_schema_with(pool)


def run_sync(coro):
    """同步腳本（CLI）跑單次 async 工作；不要在 server / event loop 中呼叫。"""
    return asyncio.run(coro)
