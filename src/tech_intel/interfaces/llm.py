"""LLM gateway 介面。"""
from __future__ import annotations

from typing import Protocol


class LLMGateway(Protocol):
    """OpenAI 相容的對話介面 — 逐則摘要、日報摘要、未來翻譯步驟共用。"""

    def chat(
        self,
        user_prompt: str,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.3,
    ) -> str: ...
