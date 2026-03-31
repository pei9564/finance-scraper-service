"""
規則式分類器 - 不呼叫 LLM，純靠標籤和標題判斷
"""
from __future__ import annotations

import logging

from models import ClassifiedEvent, EventType, RawGitHubEvent
from filter import BREAKING_LABELS, SECURITY_LABELS, score_event
from models import FilterConfig

logger = logging.getLogger(__name__)

# 效能相關關鍵字
PERF_KEYWORDS = {"perf", "performance", "speed", "latency", "throughput", "benchmark", "optimize", "optimise"}

# Bug 標籤
BUG_LABELS = {"bug", "fix", "regression", "bugfix"}

# Feature 標籤
FEATURE_LABELS = {"feature", "enhancement", "feat", "new feature"}


def classify(event: RawGitHubEvent) -> ClassifiedEvent:
    """
    規則分類（優先順序由高到低）：
    Release/Breaking > Breaking > Security > Performance > Bug > Feature > Other
    """
    labels_lower = {label.lower() for label in event.labels}
    title_lower = event.title.lower()
    body_lower = (event.body or "").lower()

    classification = _determine_classification(event, labels_lower, title_lower, body_lower)
    _filter_config = FilterConfig()  # 使用預設值計算分數
    sig_score = score_event(event, _filter_config)

    return ClassifiedEvent(
        **event.model_dump(),
        classification=classification,
        significance_score=sig_score,
    )


def _determine_classification(
    event: RawGitHubEvent,
    labels_lower: set[str],
    title_lower: str,
    body_lower: str,
) -> str:
    # Release：檢查是否含 breaking change
    if event.event_type == EventType.RELEASE:
        breaking_keywords = {"breaking change", "breaking:", "removed:", "deprecated:"}
        if any(kw in body_lower for kw in breaking_keywords):
            return "Release/Breaking"
        return "Release"

    # Breaking change 標籤
    if labels_lower & BREAKING_LABELS:
        return "Breaking"

    # 安全相關
    if labels_lower & SECURITY_LABELS:
        return "Security"

    # 效能相關（標題關鍵字）
    if any(kw in title_lower for kw in PERF_KEYWORDS):
        return "Performance"

    # Bug 修復
    if labels_lower & BUG_LABELS:
        return "Bug"

    # 新功能
    if labels_lower & FEATURE_LABELS:
        return "Feature"

    # 已 merge 的 PR 預設為 Feature
    if event.event_type == EventType.PR and event.is_merged:
        return "Feature"

    return "Other"


def classify_all(events: list[RawGitHubEvent]) -> list[ClassifiedEvent]:
    classified = [classify(e) for e in events]
    # 統計各分類數量
    counts: dict[str, int] = {}
    for e in classified:
        counts[e.classification] = counts.get(e.classification, 0) + 1
    logger.info(f"分類結果：{counts}")
    return classified
