"""事件資料模型 — pipeline 各階段流轉的型別。

RawEvent + Raw{News,Paper}Event → ClassifiedEvent → SummarizedEvent。
ClassifiedEvent 以「optional 欄位聯集」承載所有來源的欄位,此規模下務實,
collector 與 output 都依賴這個統一模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .enums import EventType, ImpactLevel, SourceType


class RawEvent(BaseModel):
    source_type: SourceType = SourceType.NEWS
    event_type: EventType
    title: str
    url: str
    created_at: datetime
    body: Optional[str] = None
    # body 的語言:'zh' / 'en' / ... / None=未知。translate-day 用此判斷該不該翻;
    # collector 蒐集時依 feed 設定填,媒體類蒐集後 body 為空、body_lang 也為 None
    body_lang: Optional[str] = None


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
    score: int = 0  # HF Daily Papers 的 upvotes(arXiv 來源為 0)


class ClassifiedEvent(RawEvent):
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
