"""測試 Pydantic 資料模型"""
from datetime import datetime

import pytest

from tech_intel.domain import (
    AppConfig, ClassifiedEvent, EventType, ImpactLevel,
    RawGitHubEvent, RepoConfig, SummarizedEvent,
)


def make_raw_event(**kwargs) -> RawGitHubEvent:
    defaults = dict(
        repo_full_name="pydantic/pydantic",
        event_type=EventType.ISSUE,
        title="Test issue",
        url="https://github.com/pydantic/pydantic/issues/1",
        created_at=datetime(2026, 3, 25),
    )
    defaults.update(kwargs)
    return RawGitHubEvent(**defaults)


def test_repo_config_full_name():
    repo = RepoConfig(owner="pydantic", name="pydantic")
    assert repo.full_name == "pydantic/pydantic"


def test_raw_event_defaults():
    event = make_raw_event()
    assert event.labels == []
    assert event.comment_count == 0
    assert event.is_merged is None


def test_classified_event_inherits():
    raw = make_raw_event()
    classified = ClassifiedEvent(**raw.model_dump(), classification="Bug", significance_score=0.3)
    assert classified.repo_full_name == raw.repo_full_name
    assert classified.classification == "Bug"


def test_summarized_event_inherits():
    raw = make_raw_event()
    classified = ClassifiedEvent(**raw.model_dump(), classification="Feature", significance_score=0.2)
    summarized = SummarizedEvent(
        **classified.model_dump(),
        ai_summary="Test summary",
        impact_level=ImpactLevel.MEDIUM,
        tags=["new-feature"],
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
    """缺 sources: / outputs: 區塊時，套用內建預設。"""
    config = AppConfig(repos=[{"owner": "a", "name": "b"}])
    assert config.sources["news"].steps == ["summarize"]
    assert config.sources["github"].enabled is True
    assert config.outputs["web"].enabled is True
    assert config.outputs["telegram"].enabled is False
