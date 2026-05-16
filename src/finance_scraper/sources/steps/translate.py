"""TranslateStep - 將非中文來源的 title 翻成繁中。

策略:
- 先看 event.feed_name 是否在 skip_feeds(來自 RSSFeedConfig.lang == "zh"),是就跳過
- 否則:LLM gateway 翻譯 → 失敗或不可用時 fallback deep-translator(Google)
- 兩者都失敗就保留原文,不擋 pipeline
- 翻譯結果直接覆寫 event.title;原文可從 url 找回,event_uid 由 url 雜湊,不受影響
"""
from __future__ import annotations

import logging
from typing import Iterable

from finance_scraper.domain import ClassifiedEvent
from finance_scraper.interfaces import LLMGateway

logger = logging.getLogger(__name__)

_TRANSLATE_PROMPT = (
    "請把以下英文標題翻成繁體中文,只輸出譯文本身,不要加引號、不要加解釋:\n\n"
)


def _translate_via_package(text: str) -> str | None:
    """LLM 不可用時的 fallback。失敗回 None。"""
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source="auto", target="zh-TW").translate(text)
        return result.strip() if result else None
    except Exception as e:
        logger.debug(f"deep-translator 失敗:{e}")
        return None


class TranslateStep:
    name = "translate"

    def __init__(self, llm: LLMGateway | None, skip_feeds: Iterable[str] = ()):
        self.llm = llm
        self.skip_feeds = set(skip_feeds)

    def apply(self, event: ClassifiedEvent) -> ClassifiedEvent:
        title = (event.title or "").strip()
        if not title:
            return event
        if event.feed_name in self.skip_feeds:
            return event

        translated: str | None = None

        if self.llm is not None:
            try:
                translated = self.llm.chat(_TRANSLATE_PROMPT + title, max_tokens=200).strip()
            except Exception as e:
                logger.warning(f"LLM 翻譯失敗,改用 fallback:{e}")

        if not translated:
            translated = _translate_via_package(title)

        if not translated or translated == title:
            return event

        return event.model_copy(update={"title": translated})
