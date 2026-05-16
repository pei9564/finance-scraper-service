"""GitHub release CRUD — 獨立於 daily events,以 published_at 為時間軸。

uid = sha1(url),pipeline 重跑時 UPSERT;前端讀取依 published_at 倒序、
可選 days 參數截尾。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .db import get_pool


def compute_uid(url: str) -> str:
    return hashlib.sha1(f"github_release|{url}".encode("utf-8")).hexdigest()


def _row_to_dict(r) -> dict[str, Any]:
    return {
        "uid": r["uid"],
        "repo": r["repo"],
        "tag": r["tag"],
        "name": r["name"],
        "url": r["url"],
        "body": r["body"],
        "ai_summary": r["ai_summary"],
        "is_prerelease": r["is_prerelease"],
        "published_at": r["published_at"].isoformat(),
        "collected_at": r["collected_at"].isoformat(),
    }


async def list_existing_uids() -> set[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT uid FROM github_releases")
    return {r["uid"] for r in rows}


async def upsert_many(items: Iterable[dict[str, Any]]) -> int:
    """UPSERT — collected_at 永遠刷新,其餘欄位以新值覆蓋。回傳寫入筆數。"""
    rows = [
        (
            it["uid"],
            it["repo"],
            it["tag"],
            it["name"],
            it["url"],
            it.get("body"),
            it.get("ai_summary"),
            bool(it.get("is_prerelease", False)),
            it["published_at"],
        )
        for it in items
    ]
    if not rows:
        return 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO github_releases (
                uid, repo, tag, name, url, body, ai_summary,
                is_prerelease, published_at, collected_at
               ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, NOW())
               ON CONFLICT (uid) DO UPDATE SET
                 repo = EXCLUDED.repo,
                 tag = EXCLUDED.tag,
                 name = EXCLUDED.name,
                 url = EXCLUDED.url,
                 body = EXCLUDED.body,
                 ai_summary = COALESCE(EXCLUDED.ai_summary, github_releases.ai_summary),
                 is_prerelease = EXCLUDED.is_prerelease,
                 published_at = EXCLUDED.published_at,
                 collected_at = NOW()""",
            rows,
        )
    return len(rows)


async def list_recent(days: int | None = 180) -> list[dict[str, Any]]:
    """回傳近 N 天的 release(依 published_at 倒序);days=None 回全部。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if days is None:
            rows = await conn.fetch(
                """SELECT uid, repo, tag, name, url, body, ai_summary,
                          is_prerelease, published_at, collected_at
                   FROM github_releases
                   ORDER BY published_at DESC"""
            )
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            rows = await conn.fetch(
                """SELECT uid, repo, tag, name, url, body, ai_summary,
                          is_prerelease, published_at, collected_at
                   FROM github_releases
                   WHERE published_at >= $1
                   ORDER BY published_at DESC""",
                cutoff,
            )
    return [_row_to_dict(r) for r in rows]
