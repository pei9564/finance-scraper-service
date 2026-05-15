"""機密設定 — 由環境變數載入。

只有 GITHUB_TOKEN 是必要（github source 永遠啟用）；notion / telegram 視
config/repos.yaml 的 outputs 區塊而定，停用時可省略對應 env var。
"""
from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel


class NotionIds(BaseModel):
    activity_logs_db: str = ""

    @classmethod
    def from_env(cls) -> "NotionIds":
        return cls(
            activity_logs_db=os.environ.get("NOTION_DB_ACTIVITY_LOGS", ""),
        )


class Secrets(BaseModel):
    github_token: str
    notion_key: str = ""
    notion_db_ids: NotionIds = NotionIds()
    telegram_token: str = ""
    telegram_chat_id: str = ""

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            github_token=os.environ["GITHUB_TOKEN"],
            notion_key=os.environ.get("NOTION_API_KEY", ""),
            notion_db_ids=NotionIds.from_env(),
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        )
