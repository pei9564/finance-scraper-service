"""Media (YouTube / Podcast) 收集器 — 共用於 4 個 source_type。

對每個頻道:讀 RSS → 取最新 N 集 → seen_urls 內的跳過 → 其餘以 body="" 的
RawNewsEvent 入庫(等用戶在 UI 上 per-event 觸發 STT)。

設計:蒐集階段不打 STT(會慢且吃資源),改由 server 的 /api/transcribe-event
端點按需求觸發。seen_urls 仍保留:DB 內已有同 url 的事件就不再 append
(不論已轉錄或還是空 body — 避免同一影片在 events 表出現多筆)。

不需要新的 domain model — feed_name + body + url + title + score 全部跟
news 一致,只是 source_type 換成 YOUTUBE_* / PODCAST_*,body 預設為空。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

import feedparser

from finance_scraper.domain import EventType, MediaSourceConfig, RawNewsEvent, SourceType

logger = logging.getLogger(__name__)


def _is_youtube(source_type: SourceType) -> bool:
    return source_type in {SourceType.YOUTUBE_TECH, SourceType.YOUTUBE_FIN}


def _extract_url(entry, source_type: SourceType) -> str | None:
    """YT 用 entry.link(影片頁);podcast 用 enclosure.url(音檔直連)。"""
    if _is_youtube(source_type):
        return entry.get("link") or None
    for enc in entry.get("enclosures", []) or []:
        url = enc.get("url")
        if url:
            return url
    return entry.get("link") or None


def _entry_published(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        struct = entry.get(attr)
        if struct:
            from time import mktime
            return datetime.fromtimestamp(mktime(struct), tz=timezone.utc)
    return datetime.now(timezone.utc)


class MediaCollector:
    def __init__(
        self,
        source_type: SourceType,
        config: MediaSourceConfig,
        seen_urls: Iterable[str] = (),
        per_channel: int = 1,
        lookback_days: int = 7,
    ):
        self.source_type = source_type
        self.config = config
        self.seen_urls: set[str] = set(seen_urls)
        self.per_channel = per_channel
        self.since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        self.event_type = EventType.VIDEO if _is_youtube(source_type) else EventType.PODCAST

    def collect(self) -> list[RawNewsEvent]:
        if not self.config.channels:
            logger.info(f"{self.source_type.value}:沒有設定 channels,跳過")
            return []

        events: list[RawNewsEvent] = []
        for channel in self.config.channels:
            try:
                events.extend(self._collect_channel(channel))
            except Exception as e:
                logger.error(f"{self.source_type.value} 頻道 '{channel.name}' 失敗:{e}")
        logger.info(f"{self.source_type.value} 收集完成:{len(events)} 筆(body 空,STT 待手動觸發)")
        return events

    def _collect_channel(self, channel) -> list[RawNewsEvent]:
        feed = feedparser.parse(channel.url)
        if feed.bozo and not feed.entries:
            logger.warning(f"RSS 解析失敗 ({channel.name}):{feed.bozo_exception}")
            return []

        out: list[RawNewsEvent] = []
        for entry in feed.entries[: self.per_channel]:
            published = _entry_published(entry)
            if published < self.since:
                continue

            url = _extract_url(entry, self.source_type)
            if not url:
                continue
            if url in self.seen_urls:
                logger.info(f"  跳過 DB 內已有:{url}")
                continue

            title = (entry.get("title") or "").strip() or url
            logger.info(f"  新增 link+title:{channel.name} / {title}")

            out.append(RawNewsEvent(
                source_type=self.source_type,
                event_type=self.event_type,
                title=title,
                url=url,
                created_at=published,
                body="",            # STT 改由 UI 手動觸發,寫進 events.body
                body_lang=None,     # body 空,等 STT 完成 server 端依 channel.lang 填
                feed_name=channel.name,
                score=0,
            ))
            # 同次 run 內若同 url 出現多次(理論上不會)也只處理一次
            self.seen_urls.add(url)
        return out
