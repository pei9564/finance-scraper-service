"""測試逐則處理步驟"""
from datetime import datetime

from finance_scraper.domain import (
    AIConfig, EventType, RawNewsEvent, SourceType, SummarizedEvent, SummaryProfile,
)
from finance_scraper.sources.steps import SummarizeStep, TranslateStep


class StubGateway:
    """記錄呼叫並回傳固定文字的假 LLM gateway。"""
    def __init__(self, reply: str = "假摘要"):
        self.reply = reply
        self.calls: list[tuple[str, int]] = []

    def chat(self, user_prompt, max_tokens, system_prompt=None, temperature=0.3):
        self.calls.append((user_prompt, max_tokens))
        return self.reply


def _news_event() -> SummarizedEvent:
    raw = RawNewsEvent(
        title="某 AI 新聞",
        url="https://example.com/a",
        created_at=datetime(2026, 5, 15),
        body="內文",
        feed_name="HackerNews",
    )
    return SummarizedEvent(**raw.model_dump())


def test_summarize_step_sets_ai_summary():
    gateway = StubGateway("這是摘要")
    config = AIConfig(summary_profiles={"news": SummaryProfile(max_tokens=300, instruction="摘要")})
    step = SummarizeStep(gateway, config)

    result = step.apply(_news_event())

    assert result.ai_summary == "這是摘要"
    assert len(gateway.calls) == 1
    assert gateway.calls[0][1] == 300


def test_summarize_step_passthrough_when_no_profile():
    """來源沒有對應的 summary profile 時，事件原樣回傳、不呼叫 gateway。"""
    gateway = StubGateway()
    config = AIConfig(summary_profiles={})  # 無 news profile
    step = SummarizeStep(gateway, config)

    event = _news_event()
    result = step.apply(event)

    assert result.ai_summary == ""
    assert gateway.calls == []


def test_translate_step_is_noop():
    gateway = StubGateway()
    step = TranslateStep(gateway)
    event = _news_event()

    result = step.apply(event)

    assert result is event
    assert gateway.calls == []
    assert step.name == "translate"
