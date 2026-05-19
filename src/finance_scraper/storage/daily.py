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
            # uid 是全域 PK,而上面只 DELETE 同日;同一篇跨日重複出現
            # (RSS 重發、YouTube lookback、arXiv 跨日重映)時會撞舊資料,
            # 故走 upsert 以最新 run 的內容為準。
            await conn.executemany(
                """INSERT INTO events (
                    uid, date, position, source, repo, event_type, classification,
                    title, url, created_at, impact_level, ai_summary, body,
                    tags, migration_steps, feed_name, score, authors, categories,
                    arxiv_id
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                          $14,$15,$16,$17,$18,$19,$20)
                   ON CONFLICT (uid) DO UPDATE SET
                     date            = EXCLUDED.date,
                     position        = EXCLUDED.position,
                     source          = EXCLUDED.source,
                     repo            = EXCLUDED.repo,
                     event_type      = EXCLUDED.event_type,
                     classification  = EXCLUDED.classification,
                     title           = EXCLUDED.title,
                     url             = EXCLUDED.url,
                     created_at      = EXCLUDED.created_at,
                     impact_level    = EXCLUDED.impact_level,
                     ai_summary      = EXCLUDED.ai_summary,
                     body            = EXCLUDED.body,
                     tags            = EXCLUDED.tags,
                     migration_steps = EXCLUDED.migration_steps,
                     feed_name       = EXCLUDED.feed_name,
                     score           = EXCLUDED.score,
                     authors         = EXCLUDED.authors,
                     categories      = EXCLUDED.categories,
                     arxiv_id        = EXCLUDED.arxiv_id""",
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


async def load_processed_events() -> dict[tuple[str, str], dict[str, Any]]:
    """回傳 {(source, url): {title, body, ai_summary}} — 只含 ai_summary 非空的事件。

    orchestrator 在 re-run 時用此 cache 跳過已摘要事件,免得每次都重打 LLM。
    跨日生效:同 (source, url) 在 events 表只會存最新一筆(uid 為 PK,upsert 覆蓋)。
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT source, url, title, body, ai_summary
               FROM events
               WHERE ai_summary IS NOT NULL AND ai_summary <> ''"""
        )
    return {
        (r["source"], r["url"]): {
            "title": r["title"],
            "body": r["body"],
            "ai_summary": r["ai_summary"],
        }
        for r in rows
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


"""sidebar / feed view 與 retry 都用「事件實際發佈日」(created_at,TW 時區)當分組鍵,
不再用 daily_runs 跑的 run date — 因為一次 run 可能撈入跨日的舊新聞/論文,
混在一起會誤導使用者。"""
_PUB_DATE_EXPR = "DATE(created_at AT TIME ZONE 'Asia/Taipei')"


async def list_feeds() -> list[dict[str, Any]]:
    """以 (source, feed_name) 為單位列出所有 feed,供日報 sidebar 使用。

    特殊處理:paper 的 feed_name 為空,整類聚合成一筆(feed_name=None)。
    舊版殘留的 source='github' 不列出。
    回傳每筆含 source / feed_name / count / missing / last_date(最近事件的發佈日)。
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT source,
                      CASE WHEN source = 'paper' THEN NULL
                           ELSE NULLIF(feed_name, '') END AS feed_name,
                      COUNT(*) AS n,
                      COUNT(*) FILTER (WHERE ai_summary IS NULL OR ai_summary = '') AS missing,
                      MAX({_PUB_DATE_EXPR}) AS last_date
               FROM events
               WHERE source != 'github'
               GROUP BY source,
                        CASE WHEN source = 'paper' THEN NULL
                             ELSE NULLIF(feed_name, '') END
               ORDER BY source, n DESC"""
        )
    return [
        {
            "source": r["source"],
            "feed_name": r["feed_name"],
            "count": r["n"],
            "missing": r["missing"],
            "last_date": r["last_date"].strftime("%Y-%m-%d") if r["last_date"] else None,
        }
        for r in rows
    ]


def _feed_where(source: str | None, feed_name: str | None) -> tuple[str, list[Any]]:
    """共用的 (source, feed_name) WHERE 子句 builder。"""
    clauses = ["source != 'github'"]
    params: list[Any] = []
    if source is not None:
        params.append(source)
        clauses.append(f"source = ${len(params)}")
        if source == "paper":
            pass  # paper 整類,不過濾 feed_name
        elif feed_name is None:
            clauses.append("(feed_name IS NULL OR feed_name = '')")
        else:
            params.append(feed_name)
            clauses.append(f"feed_name = ${len(params)}")
    return " AND ".join(clauses), params


async def load_feed_events(
    source: str | None,
    feed_name: str | None,
    limit_dates: int = 30,
) -> list[dict[str, Any]]:
    """依 (source, feed_name) 撈事件,按「實際發佈日」(created_at, TW)分組。

    - source=None 表「全部」(仍排除 github)
    - feed_name=None 對 paper 表示整類;對其他 source 表示「無 feed」
    - 結果按發佈日由新到舊,最多 limit_dates 天
    """
    where_clause, params = _feed_where(source, feed_name)
    params.append(limit_dates)
    limit_param = f"${len(params)}"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""WITH recent_dates AS (
                  SELECT DISTINCT {_PUB_DATE_EXPR} AS pub_date FROM events
                  WHERE {where_clause}
                  ORDER BY pub_date DESC LIMIT {limit_param}
                )
                SELECT uid, source, repo, event_type, classification, title, url,
                       created_at, impact_level, ai_summary, body, tags, migration_steps,
                       feed_name, score, authors, categories, arxiv_id,
                       {_PUB_DATE_EXPR} AS pub_date
                FROM events
                WHERE {where_clause}
                  AND {_PUB_DATE_EXPR} IN (SELECT pub_date FROM recent_dates)
                ORDER BY pub_date DESC, created_at DESC""",
            *params,
        )
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = r["pub_date"].strftime("%Y-%m-%d")
        g = groups.setdefault(d, {"date": d, "events": [], "missing": 0})
        ev = _row_to_event_dict(r)
        g["events"].append(ev)
        if not (ev["ai_summary"] or "").strip():
            g["missing"] += 1
    return list(groups.values())


async def list_events_by_pub_date(
    pub_date: str, source: str, feed_name: str | None = None,
) -> list[dict[str, Any]]:
    """讀取指定發佈日(TW)+ source(+ feed_name)的所有事件 — retry 用。"""
    where_clause, params = _feed_where(source, feed_name)
    params.append(_parse_date(pub_date))
    date_param = f"${len(params)}"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT uid, source, repo, event_type, classification, title, url,
                       created_at, impact_level, ai_summary, body, tags, migration_steps,
                       feed_name, score, authors, categories, arxiv_id
                FROM events
                WHERE {where_clause}
                  AND {_PUB_DATE_EXPR} = {date_param}
                ORDER BY created_at DESC""",
            *params,
        )
    return [_row_to_event_dict(r) for r in rows]


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
