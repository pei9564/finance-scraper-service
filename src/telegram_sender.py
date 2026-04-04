"""
Telegram 通知發送器
- Breaking/Security 優先個別發送
- 每個 repo 一則摘要訊息
- 最後一則總結統計
使用 HTML parse mode（避免 Markdown 特殊字元問題）
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from html import escape

from telegram import Bot
from telegram.error import TelegramError

from models import ImpactLevel, SummarizedEvent

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
        """發送每日日報：AI 摘要 + 事件列表。"""
        if not events:
            await self._send_text("今日無新事件。")
            return

        day_str = datetime.utcnow().strftime("%Y-%m-%d")

        # 1. AI 日報摘要（純文字，不用 HTML parse mode）
        header = f"📊 GitHub Collector 日報 {day_str}\n\n"
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


# ---------------------------------------------------------------------------
# 獨立執行測試
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    async def _test():
        sender = TelegramSender(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )
        await sender.send_text("✅ GitHub Collector Bot 連線測試成功！")

    asyncio.run(_test())
