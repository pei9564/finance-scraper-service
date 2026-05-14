"""
規則式分類器 - 不呼叫 LLM，純靠標籤和標題判斷（支援多來源）
"""
from __future__ import annotations

import logging

from models import ClassifiedEvent, EventType, RawEvent, SourceType
from filter import BREAKING_LABELS, SECURITY_LABELS, score_event
from models import FilterConfig

logger = logging.getLogger(__name__)

# 效能相關關鍵字
PERF_KEYWORDS = {"perf", "performance", "speed", "latency", "throughput", "benchmark", "optimize", "optimise"}

# Bug 標籤
BUG_LABELS = {"bug", "fix", "regression", "bugfix"}

# Feature 標籤
FEATURE_LABELS = {"feature", "enhancement", "feat", "new feature"}


def classify(event: RawEvent) -> ClassifiedEvent:
    if event.source_type == SourceType.GITHUB:
        return _classify_github(event)
    elif event.source_type == SourceType.NEWS:
        return _classify_news(event)
    elif event.source_type == SourceType.PAPER:
        return _classify_paper(event)
    return ClassifiedEvent(**event.model_dump(), classification="Other", significance_score=0.0)


def _classify_github(event: RawEvent) -> ClassifiedEvent:
    labels_lower = {label.lower() for label in event.labels}
    title_lower = event.title.lower()
    body_lower = (event.body or "").lower()

    classification = _determine_github_classification(event, labels_lower, title_lower, body_lower)
    _filter_config = FilterConfig()
    sig_score = score_event(event, _filter_config)

    return ClassifiedEvent(
        **event.model_dump(),
        classification=classification,
        significance_score=sig_score,
    )


def _classify_news(event: RawEvent) -> ClassifiedEvent:
    _filter_config = FilterConfig()
    sig_score = score_event(event, _filter_config)
    return ClassifiedEvent(
        **event.model_dump(),
        classification="News",
        significance_score=sig_score,
    )


def _classify_paper(event: RawEvent) -> ClassifiedEvent:
    _filter_config = FilterConfig()
    sig_score = score_event(event, _filter_config)
    return ClassifiedEvent(
        **event.model_dump(),
        classification="Paper",
        significance_score=sig_score,
    )


def _determine_github_classification(
    event: RawEvent,
    labels_lower: set[str],
    title_lower: str,
    body_lower: str,
) -> str:
    if event.event_type == EventType.RELEASE:
        breaking_keywords = {"breaking change", "breaking:", "removed:", "deprecated:"}
        if any(kw in body_lower for kw in breaking_keywords):
            return "Release/Breaking"
        return "Release"

    if labels_lower & BREAKING_LABELS:
        return "Breaking"
    if labels_lower & SECURITY_LABELS:
        return "Security"
    if any(kw in title_lower for kw in PERF_KEYWORDS):
        return "Performance"
    if labels_lower & BUG_LABELS:
        return "Bug"
    if labels_lower & FEATURE_LABELS:
        return "Feature"
    if event.event_type == EventType.PR and event.is_merged:
        return "Feature"

    return "Other"


def classify_all(events: list[RawEvent]) -> list[ClassifiedEvent]:
    classified = [classify(e) for e in events]
    counts: dict[str, int] = {}
    for e in classified:
        counts[e.classification] = counts.get(e.classification, 0) + 1
    logger.info(f"分類結果：{counts}")
    return classified
