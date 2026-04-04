"""
Notion 寫入器 - 寫入重大更新到單一資料庫
"""
from __future__ import annotations

import logging
import time
from typing import Any

from notion_client import Client

from models import NotionIds, SummarizedEvent

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
        props: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": event.title[:100]}}]},
            "Repo": {"rich_text": [{"text": {"content": event.repo_full_name}}]},
            "Type": {"select": {"name": event.event_type.value}},
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
