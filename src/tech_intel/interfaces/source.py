"""來源收集與逐則處理步驟的介面。"""
from __future__ import annotations

from typing import Protocol

from tech_intel.domain import ClassifiedEvent, RawEvent, SourceType


class SourceCollector(Protocol):
    """單一來源的事件收集器。"""

    source_type: SourceType

    def collect(self) -> list[RawEvent]: ...


class ProcessingStep(Protocol):
    """逐則處理步驟 — 可組合成鏈（如 translate → summarize）。

    apply 接收並回傳 ClassifiedEvent；回傳子類別（如 SummarizedEvent）亦可，
    鏈的下一步仍以 ClassifiedEvent 介面處理。
    """

    name: str

    def apply(self, event: ClassifiedEvent) -> ClassifiedEvent: ...
