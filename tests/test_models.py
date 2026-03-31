"""測試 Pydantic 資料模型"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from datetime import datetime
from models import (
    AppConfig, ClassifiedEvent, EventType, ImpactLevel,
    RawGitHubEvent, RepoPriority, RepoConfig, SummarizedEvent,
)


def make_raw_event(**kwargs) -> RawGitHubEvent:
    defaults = dict(
        repo_full_name="pydantic/pydantic",
        repo_priority=RepoPriority.CRITICAL,
        event_type=EventType.ISSUE,
        title="Test issue",
        url="https://github.com/pydantic/pydantic/issues/1",
        created_at=datetime(2026, 3, 25),
    )
    defaults.update(kwargs)
    return RawGitHubEvent(**defaults)


def test_repo_config_full_name():
    repo = RepoConfig(owner="pydantic", name="pydantic", priority=RepoPriority.CRITICAL)
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
            {"owner": "pydantic", "name": "pydantic", "priority": "critical"},
        ],
        "filters": {"lookback_days": 7},
    }
    config = AppConfig(**raw)
    assert len(config.repos) == 1
    assert config.repos[0].priority == RepoPriority.CRITICAL
    assert config.filters.lookback_days == 7
