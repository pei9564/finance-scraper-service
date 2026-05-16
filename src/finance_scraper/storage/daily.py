"""每日日報 CRUD — daily_runs + events 兩張表的 async 介面。

Pipeline 寫入：upsert_run() 蓋掉同一天舊資料後，批次寫入 events。
前端讀取：load_run() 回傳 {date, daily_summary, events: [...]}，
events 是直接給前端 JSON 序列化用的 dict 列表。
"""
from __future__ import annotations

import hashlib
from datetime import date as date_t, datetime
from typing import Any

from .db import get_pool


def _compute_uid(source: str, url: str) -> str:
    """事件穩定識別 — sha1(source|url)，與 bookmarks 共用同一公式。"""
    return hashlib.sha1(f"{source}|{url}".encode("utf-8")).hexdigest()


def _parse_date(s: str | date_t) -> date_t:
    if isinstance(s, date_t):
        return s
    return datetime.strptime(s, "%Y-%m-%d").date()


def _row_to_event_dict(r) -> dict[str, Any]:
    """events row → 前端 daily JSON 期待的欄位形狀。"""
    return {
        "uid": r["uid"],
        "source": r["source"],
        "repo": r["repo"],
        "type": r["event_type"],
        "classification": r["classification"],
        "title": r["title"],
        "url": r["url"],
        "created_at": r["created_at"].isoformat(),
        "impact_level": r["impact_level"],
        "ai_summary": r["ai_summary"],
        "body": r["body"],
        "tags": list(r["tags"] or []),
        "migration_steps": list(r["migration_steps"] or []),
        "feed_name": r["feed_name"],
        "score": r["score"],
        "authors": list(r["authors"] or []),
        "categories": list(r["categories"] or []),
        "arxiv_id": r["arxiv_id"],
    }


async def upsert_run(day_str: str, daily_summary: str, events: list[dict[str, Any]]) -> None:
    """寫入或覆蓋一天的日報；events 為 daily JSON 中的事件 dict 列表。

    為避免殘留舊事件，先 DELETE 同日 events 再批次 INSERT。
    """
    day = _parse_date(day_str)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO daily_runs (date, daily_summary, generated_at)
                   VALUES ($1, $2, NOW())
                   ON CONFLICT (date) DO UPDATE
                     SET daily_summary = EXCLUDED.daily_summary,
                         generated_at  = NOW()""",
                day, daily_summary,
            )
            await conn.execute("DELETE FROM events WHERE date = $1", day)
            if not events:
                return
            rows = []
            for i, e in enumerate(events):
                uid = e.get("uid") or _compute_uid(e.get("source", ""), e.get("url", ""))
                rows.append((
                    uid,
                    day,
                    i,
                    e.get("source", ""),
                    e.get("repo"),
                    e.get("type", ""),
                    e.get("classification"),
                    e.get("title", ""),
                    e.get("url", ""),
                    _to_dt(e["created_at"]),
                    e.get("impact_level"),
                    e.get("ai_summary"),
                    e.get("body"),
                    list(e.get("tags") or []),
                    list(e.get("migration_steps") or []),
                    e.get("feed_name"),
                    e.get("score"),
                    list(e.get("authors") or []),
                    list(e.get("categories") or []),
                    e.get("arxiv_id"),
                ))
            await conn.executemany(
                """INSERT INTO events (
                    uid, date, position, source, repo, event_type, classification,
                    title, url, created_at, impact_level, ai_summary, body,
                    tags, migration_steps, feed_name, score, authors, categories,
                    arxiv_id
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                          $14,$15,$16,$17,$18,$19,$20)""",
                rows,
            )


def _to_dt(v) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(v)


async def load_run(day_str: str) -> dict[str, Any] | None:
    """回傳 {date, daily_summary, events} — 形狀與舊 daily JSON 相容。"""
    day = _parse_date(day_str)
    pool = await get_pool()
    async with pool.acquire() as conn:
        head = await conn.fetchrow(
            "SELECT date, daily_summary FROM daily_runs WHERE date = $1", day,
        )
        if head is None:
            return None
        rows = await conn.fetch(
            """SELECT uid, source, repo, event_type, classification, title, url,
                      created_at, impact_level, ai_summary, body, tags, migration_steps,
                      feed_name, score, authors, categories, arxiv_id
               FROM events
               WHERE date = $1
               ORDER BY position""",
            day,
        )
    return {
        "date": head["date"].strftime("%Y-%m-%d"),
        "daily_summary": head["daily_summary"],
        "events": [_row_to_event_dict(r) for r in rows],
    }


async def list_urls_for_sources(sources: list[str]) -> set[str]:
    """回傳給定 source 在 events 表中已存在的所有 url(media collector 跨日去重用)。"""
    if not sources:
        return set()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT url FROM events WHERE source = ANY($1::text[])",
            sources,
        )
    return {r["url"] for r in rows}


async def list_dates() -> list[str]:
    """所有日報日期，新→舊。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT date FROM daily_runs ORDER BY date DESC")
    return [r["date"].strftime("%Y-%m-%d") for r in rows]


async def prune_before(cutoff: date_t) -> int:
    """刪除日期 < cutoff 的 daily_runs（events 透過 CASCADE 一併刪除）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM daily_runs WHERE date < $1", cutoff)
    # asyncpg execute 回傳例如 'DELETE 3'
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def update_event_summary(uid: str, ai_summary: str, body: str | None) -> bool:
    """retry 流程補摘要時用 — 只動 ai_summary（與必要時的 body）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if body is not None:
            result = await conn.execute(
                "UPDATE events SET ai_summary = $1, body = $2 WHERE uid = $3",
                ai_summary, body, uid,
            )
        else:
            result = await conn.execute(
                "UPDATE events SET ai_summary = $1 WHERE uid = $2",
                ai_summary, uid,
            )
    return result.endswith(" 1")
