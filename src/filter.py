"""
重要性過濾器 - 對事件評分並過濾低重要性事件
"""
from __future__ import annotations

import logging

from models import EventType, FilterConfig, RawGitHubEvent

logger = logging.getLogger(__name__)

# 標籤關鍵字（小寫比對）
BREAKING_LABELS = {"breaking change", "breaking-change", "type: breaking change", "breaking"}
SECURITY_LABELS = {"security", "vulnerability", "cve"}


def score_event(event: RawGitHubEvent, config: FilterConfig) -> float:
    """計算事件重要性分數（0.0 ~ 1.0）。"""
    score = 0.0
    labels_lower = {label.lower() for label in event.labels}

    # Breaking change 標籤（最高權重）
    if labels_lower & BREAKING_LABELS:
        score += 0.5

    # 安全相關標籤
    if labels_lower & SECURITY_LABELS:
        score += 0.4

    # 互動量（留言數）
    score += min(event.comment_count / 50.0, 0.2)

    # 反應數
    score += min(event.reactions / 100.0, 0.15)

    # Release 額外加分
    if event.event_type == EventType.RELEASE:
        score += 0.3

    # 已 merge 的 PR 加分
    if event.is_merged is True:
        score += 0.1

    return min(score, 1.0)


def filter_events(
    events: list[RawGitHubEvent],
    config: FilterConfig,
) -> list[RawGitHubEvent]:
    """
    過濾並排序事件。

    規則：
    - Release：一律通過
    - Issue：score >= 0.15 或含 breaking/security 標籤
    - PR：score >= 0.2 或已 merge 且含 breaking/security 標籤
    """
    result = []
    for event in events:
        event_score = score_event(event, config)
        labels_lower = {label.lower() for label in event.labels}
        has_priority_label = bool(labels_lower & (BREAKING_LABELS | SECURITY_LABELS))

        if event.event_type == EventType.RELEASE:
            result.append(event)

        elif event.event_type == EventType.ISSUE:
            if event_score >= 0.15 or has_priority_label:
                # 確保留言數達標（除非有重要標籤）
                if event.comment_count >= config.min_comments_for_issue or has_priority_label:
                    result.append(event)

        elif event.event_type == EventType.PR:
            if event_score >= 0.2 or (event.is_merged and has_priority_label):
                if event.comment_count >= config.min_comments_for_pr or has_priority_label:
                    result.append(event)

    # 依分數由高到低排序
    result.sort(key=lambda e: score_event(e, config), reverse=True)
    logger.info(f"過濾：{len(events)} → {len(result)} 筆事件")
    return result
