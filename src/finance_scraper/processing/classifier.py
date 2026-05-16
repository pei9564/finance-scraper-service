"""規則式分類器 - 不呼叫 LLM,純依來源指派類別標籤。"""
from __future__ import annotations

import logging

from finance_scraper.domain import ClassifiedEvent, FilterConfig, RawEvent, SourceType

from .filter import score_event

logger = logging.getLogger(__name__)


_LABEL_BY_SOURCE: dict[SourceType, str] = {
    SourceType.NEWS: "News",
    SourceType.PAPER: "Paper",
    SourceType.FINANCE: "Finance",
}


def classify(event: RawEvent) -> ClassifiedEvent:
    classification = _LABEL_BY_SOURCE.get(event.source_type, "Other")
    sig_score = score_event(event, FilterConfig())
    return ClassifiedEvent(
        **event.model_dump(),
        classification=classification,
        significance_score=sig_score,
    )


def classify_all(events: list[RawEvent]) -> list[ClassifiedEvent]:
    classified = [classify(e) for e in events]
    counts: dict[str, int] = {}
    for e in classified:
        counts[e.classification] = counts.get(e.classification, 0) + 1
    logger.info(f"分類結果:{counts}")
    return classified
