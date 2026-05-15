"""WebOutput - 寫出每日 JSON artifact 並產生靜態網頁。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from tech_intel.domain import SummarizedEvent
from tech_intel.storage.bookmarks import compute_uid

from .site_generator import generate_site, prune_old

logger = logging.getLogger(__name__)

KEEP_DAYS = 30


def _event_to_dict(e: SummarizedEvent) -> dict:
    source = e.source_type.value
    return {
        "uid": compute_uid(source, e.url),
        "source": source,
        "repo": e.repo_full_name,
        "type": e.event_type.value,
        "classification": e.classification,
        "title": e.title,
        "url": e.url,
        "created_at": e.created_at.isoformat(),
        "impact_level": e.impact_level.value,
        "ai_summary": e.ai_summary,
        "body": e.body,
        "tags": e.tags,
        "migration_steps": e.migration_steps,
        # source-specific display fields
        "feed_name": e.feed_name,
        "score": e.score,
        "authors": e.authors,
        "categories": e.categories,
        "arxiv_id": e.arxiv_id,
    }


class WebOutput:
    name = "web"

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    async def write(
        self,
        events: list[SummarizedEvent],
        daily_summary: str,
        day_str: str,
    ) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{day_str}.json"

        data = {
            "date": day_str,
            "daily_summary": daily_summary,
            "events": [_event_to_dict(e) for e in events],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON artifact 寫入：{output_path}")

        prune_old(self.output_dir, keep_days=KEEP_DAYS)
        # index.html 放到兩層上的專案根目錄，從根目錄 serve 時可直接存取
        site_root = self.output_dir.parent.parent
        generate_site(self.output_dir, site_root=site_root)
