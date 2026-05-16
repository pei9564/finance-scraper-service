"""列舉型別。"""
from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    NEWS = "news"
    PAPER = "paper"
    FINANCE = "finance"


class EventType(str, Enum):
    ARTICLE = "Article"
    PAPER = "Paper"


class ImpactLevel(str, Enum):
    BREAKING = "Breaking"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
