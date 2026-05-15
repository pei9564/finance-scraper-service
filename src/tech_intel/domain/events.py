"""事件資料模型 — pipeline 各階段流轉的型別。

RawEvent + Raw{GitHub,News,Paper}Event → ClassifiedEvent → SummarizedEvent。
ClassifiedEvent 以「optional 欄位聯集」承載所有來源的欄位，此規模下務實，
collector 與 output 都依賴這個統一模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .enums import EventType, ImpactLevel, SourceType


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
    score: int = 0  # HF Daily Papers 的 upvotes（arXiv 來源為 0）


class ClassifiedEvent(RawEvent):
    # GitHub-specific（非 GitHub 來源留預設值）
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
    # Pipeline 欄位
    classification: str = "Other"
    significance_score: float = 0.0


class SummarizedEvent(ClassifiedEvent):
    ai_summary: str = ""
    impact_level: ImpactLevel = ImpactLevel.MEDIUM
    tags: list[str] = Field(default_factory=list)
    migration_steps: list[str] = Field(default_factory=list)
