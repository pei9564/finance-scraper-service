"""
AI 摘要器 - 透過 OpenAI 相容的內部 LLM gateway 產生摘要（支援多來源）
- 逐則摘要：news / paper 各產生一則繁中摘要
- 日報摘要：所有事件彙整成一則每日摘要
"""
from __future__ import annotations

import logging
import os

import httpx

from models import AIConfig, ClassifiedEvent, ImpactLevel, SourceType, SummarizedEvent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "你是一位資深軟體工程師，專門為技術團隊整理技術情報。"


class Summarizer:
    def __init__(self, config: AIConfig):
        self.config = config
        # env var 覆蓋 config（真實的內部 gateway 位址/金鑰放 .env，不進公開 repo）
        self.vllm_base_url = os.environ.get("VLLM_BASE_URL", config.vllm_base_url)
        self.vllm_model = os.environ.get("VLLM_MODEL", config.vllm_model)
        self.vllm_api_key = os.environ.get("VLLM_API_KEY", "EMPTY")
        self._vllm_model_cache: str | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def to_summarized(self, events: list[ClassifiedEvent]) -> list[SummarizedEvent]:
        """將 ClassifiedEvent 轉為 SummarizedEvent。
        news/paper 逐則用 LLM gateway 產生中文摘要；GitHub 事件 ai_summary 留空。"""
        result = []
        for e in events:
            summary = ""
            if self.config.vllm_enabled and e.source_type in (
                SourceType.NEWS,
                SourceType.PAPER,
            ):
                summary = self._summarize_event(e)
            result.append(
                SummarizedEvent(
                    **e.model_dump(),
                    ai_summary=summary,
                    impact_level=ImpactLevel.MEDIUM,
                    tags=[],
                    migration_steps=[],
                )
            )
        return result

    def summarize_daily(self, events: list[ClassifiedEvent]) -> str:
        """對所有事件產生一則日報摘要（單次 gateway 呼叫）。"""
        if not events:
            return "今日無新事件。"
        try:
            return self._call_daily_summary(events)
        except Exception as e:
            logger.error(f"日報摘要失敗：{e}")
            return self._fallback_daily(events)

    # ------------------------------------------------------------------
    # Gateway client
    # ------------------------------------------------------------------

    def _vllm_model_name(self) -> str:
        if self.vllm_model:
            return self.vllm_model
        if self._vllm_model_cache:
            return self._vllm_model_cache
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.vllm_base_url}/models",
                headers={"Authorization": f"Bearer {self.vllm_api_key}"},
            )
            resp.raise_for_status()
            self._vllm_model_cache = resp.json()["data"][0]["id"]
        logger.info(f"gateway 自動偵測 model：{self._vllm_model_cache}")
        return self._vllm_model_cache

    def _chat(self, user_prompt: str, max_tokens: int) -> str:
        payload = {
            "model": self._vllm_model_name(),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.vllm_base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.vllm_api_key}"},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    # ------------------------------------------------------------------
    # 逐則中文摘要
    # ------------------------------------------------------------------

    def _summarize_event(self, event: ClassifiedEvent) -> str:
        try:
            return self._chat(
                self._build_event_prompt(event), self.config.max_summary_tokens
            )
        except Exception as e:
            logger.error(f"摘要失敗（{event.url}）：{e}")
            return ""

    def _build_event_prompt(self, event: ClassifiedEvent) -> str:
        body = (event.body or "")[:3000]
        if event.source_type == SourceType.PAPER:
            kind = "論文"
            head = (
                f"論文標題：{event.title}\n"
                f"作者：{', '.join(event.authors[:5])}\n"
                f"類別：{', '.join(event.categories[:3])}\n"
                f"摘要原文：{body}"
            )
        else:
            kind = "新聞"
            head = (
                f"新聞標題：{event.title}\n"
                f"來源：{event.feed_name}\n"
                f"內文：{body}"
            )
        return (
            f"請用繁體中文，以 2-3 句話摘要以下{kind}的重點。"
            f"只輸出摘要本身，不要開場白、結語或 markdown 符號。\n\n{head}"
        )

    # ------------------------------------------------------------------
    # 日報摘要 - multi-source
    # ------------------------------------------------------------------

    def _build_github_block(self, e: ClassifiedEvent) -> str:
        lines = [f"[{e.classification}] {e.repo_full_name}: {e.title}"]
        if e.event_type.value == "Release":
            if e.tag:
                lines.append(f"  版本：{e.tag}")
            if e.body:
                lines.append(f"  Release Notes：{e.body[:1500]}")
        else:
            if e.labels:
                lines.append(f"  Labels：{', '.join(e.labels)}")
            if e.comment_count or e.reactions:
                lines.append(f"  留言：{e.comment_count}，Reactions：{e.reactions}")
            if e.body:
                lines.append(f"  說明：{e.body[:500]}")
        return "\n".join(lines)

    def _build_news_block(self, e: ClassifiedEvent) -> str:
        score_info = f"（score: {e.score}）" if e.score else ""
        author_info = f" by {e.author}" if e.author else ""
        lines = [f"[{e.feed_name}] {e.title}{score_info}{author_info}"]
        if e.body:
            lines.append(f"  {e.body[:300]}")
        return "\n".join(lines)

    def _build_paper_block(self, e: ClassifiedEvent) -> str:
        cats = ", ".join(e.categories[:3])
        authors = ", ".join(e.authors[:3])
        if len(e.authors) > 3:
            authors += " et al."
        lines = [f"[{cats}] {e.title} — {authors}"]
        if e.body:
            lines.append(f"  {e.body[:400]}")
        return "\n".join(lines)

    def _call_daily_summary(self, events: list[ClassifiedEvent]) -> str:
        github_events = [e for e in events if e.source_type == SourceType.GITHUB]
        news_events = [e for e in events if e.source_type == SourceType.NEWS]
        paper_events = [e for e in events if e.source_type == SourceType.PAPER]

        sections = []
        if github_events:
            blocks = "\n\n".join(self._build_github_block(e) for e in github_events)
            sections.append(f"🔔 GitHub 事件：\n{blocks}")
        if news_events:
            blocks = "\n\n".join(self._build_news_block(e) for e in news_events)
            sections.append(f"📰 網路新聞：\n{blocks}")
        if paper_events:
            blocks = "\n\n".join(self._build_paper_block(e) for e in paper_events)
            sections.append(f"📄 最新論文：\n{blocks}")

        all_blocks = "\n\n".join(sections)

        prompt = f"""根據以下多來源技術情報，直接輸出每日摘要。

規則：
- 全程使用繁體中文
- 不要有開場白、問候語、結語，直接從內容開始
- 若有 Breaking Change 或 Security 問題，放在最前面並加上 ⚠️
- 依來源分區塊：🔔 GitHub、📰 網路新聞、📄 最新論文
- GitHub：依 repo 分組，每個 repo 用 2-4 條重點，Release 需提取具體變更
- 新聞：每則用 1-2 條重點，標註來源
- 論文：每篇用 1 條重點摘要，標註類別
- 每條重點控制在 40 字以內
- 純文字，不要任何 markdown 符號

{all_blocks}"""

        return self._chat(prompt, max_tokens=4096)

    def _fallback_daily(self, events: list[ClassifiedEvent]) -> str:
        lines = [f"📋 今日共 {len(events)} 筆事件："]
        for e in events:
            if e.source_type == SourceType.GITHUB:
                lines.append(f"• [{e.classification}] {e.repo_full_name}: {e.title}")
            elif e.source_type == SourceType.NEWS:
                lines.append(f"• [{e.feed_name}] {e.title}")
            elif e.source_type == SourceType.PAPER:
                lines.append(f"• [Paper] {e.title}")
        return "\n".join(lines)
