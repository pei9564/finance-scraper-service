"""日報摘要器 - 對所有事件產生一則跨來源的每日摘要（單次 gateway 呼叫）。"""
from __future__ import annotations

import logging

from tech_intel.domain import ClassifiedEvent, SourceType
from tech_intel.interfaces import LLMGateway

logger = logging.getLogger(__name__)


class DailySummarizer:
    def __init__(self, llm: LLMGateway | None):
        self.llm = llm

    def summarize(self, events: list[ClassifiedEvent]) -> str:
        """產生一則日報摘要；失敗或無 LLM 時回退為純文字清單。"""
        if not events:
            return "今日無新事件。"
        if self.llm is None:
            return self._fallback(events)
        try:
            return self._call_daily_summary(events)
        except Exception as e:
            logger.error(f"日報摘要失敗：{e}")
            return self._fallback(events)

    # ------------------------------------------------------------------
    # 各來源的事件區塊組裝
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

    def _build_finance_block(self, e: ClassifiedEvent) -> str:
        lines = [f"[{e.feed_name}] {e.title}"]
        if e.body:
            lines.append(f"  {e.body[:300]}")
        return "\n".join(lines)

    def _call_daily_summary(self, events: list[ClassifiedEvent]) -> str:
        github_events = [e for e in events if e.source_type == SourceType.GITHUB]
        news_events = [e for e in events if e.source_type == SourceType.NEWS]
        paper_events = [e for e in events if e.source_type == SourceType.PAPER]
        finance_events = [e for e in events if e.source_type == SourceType.FINANCE]

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
        if finance_events:
            blocks = "\n\n".join(self._build_finance_block(e) for e in finance_events)
            sections.append(f"💰 財經新聞：\n{blocks}")

        all_blocks = "\n\n".join(sections)

        prompt = f"""根據以下多來源技術情報，直接輸出每日摘要。

規則：
- 全程使用繁體中文
- 不要有開場白、問候語、結語，直接從內容開始
- 若有 Breaking Change 或 Security 問題，放在最前面並加上 ⚠️
- 依來源分區塊：🔔 GitHub、📰 網路新聞、📄 最新論文、💰 財經新聞
- GitHub：依 repo 分組，每個 repo 用 2-4 條重點，Release 需提取具體變更
- 新聞：每則用 1-2 條重點，標註來源
- 論文：每篇用 1 條重點摘要，標註類別
- 財經：每則用 1-2 條重點，標註來源；台股、美股、總體經濟可分小組
- 每條重點控制在 40 字以內
- 純文字，不要任何 markdown 符號

{all_blocks}"""

        return self.llm.chat(prompt, max_tokens=4096)

    def _fallback(self, events: list[ClassifiedEvent]) -> str:
        lines = [f"📋 今日共 {len(events)} 筆事件："]
        for e in events:
            if e.source_type == SourceType.GITHUB:
                lines.append(f"• [{e.classification}] {e.repo_full_name}: {e.title}")
            elif e.source_type == SourceType.NEWS:
                lines.append(f"• [{e.feed_name}] {e.title}")
            elif e.source_type == SourceType.PAPER:
                lines.append(f"• [Paper] {e.title}")
            elif e.source_type == SourceType.FINANCE:
                lines.append(f"• [{e.feed_name}] {e.title}")
        return "\n".join(lines)
