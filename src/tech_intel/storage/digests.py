"""LLM 月度摘要快取 — 避免重複呼叫 vLLM。"""
from __future__ import annotations

from typing import Any

from .db import get_pool


async def get(collection_key: str, month: str) -> dict[str, Any] | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT digest_text, model, source_count, generated_at
               FROM monthly_digests
               WHERE collection_key = $1 AND month = $2""",
            collection_key, month,
        )
    if row is None:
        return None
    return {
        "digest_text": row["digest_text"],
        "model": row["model"],
        "source_count": row["source_count"],
        "generated_at": row["generated_at"].isoformat(),
    }


async def set(collection_key: str, month: str, digest_text: str,
              model: str | None, source_count: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO monthly_digests
                 (collection_key, month, digest_text, model, source_count, generated_at)
               VALUES ($1, $2, $3, $4, $5, NOW())
               ON CONFLICT (collection_key, month) DO UPDATE SET
                 digest_text = EXCLUDED.digest_text,
                 model = EXCLUDED.model,
                 source_count = EXCLUDED.source_count,
                 generated_at = NOW()""",
            collection_key, month, digest_text, model, source_count,
        )
