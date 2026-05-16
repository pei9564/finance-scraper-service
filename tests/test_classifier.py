"""測試規則式分類器 — 來源 → label 對應。"""
from datetime import datetime

import pytest

from finance_scraper.domain import EventType, RawNewsEvent, RawPaperEvent, SourceType
from finance_scraper.processing.classifier import classify


def _news(**kw) -> RawNewsEvent:
    base = dict(
        title="T", url="https://example.com/x",
        created_at=datetime(2026, 5, 15), feed_name="HackerNews", score=10,
    )
    base.update(kw)
    return RawNewsEvent(**base)


def _paper(**kw) -> RawPaperEvent:
    base = dict(
        title="P", url="https://arxiv.org/abs/2401.0001",
        created_at=datetime(2026, 5, 15), arxiv_id="2401.0001",
    )
    base.update(kw)
    return RawPaperEvent(**base)


@pytest.mark.parametrize("event,label,source_type", [
    (_news(), "News", SourceType.NEWS),
    (_paper(), "Paper", SourceType.PAPER),
])
def test_classify_assigns_label_by_source(event, label, source_type):
    result = classify(event)
    assert result.classification == label
    assert result.source_type == source_type
    assert result.significance_score >= 0.0


def test_classify_preserves_event_fields():
    event = _news(title="Big news", body="content")
    result = classify(event)
    assert result.title == "Big news"
    assert result.body == "content"
    assert result.event_type == EventType.ARTICLE
