"""收藏 CRUD — 純函式介面，呼叫端不需知道 sqlite3。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .db import get_conn, init_schema


def compute_uid(source: str, url: str) -> str:
    """事件穩定識別 — sha1(source|url)。

    GitHub release URL、新聞 URL 在多次抓取下穩定；用同一公式
    讓 pipeline 寫 daily JSON 時與前端星號狀態互通。
    """
    return hashlib.sha1(f"{source}|{url}".encode("utf-8")).hexdigest()


def _origin_for(event: dict) -> str:
    """卡片上「來源欄位」的單一字串表示，方便 list 視圖快速看出出處。"""
    src = event.get("source", "")
    if src == "github":
        return event.get("repo") or ""
    if src in ("news", "finance"):
        return event.get("feed_name") or ""
    if src == "paper":
        cats = event.get("categories") or []
        return ", ".join(cats[:2])
    return ""


def add(event: dict) -> dict:
    """新增收藏；event 是 daily JSON 的 event 物件（含 uid 欄位較佳）。

    回傳 {"id": int, "uid": str}。已存在則直接回傳原 row 的 id。
    """
    init_schema()
    uid = event.get("uid") or compute_uid(event.get("source", ""), event.get("url", ""))
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id FROM bookmarks WHERE event_uid = ?", (uid,))
        existing = cur.fetchone()
        if existing:
            return {"id": existing["id"], "uid": uid}

        cur = conn.execute(
            """INSERT INTO bookmarks (
                event_uid, source, title, url, ai_summary, body, origin,
                classification, impact_level, event_created_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid,
                event.get("source", ""),
                event.get("title", ""),
                event.get("url", ""),
                event.get("ai_summary"),
                event.get("body"),
                _origin_for(event),
                event.get("classification"),
                event.get("impact_level"),
                event.get("created_at", ""),
                json.dumps(event, ensure_ascii=False),
            ),
        )
        conn.commit()
        return {"id": cur.lastrowid, "uid": uid}
    finally:
        conn.close()


def remove(uid: str) -> bool:
    init_schema()
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM bookmarks WHERE event_uid = ?", (uid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_uids() -> set[str]:
    """頁面載入時拉一份 — 前端用來決定每張卡的 ⭐ 是否實心。"""
    init_schema()
    conn = get_conn()
    try:
        cur = conn.execute("SELECT event_uid FROM bookmarks")
        return {row["event_uid"] for row in cur.fetchall()}
    finally:
        conn.close()


def months() -> list[str]:
    """已有收藏的月份清單（依 bookmarked_at），新→舊。"""
    init_schema()
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT DISTINCT substr(bookmarked_at, 1, 7) AS m FROM bookmarks ORDER BY m DESC"
        )
        return [row["m"] for row in cur.fetchall()]
    finally:
        conn.close()


def list_by_month(yyyy_mm: str) -> list[dict[str, Any]]:
    """該月所有收藏，新→舊。回傳直接 JSON 序列化用。"""
    init_schema()
    conn = get_conn()
    try:
        cur = conn.execute(
            """SELECT event_uid, source, title, url, ai_summary, body, origin,
                      classification, impact_level, event_created_at, bookmarked_at
               FROM bookmarks
               WHERE substr(bookmarked_at, 1, 7) = ?
               ORDER BY bookmarked_at DESC""",
            (yyyy_mm,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
