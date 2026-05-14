"""
論文收集器 - arXiv API
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import arxiv

from models import PaperConfig, RawPaperEvent

logger = logging.getLogger(__name__)


class PaperCollector:
    def __init__(self, config: PaperConfig, lookback_days: int = 1):
        self.config = config
        self.lookback_days = lookback_days

    def collect_all(self) -> list[RawPaperEvent]:
        events: list[RawPaperEvent] = []

        for category in self.config.arxiv_categories:
            try:
                cat_events = self._fetch_arxiv(category)
                events.extend(cat_events)
            except Exception as e:
                logger.error(f"arXiv category '{category}' 收集失敗：{e}")

        logger.info(f"Papers 收集完成：{len(events)} 筆")
        return events

    def _fetch_arxiv(self, category: str) -> list[RawPaperEvent]:
        query = f"cat:{category}"
        if self.config.arxiv_keywords:
            kw_query = " OR ".join(f'abs:"{kw}"' for kw in self.config.arxiv_keywords)
            query = f"({query}) AND ({kw_query})"

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=self.config.arxiv_max_per_category,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        events = []
        cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=self.lookback_days)

        for result in client.results(search):
            # Filter by date since arXiv API doesn't support date range natively
            if result.published.replace(tzinfo=timezone.utc) < cutoff:
                continue

            arxiv_id = result.entry_id.split("/")[-1] if result.entry_id else ""
            authors = [a.name for a in result.authors[:5]]
            categories = [c for c in result.categories]

            events.append(RawPaperEvent(
                title=result.title.replace("\n", " ").strip(),
                url=result.entry_id,
                created_at=result.published.replace(tzinfo=timezone.utc),
                body=result.summary.replace("\n", " ").strip() if result.summary else None,
                authors=authors,
                categories=categories,
                arxiv_id=arxiv_id,
            ))

        logger.info(f"arXiv '{category}'：{len(events)} 筆")
        return events
