"""Notion 輸出
- NotionWriter：底層資料庫寫入（去重、只寫重大更新）
- NotionOutput：OutputWriter 介面的包裝
"""
from __future__ import annotations

import logging
import time
from typing import Any

from notion_client import Client

from tech_intel.domain import NotionIds, SourceType, SummarizedEvent

logger = logging.getLogger(__name__)

NOTION_SLEEP = 0.4

SIGNIFICANT_CLASSIFICATIONS = {"Release", "Breaking", "Security", "Release/Breaking"}
SIGNIFICANT_IMPACTS = {"Breaking", "High"}


class NotionWriter:
    def __init__(self, token: str, db_ids: NotionIds):
        self.client = Client(auth=token)
        self.db_id = db_ids.activity_logs_db
        self._existing_urls: set[str] | None = None

    def write_events(self, events: list[SummarizedEvent]) -> None:
        self._load_existing_urls()

        significant = [
            e for e in events
            if e.classification in SIGNIFICANT_CLASSIFICATIONS
            or e.impact_level.value in SIGNIFICANT_IMPACTS
        ]

        inserted = 0
        skipped = 0
        for event in significant:
            if event.url in (self._existing_urls or set()):
                skipped += 1
                continue
            try:
                self._create_page(event)
                if self._existing_urls is not None:
                    self._existing_urls.add(event.url)
                inserted += 1
            except Exception as e:
                logger.error(f"Notion 寫入失敗（{event.url}）：{e}")

        logger.info(f"Notion：新增 {inserted} 筆，跳過重複 {skipped} 筆")

    def _create_page(self, event: SummarizedEvent) -> None:
        # 非 GitHub 來源的 Repo/Type 欄位轉換
        if event.source_type == SourceType.NEWS:
            repo_value = event.feed_name
            type_value = "Article"
        elif event.source_type == SourceType.PAPER:
            repo_value = ", ".join(event.categories[:3])
            type_value = "Paper"
        else:
            repo_value = event.repo_full_name
            type_value = event.event_type.value

        props: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": event.title[:100]}}]},
            "Repo": {"rich_text": [{"text": {"content": repo_value}}]},
            "Type": {"select": {"name": type_value}},
            "Source": {"select": {"name": event.source_type.value}},
            "Date": {"date": {"start": event.created_at.date().isoformat()}},
            "URL": {"url": event.url},
            "Classification": {"select": {"name": event.classification}},
            "Impact Level": {"select": {"name": event.impact_level.value}},
        }
        time.sleep(NOTION_SLEEP)
        self.client.pages.create(
            parent={"database_id": self.db_id},
            properties=props,
        )

    def _load_existing_urls(self) -> None:
        urls: set[str] = set()
        try:
            cursor = None
            while True:
                time.sleep(NOTION_SLEEP)
                kwargs: dict[str, Any] = {"database_id": self.db_id, "page_size": 100}
                if cursor:
                    kwargs["start_cursor"] = cursor
                resp = self.client.databases.query(**kwargs)
                for page in resp.get("results", []):
                    url = page.get("properties", {}).get("URL", {}).get("url")
                    if url:
                        urls.add(url)
                if not resp.get("has_more"):
                    break
                cursor = resp.get("next_cursor")
            self._existing_urls = urls
            logger.info(f"已載入 {len(urls)} 筆現有 URL（去重用）")
        except Exception as e:
            logger.warning(f"載入現有 URL 失敗：{e}")
            self._existing_urls = set()


class NotionOutput:
    name = "notion"

    def __init__(self, token: str, db_ids: NotionIds):
        self.writer = NotionWriter(token, db_ids)

    async def write(
        self,
        events: list[SummarizedEvent],
        daily_summary: str,
        day_str: str,
    ) -> None:
        self.writer.write_events(events)
