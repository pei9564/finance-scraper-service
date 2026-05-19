"""MediaCollector 行為測試 — 蒐集階段不打 STT,只產 link+title 的事件。"""
from __future__ import annotations

from unittest.mock import MagicMock

from finance_scraper.domain import MediaChannelConfig, MediaSourceConfig, SourceType
from finance_scraper.sources.media.collector import MediaCollector


def _fake_feed(entries: list[dict]):
    f = MagicMock()
    f.bozo = False
    f.entries = entries
    f.bozo_exception = None
    return f


def _entry(link: str, title: str = "標題", days_ago: int = 1) -> dict:
    from time import gmtime, time
    ts = gmtime(time() - days_ago * 86400)
    return {
        "link": link,
        "title": title,
        "published_parsed": ts,
        "enclosures": [],
    }


def test_youtube_collector_emits_event_with_empty_body(monkeypatch):
    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed([_entry("https://yt/v1", title="影片 A")]),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="Fireship", url="rss")])
    collector = MediaCollector(SourceType.YOUTUBE_TECH, cfg, seen_urls=set())

    events = collector.collect()

    assert len(events) == 1
    assert events[0].source_type == SourceType.YOUTUBE_TECH
    assert events[0].title == "影片 A"
    assert events[0].url == "https://yt/v1"
    assert events[0].body == ""  # STT 在 UI 上手動觸發,蒐集階段 body 一律空
    assert events[0].feed_name == "Fireship"


def test_collector_skips_seen_urls(monkeypatch):
    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed([_entry("https://yt/dup")]),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="X", url="rss")])
    collector = MediaCollector(SourceType.YOUTUBE_TECH, cfg,
                               seen_urls={"https://yt/dup"})

    assert collector.collect() == []


def test_podcast_collector_uses_enclosure_url(monkeypatch):
    entry = _entry("https://podcast/page/1", title="ep 1")
    entry["enclosures"] = [{"url": "https://podcast/audio/1.mp3"}]
    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed([entry]),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="Pod", url="rss")])
    collector = MediaCollector(SourceType.PODCAST_TECH, cfg, seen_urls=set())
    events = collector.collect()

    assert len(events) == 1
    assert events[0].url == "https://podcast/audio/1.mp3"
    assert events[0].body == ""


def test_collector_only_takes_per_channel_entries(monkeypatch):
    entries = [_entry(f"https://yt/v{i}") for i in range(5)]
    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed(entries),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="C", url="rss")])
    collector = MediaCollector(SourceType.YOUTUBE_TECH, cfg,
                               seen_urls=set(), per_channel=2)
    events = collector.collect()
    assert len(events) == 2
