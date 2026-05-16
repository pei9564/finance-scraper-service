"""測試重要性過濾器 — 目前所有事件全數通過,只依分數重排。"""
from datetime import datetime

from finance_scraper.domain import FilterConfig, RawNewsEvent
from finance_scraper.processing.filter import filter_events, score_event


def _news(score: int, url: str = "https://example.com/x") -> RawNewsEvent:
    return RawNewsEvent(
        title="T", url=url, created_at=datetime(2026, 5, 15),
        feed_name="HackerNews", score=score,
    )


def test_score_news_baseline():
    assert score_event(_news(10), FilterConfig()) == 0.3


def test_score_news_high_hn_score():
    assert score_event(_news(200), FilterConfig()) == 0.7


def test_filter_passes_all_and_sorts_by_score():
    low = _news(10, url="https://example.com/a")
    high = _news(200, url="https://example.com/b")
    result = filter_events([low, high], FilterConfig())
    assert len(result) == 2
    assert result[0].url == high.url
    assert result[1].url == low.url
