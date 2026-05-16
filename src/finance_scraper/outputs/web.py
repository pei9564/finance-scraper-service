"""WebOutput — 把每日事件寫入 PG。

寫入後順手清掉超過 KEEP_DAYS 的舊資料，避免無限增長。靜態網頁
由 server.py 直接從 PG 動態渲染，不再需要產生 manifest/index。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from finance_scraper.domain import SummarizedEvent
from finance_scraper.storage import daily
from finance_scraper.storage.bookmarks import compute_uid

logger = logging.getLogger(__name__)

KEEP_DAYS = 30


def _event_to_dict(e: SummarizedEvent) -> dict:
    source = e.source_type.value
    return {
        "uid": compute_uid(source, e.url),
        "source": source,
        "repo": None,  # github 來源已移除,events.repo 欄位保留供未來擴充
        "type": e.event_type.value,
        "classification": e.classification,
        "title": e.title,
        "url": e.url,
        "created_at": e.created_at.isoformat(),
        "impact_level": e.impact_level.value,
        "ai_summary": e.ai_summary,
        "body": e.body,
        "tags": e.tags,
        "migration_steps": e.migration_steps,
        "feed_name": e.feed_name,
        "score": e.score,
        "authors": e.authors,
        "categories": e.categories,
        "arxiv_id": e.arxiv_id,
    }


class WebOutput:
    name = "web"

    def __init__(self, *_args, **_kwargs):
        # 簽名相容 registry 仍會傳 output_dir，但實際走 PG，不用該參數
        pass

    async def write(
        self,
        events: list[SummarizedEvent],
        daily_summary: str,
        day_str: str,
    ) -> None:
        await daily.upsert_run(day_str, daily_summary, [_event_to_dict(e) for e in events])
        logger.info(f"日報寫入 PG：{day_str}（{len(events)} 筆事件）")

        cutoff = date.today() - timedelta(days=KEEP_DAYS)
        removed = await daily.prune_before(cutoff)
        if removed:
            logger.info(f"清除 {removed} 天超過 {KEEP_DAYS} 天的舊日報")
