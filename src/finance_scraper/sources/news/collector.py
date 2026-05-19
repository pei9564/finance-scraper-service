"""網路新聞收集器 - Hacker News Algolia API + RSS feeds"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from finance_scraper.domain import NewsConfig, RawNewsEvent, SourceType

logger = logging.getLogger(__name__)

HN_API = "https://hn.algolia.com/api/v1/search"


class NewsCollector:
    source_type = SourceType.NEWS

    def __init__(self, config: NewsConfig, lookback_days: int = 1):
        self.config = config
        self.lookback_days = lookback_days

    def collect(self) -> list[RawNewsEvent]:
        events: list[RawNewsEvent] = []

        if self.config.hackernews_enabled:
            try:
                hn_events = self._fetch_hackernews()
                events.extend(hn_events)
            except Exception as e:
                logger.error(f"Hacker News 收集失敗：{e}")

        for feed_cfg in self.config.rss_feeds:
            try:
                rss_events = self._fetch_rss(feed_cfg)
                events.extend(rss_events)
            except Exception as e:
                logger.error(f"RSS '{feed_cfg.name}' 收集失敗：{e}")

        logger.info(f"News 收集完成：{len(events)} 筆")
        return events

    # ------------------------------------------------------------------
    # Hacker News (Algolia API)
    # ------------------------------------------------------------------

    def _fetch_hackernews(self) -> list[RawNewsEvent]:
        since = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        params = {
            "tags": "story",
            "numericFilters": f"created_at_i>{int(since.timestamp())},points>{self.config.hackernews_min_score}",
            "hitsPerPage": self.config.hackernews_top_n,
            "restrictSearchableAttributes": "title",
        }

        with httpx.Client(timeout=30) as client:
            resp = client.get(HN_API, params=params)
            resp.raise_for_status()
            data = resp.json()

        events = []
        for hit in data.get("hits", []):
            title = hit.get("title", "").strip()
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
            score = int(hit.get("points", 0))
            created = datetime.fromisoformat(hit["created_at"].replace("Z", "+00:00"))

            if not title:
                continue

            events.append(RawNewsEvent(
                title=title,
                url=url,
                created_at=created,
                body=None,
                body_lang=None,  # body 空,等 fetch_body 補爬後再判斷;HN 都是英文網站
                feed_name="HackerNews",
                score=score,
                author=hit.get("author"),
            ))

        logger.info(f"Hacker News：{len(events)} 筆（score >= {self.config.hackernews_min_score}）")
        return events

    # ------------------------------------------------------------------
    # RSS / Atom feeds
    # ------------------------------------------------------------------

    def _fetch_rss(self, feed_cfg) -> list[RawNewsEvent]:
        since = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)

        feed = feedparser.parse(feed_cfg.url)
        if feed.bozo and not feed.entries:
            logger.warning(f"RSS 解析錯誤 ({feed_cfg.name})：{feed.bozo_exception}")
            return []

        events = []
        for entry in feed.entries:
            published = self._parse_entry_date(entry)
            if published and published < since:
                continue

            title = entry.get("title", "").strip()
            url = entry.get("link", "")
            if not title or not url:
                continue

            summary = entry.get("summary", "") or entry.get("description", "")
            if summary:
                summary = summary[:2000]

            events.append(RawNewsEvent(
                title=title,
                url=url,
                created_at=published or datetime.now(timezone.utc),
                body=summary,
                body_lang=feed_cfg.lang if summary else None,
                feed_name=feed_cfg.name,
                score=0,
                author=entry.get("author"),
            ))

        logger.info(f"RSS '{feed_cfg.name}'：{len(events)} 筆")
        return events

    def _parse_entry_date(self, entry) -> datetime | None:
        for attr in ("published_parsed", "updated_parsed"):
            struct = getattr(entry, attr, None)
            if struct:
                try:
                    from time import mktime
                    return datetime.fromtimestamp(mktime(struct), tz=timezone.utc)
                except Exception:
                    pass
        return None
