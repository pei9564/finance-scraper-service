"""列舉型別。"""
from __future__ import annotations

from enum import Enum


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
