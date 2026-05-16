"""列舉型別。"""
from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    NEWS = "news"
    PAPER = "paper"
    FINANCE = "finance"
    YOUTUBE_TECH = "youtube_tech"
    YOUTUBE_FIN = "youtube_fin"
    PODCAST_TECH = "podcast_tech"
    PODCAST_FIN = "podcast_fin"


MEDIA_SOURCE_TYPES: frozenset[SourceType] = frozenset({
    SourceType.YOUTUBE_TECH,
    SourceType.YOUTUBE_FIN,
    SourceType.PODCAST_TECH,
    SourceType.PODCAST_FIN,
})


class EventType(str, Enum):
    ARTICLE = "Article"
    PAPER = "Paper"
    VIDEO = "Video"
    PODCAST = "Podcast"


class ImpactLevel(str, Enum):
    BREAKING = "Breaking"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
