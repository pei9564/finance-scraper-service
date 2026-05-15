"""Telegram 輸出
- TelegramSender：底層 Bot API 封裝（HTML parse mode）
- TelegramOutput：OutputWriter 介面的包裝
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from telegram import Bot
from telegram.error import TelegramError

from tech_intel.domain import ImpactLevel, SourceType, SummarizedEvent

logger = logging.getLogger(__name__)

# 優先發送的分類
PRIORITY_CLASSIFICATIONS = {"Breaking", "Security", "Release/Breaking"}

# Impact 對應 emoji
IMPACT_EMOJI = {
    ImpactLevel.BREAKING: "🔴",
    ImpactLevel.HIGH: "🟠",
    ImpactLevel.MEDIUM: "🟡",
    ImpactLevel.LOW: "🟢",
}

# Telegram 單則訊息上限
MAX_MSG_LEN = 4096


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def send_daily_report(self, events: list[SummarizedEvent], daily_summary: str) -> None:
        """發送每日日報：AI 摘要 + 分來源事件列表。"""
        if not events:
            await self._send_text("今日無新事件。")
            return

        CST = timezone(timedelta(hours=8))
        day_str = datetime.now(CST).strftime("%Y-%m-%d")

        # 1. AI 日報摘要
        header = f"📊 Tech Intel 日報 {day_str}\n\n"
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=self._truncate(header + daily_summary),
            disable_web_page_preview=True,
        )
        await asyncio.sleep(1)

        # 2. 若有 Breaking/Security 事件，附上連結清單
        priority_events = [
            e for e in events
            if e.classification in PRIORITY_CLASSIFICATIONS
            or e.impact_level == ImpactLevel.BREAKING
        ]
        if priority_events:
            lines = ["🔴 <b>需注意項目：</b>"]
            for e in priority_events:
                emoji = IMPACT_EMOJI.get(e.impact_level, "⚠️")
                lines.append(
                    f'{emoji} <a href="{escape(e.url)}">{escape(e.title[:60])}</a>'
                )
            await self._send_text("\n".join(lines))

        # 3. 分來源事件列表
        github_events = [e for e in events if e.source_type == SourceType.GITHUB]
        news_events = [e for e in events if e.source_type == SourceType.NEWS]
        paper_events = [e for e in events if e.source_type == SourceType.PAPER]

        if github_events:
            lines = [f"🔔 GitHub（{len(github_events)} 筆）"]
            for e in github_events[:10]:
                lines.append(
                    f'• <a href="{escape(e.url)}">{escape(e.title[:60])}</a>'
                    f" [{escape(e.classification)}]"
                )
            await self._send_text("\n".join(lines))
            await asyncio.sleep(1)

        if news_events:
            lines = [f"📰 網路新聞（{len(news_events)} 筆）"]
            for e in news_events[:10]:
                source = escape(e.feed_name)
                lines.append(
                    f'• [{source}] <a href="{escape(e.url)}">{escape(e.title[:60])}</a>'
                )
            await self._send_text("\n".join(lines))
            await asyncio.sleep(1)

        if paper_events:
            lines = [f"📄 最新論文（{len(paper_events)} 筆）"]
            for e in paper_events[:10]:
                cats = ", ".join(e.categories[:2])
                lines.append(
                    f'• [{escape(cats)}] <a href="{escape(e.url)}">{escape(e.title[:60])}</a>'
                )
            await self._send_text("\n".join(lines))

    async def send_text(self, text: str) -> None:
        """公開的單則訊息發送。"""
        await self._send_text(text)

    # ------------------------------------------------------------------
    # Format
    # ------------------------------------------------------------------

    def _format_alert(self, event: SummarizedEvent) -> str:
        emoji = IMPACT_EMOJI.get(event.impact_level, "⚠️")
        repo = escape(event.repo_full_name)
        title = escape(event.title[:80])
        summary = escape(event.ai_summary[:300])
        tags = " ".join(f"#{escape(t)}" for t in event.tags[:3])

        lines = [
            f"{emoji} <b>[{escape(event.classification)}] {repo}</b>",
            f"<b>{title}</b>",
            "",
            summary,
        ]
        if event.migration_steps:
            lines.append("")
            lines.append("⚡ <b>遷移步驟：</b>")
            for i, step in enumerate(event.migration_steps[:3], 1):
                lines.append(f"  {i}. {escape(step[:100])}")

        if tags:
            lines.append("")
            lines.append(tags)

        lines.append(f'\n🔗 <a href="{escape(event.url)}">查看詳情</a>')
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _truncate(self, text: str) -> str:
        if len(text) <= MAX_MSG_LEN:
            return text
        return text[:MAX_MSG_LEN - 20] + "\n\n[...訊息已截斷]"

    async def _send_text(self, text: str) -> None:
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=self._truncate(text),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except TelegramError as e:
            logger.error(f"Telegram 發送失敗：{e}")


class TelegramOutput:
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.sender = TelegramSender(bot_token, chat_id)

    async def write(
        self,
        events: list[SummarizedEvent],
        daily_summary: str,
        day_str: str,
    ) -> None:
        await self.sender.send_daily_report(events, daily_summary)
