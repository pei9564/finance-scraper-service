"""測試 Pipeline orchestrator — 階段串接與輸出注入。"""
from datetime import datetime

import pytest

from tech_intel.domain import (
    ClassifiedEvent, EventType, FilterConfig, RawGitHubEvent, RawNewsEvent,
    SourceType, SummarizedEvent,
)
from tech_intel.pipeline import Pipeline
from tech_intel.processing import DailySummarizer
from tech_intel.sources import SourceUnit


class StubGateway:
    def __init__(self, reply: str = "每日摘要"):
        self.reply = reply

    def chat(self, user_prompt, max_tokens, system_prompt=None, temperature=0.3):
        return self.reply


class FakeCollector:
    def __init__(self, source_type: SourceType, events: list):
        self.source_type = source_type
        self._events = events
        self.collected = False

    def collect(self):
        self.collected = True
        return self._events


class FakeStep:
    name = "fake"

    def __init__(self):
        self.applied = 0

    def apply(self, event: ClassifiedEvent) -> ClassifiedEvent:
        self.applied += 1
        return event.model_copy(update={"ai_summary": "STEP DONE"})


class FakeOutput:
    def __init__(self, name: str):
        self.name = name
        self.calls: list[tuple] = []

    async def write(self, events, daily_summary, day_str):
        self.calls.append((list(events), daily_summary, day_str))


def _github_release() -> RawGitHubEvent:
    return RawGitHubEvent(
        repo_full_name="a/b",
        event_type=EventType.RELEASE,
        title="v1.0.0",
        url="https://github.com/a/b/releases/1",
        created_at=datetime(2026, 5, 15),
        body="notes",
    )


def _news() -> RawNewsEvent:
    return RawNewsEvent(
        title="新聞",
        url="https://example.com/n",
        created_at=datetime(2026, 5, 15),
        body="內文",
        feed_name="HackerNews",
    )


@pytest.mark.asyncio
async def test_pipeline_runs_all_stages():
    news_step = FakeStep()
    units = [
        SourceUnit(SourceType.GITHUB, FakeCollector(SourceType.GITHUB, [_github_release()]), []),
        SourceUnit(SourceType.NEWS, FakeCollector(SourceType.NEWS, [_news()]), [news_step]),
    ]
    output = FakeOutput("fake")
    pipeline = Pipeline(units, [output], FilterConfig(), DailySummarizer(StubGateway()))

    await pipeline.run("2026-05-15")

    # 輸出被呼叫一次
    assert len(output.calls) == 1
    events, daily_summary, day_str = output.calls[0]
    assert day_str == "2026-05-15"
    assert daily_summary == "每日摘要"

    # 所有事件都轉成 SummarizedEvent
    assert all(isinstance(e, SummarizedEvent) for e in events)
    assert len(events) == 2

    # news 的步驟有被套用，github（無步驟）也產出 SummarizedEvent
    assert news_step.applied == 1
    by_source = {e.source_type: e for e in events}
    assert by_source[SourceType.NEWS].ai_summary == "STEP DONE"
    assert by_source[SourceType.GITHUB].ai_summary == ""


@pytest.mark.asyncio
async def test_pipeline_skips_outputs_when_no_events():
    units = [SourceUnit(SourceType.NEWS, FakeCollector(SourceType.NEWS, []), [])]
    output = FakeOutput("fake")
    pipeline = Pipeline(units, [output], FilterConfig(), DailySummarizer(StubGateway()))

    await pipeline.run("2026-05-15")

    assert output.calls == []


@pytest.mark.asyncio
async def test_pipeline_isolates_collector_failure():
    class BoomCollector:
        source_type = SourceType.GITHUB

        def collect(self):
            raise RuntimeError("boom")

    units = [
        SourceUnit(SourceType.GITHUB, BoomCollector(), []),
        SourceUnit(SourceType.NEWS, FakeCollector(SourceType.NEWS, [_news()]), []),
    ]
    output = FakeOutput("fake")
    pipeline = Pipeline(units, [output], FilterConfig(), DailySummarizer(StubGateway()))

    await pipeline.run("2026-05-15")

    # github 收集失敗不影響 news，輸出仍以 news 事件執行
    assert len(output.calls) == 1
    assert len(output.calls[0][0]) == 1
