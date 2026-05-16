"""輸出寫入器介面。"""
from __future__ import annotations

from typing import Protocol

from tech_intel.domain import SummarizedEvent


class OutputWriter(Protocol):
    """單一輸出目標（web ...）。

    統一 async 簽章 — 同步輸出（web）內部包同步工作後直接回傳。
    """

    name: str

    async def write(
        self,
        events: list[SummarizedEvent],
        daily_summary: str,
        day_str: str,
    ) -> None: ...
