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


def _media_event() -> SummarizedEvent:
    raw = RawNewsEvent(
        source_type=SourceType.YOUTUBE_FIN,
        event_type=EventType.VIDEO,
        title="某 YT 影片",
        url="https://yt/v1",
        created_at=datetime(2026, 5, 15),
        body="完整逐字稿內容...",
        feed_name="頻道X",
    )
    return SummarizedEvent(**raw.model_dump())


def test_summarize_step_media_fallback_when_llm_none():
    """LLM 不可用時 media 來源應 fallback 把 body 寫進 ai_summary。"""
    config = AIConfig(summary_profiles={})  # profile 不重要,llm None 直接走 fallback
    step = SummarizeStep(llm=None, config=config)

    result = step.apply(_media_event())

    assert result.ai_summary == "完整逐字稿內容..."


def test_summarize_step_media_fallback_when_llm_raises():
    """LLM 拋錯時 media 來源也應 fallback。"""
    class BoomGateway:
        def chat(self, *a, **k):
            raise RuntimeError("boom")
    config = AIConfig(summary_profiles={"youtube_fin": SummaryProfile(max_tokens=300, instruction="x")})
    step = SummarizeStep(BoomGateway(), config)

    result = step.apply(_media_event())

    assert result.ai_summary == "完整逐字稿內容..."


def test_summarize_step_news_does_not_fallback_when_llm_none():
    """非 media 來源即使 LLM 不可用也不該 fallback,維持空 ai_summary。"""
    step = SummarizeStep(llm=None, config=AIConfig(summary_profiles={}))

    result = step.apply(_news_event())

    assert result.ai_summary == ""


def _en_news_event(feed_name: str = "HackerNews") -> SummarizedEvent:
    raw = RawNewsEvent(
        title="OpenAI releases new model",
        url="https://example.com/a",
        created_at=datetime(2026, 5, 15),
        body="...",
        feed_name=feed_name,
    )
    return SummarizedEvent(**raw.model_dump())


def test_translate_step_uses_llm():
    gateway = StubGateway("OpenAI 發表新模型")
    step = TranslateStep(gateway, skip_feeds=set())

    result = step.apply(_en_news_event())

    assert result.title == "OpenAI 發表新模型"
    assert len(gateway.calls) == 1


def test_translate_step_skips_zh_feed():
    """中文來源(feed_name 在 skip_feeds 內)應原樣回傳、不呼叫 LLM。"""
    gateway = StubGateway()
    step = TranslateStep(gateway, skip_feeds={"經濟日報 焦點"})

    event = _en_news_event(feed_name="經濟日報 焦點")
    result = step.apply(event)

    assert result.title == event.title
    assert gateway.calls == []


def test_translate_step_falls_back_to_package(monkeypatch):
    """LLM 拋錯時改用 deep-translator;這裡 monkeypatch 避免真實網路。"""
    gateway = StubGateway()
    def boom(*a, **k):
        raise RuntimeError("gateway down")
    gateway.chat = boom  # type: ignore[assignment]

    from finance_scraper.sources.steps import translate as translate_mod
    monkeypatch.setattr(translate_mod, "_translate_via_package", lambda text: "套件譯文")

    step = TranslateStep(gateway, skip_feeds=set())
    result = step.apply(_en_news_event())

    assert result.title == "套件譯文"


def test_translate_step_preserves_title_when_all_fail(monkeypatch):
    """LLM 與套件皆失敗時,保留原 title、不擋 pipeline。"""
    from finance_scraper.sources.steps import translate as translate_mod
    monkeypatch.setattr(translate_mod, "_translate_via_package", lambda text: None)

    step = TranslateStep(llm=None, skip_feeds=set())
    event = _en_news_event()
    result = step.apply(event)

    assert result.title == event.title
    assert step.name == "translate"
