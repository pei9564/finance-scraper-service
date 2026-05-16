"""MediaCollector 行為測試 — feedparser + STTClient 都 mock 掉。"""
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


def test_youtube_collector_emits_event_for_new_url(monkeypatch):
    stt = MagicMock()
    stt.transcribe.return_value = "fake transcript text"

    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed([_entry("https://yt/v1")]),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="Fireship", url="rss")])
    collector = MediaCollector(SourceType.YOUTUBE_TECH, cfg, stt, seen_urls=set())

    events = collector.collect()

    assert len(events) == 1
    assert events[0].source_type == SourceType.YOUTUBE_TECH
    assert events[0].body == "fake transcript text"
    assert events[0].feed_name == "Fireship"
    stt.transcribe.assert_called_once()


def test_collector_skips_seen_urls_without_transcribing(monkeypatch):
    stt = MagicMock()
    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed([_entry("https://yt/dup")]),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="X", url="rss")])
    collector = MediaCollector(SourceType.YOUTUBE_TECH, cfg, stt,
                               seen_urls={"https://yt/dup"})

    assert collector.collect() == []
    stt.transcribe.assert_not_called()


def test_podcast_collector_uses_enclosure_url(monkeypatch):
    stt = MagicMock()
    stt.transcribe.return_value = "ep text"

    entry = _entry("https://podcast/page/1", title="ep 1")
    entry["enclosures"] = [{"url": "https://podcast/audio/1.mp3"}]
    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed([entry]),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="Pod", url="rss")])
    collector = MediaCollector(SourceType.PODCAST_TECH, cfg, stt, seen_urls=set())
    events = collector.collect()

    assert len(events) == 1
    assert events[0].url == "https://podcast/audio/1.mp3"
    stt.transcribe.assert_called_once_with("https://podcast/audio/1.mp3", topic="ep 1")


def test_collector_skips_when_stt_fails(monkeypatch):
    stt = MagicMock()
    stt.transcribe.return_value = None  # STT 失敗

    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed([_entry("https://yt/v2")]),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="Y", url="rss")])
    collector = MediaCollector(SourceType.YOUTUBE_TECH, cfg, stt, seen_urls=set())
    assert collector.collect() == []


def test_collector_only_takes_per_channel_entries(monkeypatch):
    stt = MagicMock()
    stt.transcribe.return_value = "t"

    entries = [_entry(f"https://yt/v{i}") for i in range(5)]
    monkeypatch.setattr(
        "finance_scraper.sources.media.collector.feedparser.parse",
        lambda url: _fake_feed(entries),
    )

    cfg = MediaSourceConfig(channels=[MediaChannelConfig(name="C", url="rss")])
    collector = MediaCollector(SourceType.YOUTUBE_TECH, cfg, stt,
                               seen_urls=set(), per_channel=2)
    events = collector.collect()
    assert len(events) == 2
