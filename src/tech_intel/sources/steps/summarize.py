"""SummarizeStep - 逐則 LLM 摘要步驟。

各來源的 head builder 把事件結構化欄位組成文字；摘要指令與長度由
AIConfig.summary_profiles（對應 repos.yaml）提供，調整不需改程式。
新增來源：寫一個 _build_<x>_head，加進 _HEAD_BUILDERS，再到 repos.yaml 加 profile。
"""
from __future__ import annotations

import logging
from typing import Callable

from tech_intel.domain import AIConfig, ClassifiedEvent, SourceType, SummarizedEvent
from tech_intel.interfaces import LLMGateway

logger = logging.getLogger(__name__)


def _build_news_head(event: ClassifiedEvent) -> str:
    body = (event.body or "")[:3000]
    return (
        f"新聞標題：{event.title}\n"
        f"來源：{event.feed_name}\n"
        f"內文：{body}"
    )


def _build_paper_head(event: ClassifiedEvent) -> str:
    body = (event.body or "")[:3000]
    return (
        f"論文標題：{event.title}\n"
        f"作者：{', '.join(event.authors[:5])}\n"
        f"類別：{', '.join(event.categories[:3])}\n"
        f"摘要原文：{body}"
    )


def _build_finance_head(event: ClassifiedEvent) -> str:
    body = (event.body or "")[:3000]
    return (
        f"財經新聞標題：{event.title}\n"
        f"來源：{event.feed_name}\n"
        f"內文：{body}"
    )


_HEAD_BUILDERS: dict[SourceType, Callable[[ClassifiedEvent], str]] = {
    SourceType.NEWS: _build_news_head,
    SourceType.PAPER: _build_paper_head,
    SourceType.FINANCE: _build_finance_head,
}


class SummarizeStep:
    name = "summarize"

    def __init__(self, llm: LLMGateway | None, config: AIConfig):
        self.llm = llm
        self.config = config

    def apply(self, event: ClassifiedEvent) -> ClassifiedEvent:
        """為事件產生繁中摘要並寫入 ai_summary。

        event 由 orchestrator 預先轉成 SummarizedEvent；若該來源沒有對應的
        head builder 或 summary profile，原樣回傳。
        LLM 不可用時直接跳過——卡片會顯示「摘要待重跑」，可後續用 retry 補。
        """
        if self.llm is None:
            return event

        head_builder = _HEAD_BUILDERS.get(event.source_type)
        profile = self.config.summary_profiles.get(event.source_type.value)
        if head_builder is None or profile is None:
            return event

        if not (event.body or "").strip():
            return event  # 無內文，等補爬後再摘要

        prompt = f"{profile.instruction.strip()}\n\n{head_builder(event)}"
        try:
            summary = self.llm.chat(prompt, profile.max_tokens)
        except Exception as e:
            logger.error(f"摘要失敗（{event.url}）：{e}")
            return event

        if isinstance(event, SummarizedEvent):
            return event.model_copy(update={"ai_summary": summary})
        return SummarizedEvent(**event.model_dump(), ai_summary=summary)
