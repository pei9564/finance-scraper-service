"""
資料模型定義 - 所有 Pydantic v2 模型
"""
from __future__ import annotations

import os
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    RELEASE = "Release"
    ISSUE = "Issue"
    PR = "PR"


class ImpactLevel(str, Enum):
    BREAKING = "Breaking"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------

class RepoConfig(BaseModel):
    owner: str
    name: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class FilterConfig(BaseModel):
    min_reactions: int = 0
    min_comments_for_issue: int = 3
    min_comments_for_pr: int = 2
    include_labels: list[str] = Field(default_factory=list)
    lookback_days: int = 7


class AIConfig(BaseModel):
    flash_model: str = "gemini-2.0-flash"
    pro_model: str = "gemini-2.5-pro-preview-05-06"
    max_summary_tokens: int = 300
    max_diff_tokens: int = 150000
    diff_chunk_size: int = 50000


class TelegramConfig(BaseModel):
    max_events_per_message: int = 10
    critical_only_for_immediate: bool = True


class AppConfig(BaseModel):
    repos: list[RepoConfig]
    filters: FilterConfig = Field(default_factory=FilterConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


# ---------------------------------------------------------------------------
# GitHub event models
# ---------------------------------------------------------------------------

class RawGitHubEvent(BaseModel):
    repo_full_name: str
    event_type: EventType
    title: str
    number: Optional[int] = None      # PR / Issue 編號；Release 為 None
    tag: Optional[str] = None         # 只有 Release 才有
    url: str
    created_at: datetime
    body: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    comment_count: int = 0
    reactions: int = 0
    is_merged: Optional[bool] = None  # 只有 PR 才有
    diff_url: Optional[str] = None    # 只有 PR 才有


class ClassifiedEvent(RawGitHubEvent):
    classification: str = "Other"
    significance_score: float = 0.0


class SummarizedEvent(ClassifiedEvent):
    ai_summary: str = ""
    impact_level: ImpactLevel = ImpactLevel.MEDIUM
    tags: list[str] = Field(default_factory=list)
    migration_steps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class WeeklyReport(BaseModel):
    week_start: date
    week_end: date
    repo_summaries: dict[str, list[SummarizedEvent]] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    failed_repos: list[str] = Field(default_factory=list)
    total_events: int = 0


class NotionIds(BaseModel):
    activity_logs_db: str

    @classmethod
    def from_env(cls) -> "NotionIds":
        return cls(
            activity_logs_db=os.environ["NOTION_DB_ACTIVITY_LOGS"],
        )


class Secrets(BaseModel):
    github_token: str
    google_api_key: str
    notion_key: str
    notion_db_ids: NotionIds
    telegram_token: str
    telegram_chat_id: str

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            github_token=os.environ["GITHUB_TOKEN"],
            google_api_key=os.environ["GOOGLE_API_KEY"],
            notion_key=os.environ["NOTION_API_KEY"],
            notion_db_ids=NotionIds.from_env(),
            telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )
