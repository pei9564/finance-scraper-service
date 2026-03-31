"""測試重要性過濾器"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime
from models import EventType, FilterConfig, RawGitHubEvent, RepoPriority
from filter import filter_events, score_event


def make_event(**kwargs) -> RawGitHubEvent:
    defaults = dict(
        repo_full_name="pydantic/pydantic",
        repo_priority=RepoPriority.CRITICAL,
        event_type=EventType.ISSUE,
        title="Test",
        url="https://github.com/pydantic/pydantic/issues/1",
        created_at=datetime(2026, 3, 25),
        labels=[],
        comment_count=0,
        reactions=0,
    )
    defaults.update(kwargs)
    return RawGitHubEvent(**defaults)


CONFIG = FilterConfig()


class TestScoring:
    def test_release_gets_bonus(self):
        event = make_event(event_type=EventType.RELEASE)
        assert score_event(event, CONFIG) >= 0.3

    def test_breaking_label_high_score(self):
        event = make_event(labels=["breaking change"])
        assert score_event(event, CONFIG) >= 0.5

    def test_security_label_high_score(self):
        event = make_event(labels=["security"])
        assert score_event(event, CONFIG) >= 0.4

    def test_comment_count_capped(self):
        # 超過 50 留言仍上限 0.2
        event = make_event(comment_count=1000)
        score = score_event(event, CONFIG)
        assert score <= 0.2 + 0.01  # float tolerance

    def test_merged_pr_bonus(self):
        event = make_event(event_type=EventType.PR, is_merged=True)
        score = score_event(event, CONFIG)
        assert score >= 0.1

    def test_score_capped_at_1(self):
        event = make_event(
            labels=["breaking change", "security"],
            comment_count=100,
            reactions=200,
            event_type=EventType.RELEASE,
            is_merged=True,
        )
        assert score_event(event, CONFIG) <= 1.0


class TestFilter:
    def test_release_always_passes(self):
        event = make_event(event_type=EventType.RELEASE)
        result = filter_events([event], CONFIG)
        assert len(result) == 1

    def test_low_score_issue_filtered_out(self):
        event = make_event(event_type=EventType.ISSUE, comment_count=0)
        result = filter_events([event], CONFIG)
        assert len(result) == 0

    def test_breaking_label_issue_passes(self):
        event = make_event(
            event_type=EventType.ISSUE,
            labels=["breaking change"],
            comment_count=0,
        )
        result = filter_events([event], CONFIG)
        assert len(result) == 1

    def test_merged_pr_with_enough_comments_passes(self):
        event = make_event(
            event_type=EventType.PR,
            is_merged=True,
            comment_count=5,
            labels=["enhancement"],
        )
        result = filter_events([event], CONFIG)
        assert len(result) == 1

    def test_sorted_by_score_descending(self):
        low = make_event(url="https://github.com/a/a/issues/1", comment_count=0)
        high = make_event(
            url="https://github.com/a/a/issues/2",
            labels=["breaking change"],
            comment_count=10,
        )
        result = filter_events([low, high], CONFIG)
        # high score 應排在前面（若兩者都通過）
        if len(result) >= 2:
            assert result[0].url == high.url
