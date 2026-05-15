"""測試規則式分類器"""
from datetime import datetime

import pytest

from tech_intel.domain import EventType, RawGitHubEvent
from tech_intel.processing.classifier import classify


def make_event(**kwargs) -> RawGitHubEvent:
    defaults = dict(
        repo_full_name="test/repo",
        event_type=EventType.ISSUE,
        title="Test",
        url="https://github.com/test/repo/issues/1",
        created_at=datetime(2026, 3, 25),
        labels=[],
        comment_count=0,
        reactions=0,
    )
    defaults.update(kwargs)
    return RawGitHubEvent(**defaults)


@pytest.mark.parametrize("event_kwargs,expected", [
    # Release
    ({"event_type": EventType.RELEASE, "title": "v2.0.0", "body": "Minor improvements"}, "Release"),
    # Release/Breaking
    ({"event_type": EventType.RELEASE, "title": "v3.0.0", "body": "Breaking change: removed X"}, "Release/Breaking"),
    # Breaking label
    ({"event_type": EventType.ISSUE, "labels": ["breaking change"]}, "Breaking"),
    ({"event_type": EventType.ISSUE, "labels": ["breaking-change"]}, "Breaking"),
    # Security
    ({"event_type": EventType.ISSUE, "labels": ["security"]}, "Security"),
    ({"event_type": EventType.ISSUE, "labels": ["vulnerability"]}, "Security"),
    # Performance
    ({"event_type": EventType.PR, "title": "Improve latency by 30%", "is_merged": True}, "Performance"),
    ({"event_type": EventType.PR, "title": "perf: optimize batch processing", "is_merged": True}, "Performance"),
    # Bug
    ({"event_type": EventType.ISSUE, "labels": ["bug"]}, "Bug"),
    ({"event_type": EventType.PR, "labels": ["fix"], "is_merged": True}, "Bug"),
    # Feature
    ({"event_type": EventType.ISSUE, "labels": ["enhancement"]}, "Feature"),
    ({"event_type": EventType.PR, "labels": ["feature"], "is_merged": True}, "Feature"),
    # Merged PR without labels → Feature
    ({"event_type": EventType.PR, "is_merged": True}, "Feature"),
    # Other
    ({"event_type": EventType.ISSUE}, "Other"),
])
def test_classify(event_kwargs, expected):
    event = make_event(**event_kwargs)
    result = classify(event)
    assert result.classification == expected, (
        f"Expected '{expected}', got '{result.classification}' for {event_kwargs}"
    )


def test_classify_preserves_original_fields():
    event = make_event(title="Original title", labels=["bug"])
    result = classify(event)
    assert result.title == "Original title"
    assert result.labels == ["bug"]
    assert result.significance_score >= 0.0
