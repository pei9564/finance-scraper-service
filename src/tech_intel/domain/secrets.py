"""機密設定 — 由環境變數載入。"""
from __future__ import annotations

import os

from pydantic import BaseModel


class NotionIds(BaseModel):
    activity_logs_db: str

    @classmethod
    def from_env(cls) -> "NotionIds":
        return cls(
            activity_logs_db=os.environ["NOTION_DB_ACTIVITY_LOGS"],
        )


class Secrets(BaseModel):
    github_token: str
    notion_key: str
    notion_db_ids: NotionIds
    telegram_token: str
    telegram_chat_id: str

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            github_token=os.environ["GITHUB_TOKEN"],
            notion_key=os.environ["NOTION_API_KEY"],
            notion_db_ids=NotionIds.from_env(),
            telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )
