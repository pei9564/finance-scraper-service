"""TranslateStep - 翻譯步驟骨架。

設計上可放在 summarize 之前組成「先翻譯再摘要」的步驟鏈。目前是安全的
no-op：已註冊進 STEP_FACTORIES，但 repos.yaml 不接到任何來源。
未來要啟用時，於 apply 中呼叫 self.llm.chat 並把譯文寫回 event.body。
"""
from __future__ import annotations

import logging

from finance_scraper.domain import ClassifiedEvent
from finance_scraper.interfaces import LLMGateway

logger = logging.getLogger(__name__)


class TranslateStep:
    name = "translate"

    def __init__(self, llm: LLMGateway):
        self.llm = llm

    def apply(self, event: ClassifiedEvent) -> ClassifiedEvent:
        # TODO 實際翻譯 prompt 待定；啟用時呼叫 self.llm.chat 並更新 event.body
        return event
