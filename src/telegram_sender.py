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
from collections import defaultdict
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

    async def send_weekly_report(self, events: list[SummarizedEvent]) -> None:
        """發送完整週報：優先警報 → 各 repo 摘要 → 統計。"""
        if not events:
            await self._send_text("本週無新事件。")
            return

        # 1. 發送開始通知
        week_str = datetime.utcnow().strftime("%Y-W%U")
        await self._send_text(f"📊 <b>GitHub Intel 週報 {week_str}</b> 開始發送...")
        await asyncio.sleep(1)

        # 2. 優先發送 Breaking/Security 個別警報
        priority_events = [
            e for e in events
            if e.classification in PRIORITY_CLASSIFICATIONS
            or e.impact_level == ImpactLevel.BREAKING
        ]
        for event in priority_events:
            msg = self._format_alert(event)
            await self._send_text(msg)
            await asyncio.sleep(1)

        # 3. 各 repo 摘要
        by_repo: dict[str, list[SummarizedEvent]] = defaultdict(list)
        for e in events:
            by_repo[e.repo_full_name].append(e)

        for repo, repo_events in sorted(by_repo.items()):
            digest = self._format_repo_digest(repo, repo_events)
            await self._send_text(digest)
            await asyncio.sleep(1)

        # 4. 統計摘要
        summary = self._format_summary(events, week_str)
        await self._send_text(summary)

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

    def _format_repo_digest(self, repo: str, events: list[SummarizedEvent]) -> str:
        repo_esc = escape(repo)
        lines = [f"📦 <b>{repo_esc}</b>（{len(events)} 筆事件）", ""]

        for event in events[:10]:  # 最多顯示 10 筆
            emoji = IMPACT_EMOJI.get(event.impact_level, "▪️")
            title = escape(event.title[:60])
            summary = escape(event.ai_summary[:150])
            lines.append(f"{emoji} <b>[{escape(event.classification)}]</b> {title}")
            lines.append(f"   {summary}")
            lines.append(f'   <a href="{escape(event.url)}">連結</a>')
            lines.append("")

        return self._truncate(("\n".join(lines)).strip())

    def _format_summary(self, events: list[SummarizedEvent], week_str: str) -> str:
        total = len(events)
        breaking_count = sum(
            1 for e in events
            if e.classification in PRIORITY_CLASSIFICATIONS
            or e.impact_level == ImpactLevel.BREAKING
        )
        repos_affected = len({e.repo_full_name for e in events})

        lines = [
            f"✅ <b>週報完成｜{week_str}</b>",
            "",
            f"📌 追蹤到 <b>{total}</b> 筆事件",
            f"🔴 需注意 <b>{breaking_count}</b> 筆 Breaking/Security",
            f"📂 涵蓋 <b>{repos_affected}</b> 個 repo",
            "",
            "報告已同步至 Notion。",
        ]
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
        await sender.send_text("✅ GitHub Intel Bot 連線測試成功！")

    asyncio.run(_test())
