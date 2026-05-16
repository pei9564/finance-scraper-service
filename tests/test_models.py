"""測試 Pydantic 資料模型"""
from datetime import datetime

import pytest

from finance_scraper.domain import (
    AppConfig, ClassifiedEvent, EventType, ImpactLevel,
    RawNewsEvent, RepoConfig, SummarizedEvent,
)


def make_raw_event(**kwargs) -> RawNewsEvent:
    defaults = dict(
        title="Test article",
        url="https://example.com/x",
        created_at=datetime(2026, 3, 25),
        feed_name="HackerNews",
    )
    defaults.update(kwargs)
    return RawNewsEvent(**defaults)


def test_repo_config_full_name():
    repo = RepoConfig(owner="pydantic", name="pydantic")
    assert repo.full_name == "pydantic/pydantic"


def test_raw_event_defaults():
    event = make_raw_event()
    assert event.feed_name == "HackerNews"
    assert event.score == 0
    assert event.event_type == EventType.ARTICLE


def test_classified_event_inherits():
    raw = make_raw_event()
    classified = ClassifiedEvent(**raw.model_dump(), classification="News", significance_score=0.3)
    assert classified.feed_name == raw.feed_name
    assert classified.classification == "News"


def test_summarized_event_inherits():
    raw = make_raw_event()
    classified = ClassifiedEvent(**raw.model_dump(), classification="News", significance_score=0.2)
    summarized = SummarizedEvent(
        **classified.model_dump(),
        ai_summary="Test summary",
        impact_level=ImpactLevel.MEDIUM,
        tags=["topic"],
    )
    assert summarized.ai_summary == "Test summary"
    assert summarized.impact_level == ImpactLevel.MEDIUM
    assert summarized.migration_steps == []


def test_impact_level_enum():
    assert ImpactLevel("Breaking") == ImpactLevel.BREAKING
    with pytest.raises(ValueError):
        ImpactLevel("Invalid")


def test_app_config_parsing():
    raw = {
        "repos": [
            {"owner": "pydantic", "name": "pydantic"},
        ],
        "filters": {"lookback_days": 7},
    }
    config = AppConfig(**raw)
    assert len(config.repos) == 1
    assert config.repos[0].full_name == "pydantic/pydantic"
    assert config.filters.lookback_days == 7


def test_app_config_default_sources_and_outputs():
    """缺 sources: / outputs: 區塊時,套用內建預設。"""
    config = AppConfig(repos=[{"owner": "a", "name": "b"}])
    assert config.sources["news"].steps == ["summarize"]
    assert config.sources["news"].enabled is True
    assert "github" not in config.sources
    assert config.outputs["web"].enabled is True
