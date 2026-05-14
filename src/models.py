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


class SourceType(str, Enum):
    GITHUB = "github"
    NEWS = "news"
    PAPER = "paper"


class EventType(str, Enum):
    RELEASE = "Release"
    ISSUE = "Issue"
    PR = "PR"
    ARTICLE = "Article"
    PAPER = "Paper"


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


class SummaryProfile(BaseModel):
    max_tokens: int = 600
    instruction: str = ""


class AIConfig(BaseModel):
    # 內部 LLM gateway（OpenAI 相容），用於逐則與日報摘要
    vllm_enabled: bool = True
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model: str = ""  # 留空則自動向 /models 探測
    # 各來源的逐則摘要設定，key 為 SourceType 值（news / paper / ...）
    summary_profiles: dict[str, SummaryProfile] = Field(default_factory=dict)


class TelegramConfig(BaseModel):
    max_events_per_message: int = 10
    critical_only_for_immediate: bool = True


class RSSFeedConfig(BaseModel):
    name: str
    url: str


class NewsConfig(BaseModel):
    hackernews_enabled: bool = True
    hackernews_top_n: int = 20
    hackernews_min_score: int = 50
    rss_feeds: list[RSSFeedConfig] = Field(default_factory=list)


class PaperConfig(BaseModel):
    arxiv_categories: list[str] = Field(default_factory=lambda: ["cs.AI", "cs.CL", "cs.LG"])
    arxiv_max_per_category: int = 10
    arxiv_keywords: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    repos: list[RepoConfig]
    news: NewsConfig = Field(default_factory=NewsConfig)
    papers: PaperConfig = Field(default_factory=PaperConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


# ---------------------------------------------------------------------------
# Event models - base + source-specific
# ---------------------------------------------------------------------------

class RawEvent(BaseModel):
    source_type: SourceType = SourceType.GITHUB
    event_type: EventType
    title: str
    url: str
    created_at: datetime
    body: Optional[str] = None


class RawGitHubEvent(RawEvent):
    source_type: SourceType = SourceType.GITHUB
    repo_full_name: str
    number: Optional[int] = None
    tag: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    comment_count: int = 0
    reactions: int = 0
    is_merged: Optional[bool] = None
    diff_url: Optional[str] = None


class RawNewsEvent(RawEvent):
    source_type: SourceType = SourceType.NEWS
    event_type: EventType = EventType.ARTICLE
    feed_name: str = ""
    score: int = 0
    author: Optional[str] = None


class RawPaperEvent(RawEvent):
    source_type: SourceType = SourceType.PAPER
    event_type: EventType = EventType.PAPER
    authors: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    arxiv_id: str = ""


# ---------------------------------------------------------------------------
# Pipeline event models (generic across sources)
# ---------------------------------------------------------------------------

class ClassifiedEvent(RawEvent):
    # GitHub-specific (Optional for non-GitHub sources)
    repo_full_name: Optional[str] = None
    number: Optional[int] = None
    tag: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    comment_count: int = 0
    reactions: int = 0
    is_merged: Optional[bool] = None
    diff_url: Optional[str] = None
    # News-specific
    feed_name: str = ""
    score: int = 0
    author: Optional[str] = None
    # Paper-specific
    authors: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    arxiv_id: str = ""
    # Pipeline fields
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
