"""重要性過濾器 - 對事件評分並排序(目前所有來源皆全數通過,只重排)。"""
from __future__ import annotations

import logging

from finance_scraper.domain import FilterConfig, RawEvent, SourceType

logger = logging.getLogger(__name__)


def score_event(event: RawEvent, config: FilterConfig) -> float:
    """計算事件重要性分數(0.0 ~ 1.0),依來源分流。"""
    if event.source_type == SourceType.NEWS:
        return _score_news(event)
    if event.source_type == SourceType.PAPER:
        return _score_paper(event)
    if event.source_type == SourceType.FINANCE:
        return _score_finance(event)
    return 0.0


def _score_news(event: RawEvent) -> float:
    score = 0.3
    if event.score >= 100:
        score += 0.4
    elif event.score >= 50:
        score += 0.2
    return min(score, 1.0)


def _score_paper(event: RawEvent) -> float:
    return 0.3


def _score_finance(event: RawEvent) -> float:
    return 0.3


def filter_events(events: list[RawEvent], config: FilterConfig) -> list[RawEvent]:
    """目前所有來源全數通過,僅依分數排序(高→低)。"""
    result = list(events)
    result.sort(key=lambda e: score_event(e, config), reverse=True)
    logger.info(f"過濾:{len(events)} → {len(result)} 筆事件")
    return result
