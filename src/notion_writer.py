"""
Notion 寫入器 - 寫入三個資料庫
1. Repositories DB  - repo 基本資訊（upsert）
2. Activity Logs DB - 個別事件（URL 去重）
3. Weekly Tech Radar DB - 每週摘要（upsert）
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from notion_client import Client
from notion_client.errors import APIResponseError

from models import AppConfig, ImpactLevel, NotionIds, RepoPriority, SummarizedEvent

logger = logging.getLogger(__name__)

# Notion API 限制 3 req/sec，保守使用 0.4s 間隔
NOTION_SLEEP = 0.4


class NotionWriter:
    def __init__(self, token: str, db_ids: NotionIds):
        self.client = Client(auth=token)
        self.db_ids = db_ids
        # 快取已存在的 Activity Log URL，避免重複 API 查詢
        self._existing_urls: set[str] | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def write_all(
        self,
        events: list[SummarizedEvent],
        config: AppConfig,
    ) -> None:
        """寫入全部資料到 Notion。"""
        # 預先載入已存在的 URL（批次查詢，減少 API 呼叫）
        self._load_existing_urls()

        # 1. Repositories DB（每個 repo upsert 一次）
        for repo_config in config.repos:
            repo_events = [e for e in events if e.repo_full_name == repo_config.full_name]
            try:
                self._upsert_repo(repo_config.full_name, repo_events)
            except Exception as e:
                logger.error(f"Repositories DB 寫入失敗（{repo_config.full_name}）：{e}")

        # 2. Activity Logs DB
        inserted = 0
        skipped = 0
        for event in events:
            if event.url in (self._existing_urls or set()):
                skipped += 1
                continue
            try:
                self._create_activity_log(event)
                if self._existing_urls is not None:
                    self._existing_urls.add(event.url)
                inserted += 1
            except Exception as e:
                logger.error(f"Activity Log 寫入失敗（{event.url}）：{e}")

        logger.info(f"Activity Logs：新增 {inserted} 筆，跳過重複 {skipped} 筆")

        # 3. Weekly Tech Radar DB
        week_str = datetime.utcnow().strftime("%Y-W%U")
        by_repo: dict[str, list[SummarizedEvent]] = {}
        for event in events:
            by_repo.setdefault(event.repo_full_name, []).append(event)

        for repo_name, repo_events in by_repo.items():
            try:
                self._upsert_weekly_radar(week_str, repo_name, repo_events)
            except Exception as e:
                logger.error(f"Weekly Radar 寫入失敗（{repo_name}）：{e}")

    # ------------------------------------------------------------------
    # Repositories DB
    # ------------------------------------------------------------------

    def _upsert_repo(self, repo_full_name: str, events: list[SummarizedEvent]) -> None:
        existing = self._query_by_title(self.db_ids.repositories_db, repo_full_name)

        latest_release = next(
            (e.tag for e in events if e.tag and e.event_type.value == "Release"),
            None,
        )

        props: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": repo_full_name}}]},
            "URL": {"url": f"https://github.com/{repo_full_name}"},
            "Last Updated": {"date": {"start": datetime.utcnow().isoformat()}},
        }
        if latest_release:
            props["Last Release"] = {"rich_text": [{"text": {"content": latest_release}}]}

        time.sleep(NOTION_SLEEP)
        if existing:
            self.client.pages.update(page_id=existing["id"], properties=props)
            logger.debug(f"Repo 更新：{repo_full_name}")
        else:
            self.client.pages.create(
                parent={"database_id": self.db_ids.repositories_db},
                properties=props,
            )
            logger.debug(f"Repo 新增：{repo_full_name}")

    # ------------------------------------------------------------------
    # Activity Logs DB
    # ------------------------------------------------------------------

    def _create_activity_log(self, event: SummarizedEvent) -> None:
        impact_name = event.impact_level.value
        props: dict[str, Any] = {
            "Title": {"title": [{"text": {"content": event.title[:100]}}]},
            "Repo": {"rich_text": [{"text": {"content": event.repo_full_name}}]},
            "Type": {"select": {"name": event.event_type.value}},
            "Date": {"date": {"start": event.created_at.isoformat()}},
            "URL": {"url": event.url},
            "AI Summary": {"rich_text": [{"text": {"content": event.ai_summary[:2000]}}]},
            "Impact Level": {"select": {"name": impact_name}},
            "Classification": {"rich_text": [{"text": {"content": event.classification}}]},
        }
        if event.tags:
            props["Tags"] = {"multi_select": [{"name": t} for t in event.tags[:5]]}

        time.sleep(NOTION_SLEEP)
        self.client.pages.create(
            parent={"database_id": self.db_ids.activity_logs_db},
            properties=props,
        )

    # ------------------------------------------------------------------
    # Weekly Tech Radar DB
    # ------------------------------------------------------------------

    def _upsert_weekly_radar(
        self,
        week_str: str,
        repo_name: str,
        events: list[SummarizedEvent],
    ) -> None:
        page_title = f"{week_str} | {repo_name}"
        existing = self._query_by_title(self.db_ids.weekly_radar_db, page_title)

        breaking = [e for e in events if e.impact_level == ImpactLevel.BREAKING
                    or e.classification in {"Breaking", "Release/Breaking", "Security"}]

        key_changes = "\n".join(
            f"• [{e.classification}] {e.title}: {e.ai_summary[:200]}"
            for e in events[:20]
        )
        breaking_text = "\n".join(
            f"• {e.title}: {e.ai_summary[:300]}"
            for e in breaking
        ) or "本週無 breaking change"

        migration_text = ""
        for e in breaking:
            if e.migration_steps:
                migration_text += f"\n{e.title}:\n"
                migration_text += "\n".join(f"  {i+1}. {s}" for i, s in enumerate(e.migration_steps))

        props: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": page_title}}]},
            "Week": {"rich_text": [{"text": {"content": week_str}}]},
            "Repo": {"rich_text": [{"text": {"content": repo_name}}]},
            "Key Changes": {"rich_text": [{"text": {"content": key_changes[:2000]}}]},
            "Breaking Changes": {"rich_text": [{"text": {"content": breaking_text[:2000]}}]},
            "Total Events": {"number": len(events)},
        }
        if migration_text:
            props["Migration Notes"] = {"rich_text": [{"text": {"content": migration_text[:2000]}}]}

        time.sleep(NOTION_SLEEP)
        if existing:
            self.client.pages.update(page_id=existing["id"], properties=props)
        else:
            self.client.pages.create(
                parent={"database_id": self.db_ids.weekly_radar_db},
                properties=props,
            )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _query_by_title(self, db_id: str, title: str) -> dict | None:
        """查詢資料庫中是否已存在相同標題的頁面。"""
        try:
            time.sleep(NOTION_SLEEP)
            resp = self.client.databases.query(
                database_id=db_id,
                filter={
                    "property": "Name",
                    "title": {"equals": title},
                },
                page_size=1,
            )
            results = resp.get("results", [])
            return results[0] if results else None
        except APIResponseError as e:
            logger.warning(f"查詢 Notion 失敗：{e}")
            return None

    def _load_existing_urls(self) -> None:
        """批次載入 Activity Logs 中已存在的 URL，用於去重。"""
        urls: set[str] = set()
        try:
            cursor = None
            while True:
                time.sleep(NOTION_SLEEP)
                kwargs: dict[str, Any] = {
                    "database_id": self.db_ids.activity_logs_db,
                    "page_size": 100,
                }
                if cursor:
                    kwargs["start_cursor"] = cursor

                resp = self.client.databases.query(**kwargs)
                for page in resp.get("results", []):
                    url_prop = page.get("properties", {}).get("URL", {})
                    url = url_prop.get("url")
                    if url:
                        urls.add(url)

                if not resp.get("has_more"):
                    break
                cursor = resp.get("next_cursor")

            self._existing_urls = urls
            logger.info(f"已載入 {len(urls)} 筆現有 URL（去重用）")
        except Exception as e:
            logger.warning(f"載入現有 URL 失敗，跳過去重：{e}")
            self._existing_urls = set()
