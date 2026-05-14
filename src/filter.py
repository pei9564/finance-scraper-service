"""
重要性過濾器 - 對事件評分並過濾低重要性事件（支援多來源）
"""
from __future__ import annotations

import logging

from models import EventType, FilterConfig, RawEvent, SourceType

logger = logging.getLogger(__name__)

# 標籤關鍵字（小寫比對）
BREAKING_LABELS = {"breaking change", "breaking-change", "type: breaking change", "breaking"}
SECURITY_LABELS = {"security", "vulnerability", "cve"}


def score_event(event: RawEvent, config: FilterConfig) -> float:
    """計算事件重要性分數（0.0 ~ 1.0），依來源分流。"""
    if event.source_type == SourceType.GITHUB:
        return _score_github(event, config)
    elif event.source_type == SourceType.NEWS:
        return _score_news(event)
    elif event.source_type == SourceType.PAPER:
        return _score_paper(event)
    return 0.0


def _score_github(event: RawEvent, config: FilterConfig) -> float:
    score = 0.0
    labels_lower = {label.lower() for label in event.labels}

    if labels_lower & BREAKING_LABELS:
        score += 0.5
    if labels_lower & SECURITY_LABELS:
        score += 0.4
    score += min(event.comment_count / 50.0, 0.2)
    score += min(event.reactions / 100.0, 0.15)

    if event.event_type == EventType.RELEASE:
        score += 0.3
    if event.is_merged is True:
        score += 0.1

    return min(score, 1.0)


def _score_news(event: RawEvent) -> float:
    score = 0.3
    if event.score >= 100:
        score += 0.4
    elif event.score >= 50:
        score += 0.2
    return min(score, 1.0)


def _score_paper(event: RawEvent) -> float:
    return 0.3


def filter_events(
    events: list[RawEvent],
    config: FilterConfig,
) -> list[RawEvent]:
    """過濾並排序事件。GitHub 用原有規則，News/Paper 全數通過。"""
    result = []
    for event in events:
        if event.source_type != SourceType.GITHUB:
            result.append(event)
            continue

        # GitHub 原有過濾邏輯
        event_score = _score_github(event, config)
        labels_lower = {label.lower() for label in event.labels}
        has_priority_label = bool(labels_lower & (BREAKING_LABELS | SECURITY_LABELS))

        if event.event_type == EventType.RELEASE:
            result.append(event)
        elif event.event_type == EventType.ISSUE:
            if event_score >= 0.15 or has_priority_label:
                if event.comment_count >= config.min_comments_for_issue or has_priority_label:
                    result.append(event)
        elif event.event_type == EventType.PR:
            if event_score >= 0.2 or (event.is_merged and has_priority_label):
                if event.comment_count >= config.min_comments_for_pr or has_priority_label:
                    result.append(event)

    result.sort(key=lambda e: score_event(e, config), reverse=True)
    logger.info(f"過濾：{len(events)} → {len(result)} 筆事件")
    return result
