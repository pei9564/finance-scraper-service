"""月度 trending repos CRUD — trending_runs + trending_repos。"""
from __future__ import annotations

from datetime import date as date_t, datetime
from typing import Any

from .db import get_pool


def _row_to_repo_dict(r) -> dict[str, Any]:
    return {
        "rank": r["rank"],
        "full_name": r["full_name"],
        "url": r["url"],
        "description": r["description"] or "",
        "language": r["language"] or "",
        "stars": r["stars"],
        "forks": r["forks"],
        "created_at": r["created_at"].strftime("%Y-%m-%d"),
        "topics": list(r["topics"] or []),
    }


async def upsert_run(month: str, lookback_days: int, repos: list[dict[str, Any]]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO trending_runs (month, generated_at, lookback_days, count)
                   VALUES ($1, NOW(), $2, $3)
                   ON CONFLICT (month) DO UPDATE
                     SET generated_at = NOW(),
                         lookback_days = EXCLUDED.lookback_days,
                         count = EXCLUDED.count""",
                month, lookback_days, len(repos),
            )
            await conn.execute("DELETE FROM trending_repos WHERE month = $1", month)
            if not repos:
                return
            rows = [
                (
                    month,
                    r["rank"],
                    r["full_name"],
                    r["url"],
                    r.get("description") or None,
                    r.get("language") or None,
                    r["stars"],
                    r["forks"],
                    _to_date(r["created_at"]),
                    list(r.get("topics") or []),
                )
                for r in repos
            ]
            await conn.executemany(
                """INSERT INTO trending_repos
                     (month, rank, full_name, url, description, language,
                      stars, forks, created_at, topics)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                rows,
            )


def _to_date(v) -> date_t:
    if isinstance(v, date_t):
        return v
    return datetime.strptime(v, "%Y-%m-%d").date()


async def load_month(month: str) -> dict[str, Any] | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        head = await conn.fetchrow(
            "SELECT month, generated_at, lookback_days, count FROM trending_runs WHERE month = $1",
            month,
        )
        if head is None:
            return None
        rows = await conn.fetch(
            """SELECT rank, full_name, url, description, language,
                      stars, forks, created_at, topics
               FROM trending_repos
               WHERE month = $1
               ORDER BY rank""",
            month,
        )
    return {
        "month": head["month"],
        "generated_at": head["generated_at"].isoformat(),
        "lookback_days": head["lookback_days"],
        "count": head["count"],
        "repos": [_row_to_repo_dict(r) for r in rows],
    }


async def list_months() -> list[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT month FROM trending_runs ORDER BY month DESC")
    return [r["month"] for r in rows]
