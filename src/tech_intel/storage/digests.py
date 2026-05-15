"""LLM 月度摘要快取 — 避免重複呼叫 vLLM。"""
from __future__ import annotations

from typing import Any

from .db import get_conn, init_schema


def get(collection_key: str, month: str) -> dict[str, Any] | None:
    init_schema()
    conn = get_conn()
    try:
        cur = conn.execute(
            """SELECT digest_text, model, source_count, generated_at
               FROM monthly_digests
               WHERE collection_key = ? AND month = ?""",
            (collection_key, month),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set(collection_key: str, month: str, digest_text: str,
        model: str | None, source_count: int) -> None:
    init_schema()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO monthly_digests
                 (collection_key, month, digest_text, model, source_count, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(collection_key, month) DO UPDATE SET
                 digest_text = excluded.digest_text,
                 model = excluded.model,
                 source_count = excluded.source_count,
                 generated_at = excluded.generated_at""",
            (collection_key, month, digest_text, model, source_count),
        )
        conn.commit()
    finally:
        conn.close()
