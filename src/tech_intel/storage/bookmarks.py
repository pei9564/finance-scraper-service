"""收藏 CRUD — asyncpg 介面，呼叫端不需知道 PG schema。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .db import get_pool


def compute_uid(source: str, url: str) -> str:
    """事件穩定識別 — sha1(source|url)。

    GitHub release URL、新聞 URL 在多次抓取下穩定；pipeline 寫每日事件與
    前端按星號收藏共用同一公式，得以互通。
    """
    return hashlib.sha1(f"{source}|{url}".encode("utf-8")).hexdigest()


def _origin_for(event: dict) -> str:
    src = event.get("source", "")
    if src == "github":
        return event.get("repo") or ""
    if src in ("news", "finance"):
        return event.get("feed_name") or ""
    if src == "paper":
        cats = event.get("categories") or []
        return ", ".join(cats[:2])
    return ""


def _to_dt(v) -> datetime:
    if isinstance(v, datetime):
        return v
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def add(event: dict) -> dict:
    """新增收藏；event 是 daily JSON 的 event 物件（含 uid 欄位較佳）。

    回傳 {"uid": str, "created": bool}。已存在則 created=False。
    """
    uid = event.get("uid") or compute_uid(event.get("source", ""), event.get("url", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """INSERT INTO bookmarks (
                event_uid, source, title, url, ai_summary, body, origin,
                classification, impact_level, event_created_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (event_uid) DO NOTHING""",
            uid,
            event.get("source", ""),
            event.get("title", ""),
            event.get("url", ""),
            event.get("ai_summary"),
            event.get("body"),
            _origin_for(event),
            event.get("classification"),
            event.get("impact_level"),
            _to_dt(event.get("created_at", "")),
        )
    return {"uid": uid, "created": result.endswith(" 1")}


async def remove(uid: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM bookmarks WHERE event_uid = $1", uid)
    return result.endswith(" 1")


async def list_uids() -> set[str]:
    """頁面載入時拉一份 — 前端用來決定每張卡的 ⭐ 是否實心。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT event_uid FROM bookmarks")
    return {r["event_uid"] for r in rows}


async def months() -> list[str]:
    """已有收藏的月份清單（依 bookmarked_at），新→舊。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT to_char(bookmarked_at, 'YYYY-MM') AS m "
            "FROM bookmarks ORDER BY m DESC"
        )
    return [r["m"] for r in rows]


async def list_by_month(yyyy_mm: str) -> list[dict[str, Any]]:
    """該月所有收藏，新→舊。回傳給 JSON 序列化用。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT event_uid, source, title, url, ai_summary, body, origin,
                      classification, impact_level, event_created_at, bookmarked_at
               FROM bookmarks
               WHERE to_char(bookmarked_at, 'YYYY-MM') = $1
               ORDER BY bookmarked_at DESC""",
            yyyy_mm,
        )
    return [
        {
            "event_uid": r["event_uid"],
            "source": r["source"],
            "title": r["title"],
            "url": r["url"],
            "ai_summary": r["ai_summary"],
            "body": r["body"],
            "origin": r["origin"],
            "classification": r["classification"],
            "impact_level": r["impact_level"],
            "event_created_at": r["event_created_at"].isoformat(),
            "bookmarked_at": r["bookmarked_at"].isoformat(),
        }
        for r in rows
    ]
