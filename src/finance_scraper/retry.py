"""補充缺少 ai_summary 的事件摘要，不重抓資料。

用法：
  finance-scraper-retry 2026-05-15 paper
  finance-scraper-retry 2026-05-15 news
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from finance_scraper.domain import AppConfig, EventType, ImpactLevel, SourceType, SummarizedEvent
from finance_scraper.infrastructure import LLMGatewayClient
from finance_scraper.sources.steps import SummarizeStep
from finance_scraper.sources.steps.fetch_body import fetch_article_text
from finance_scraper.storage import daily, init_schema

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "repos.yaml"


def _dict_to_event(d: dict) -> SummarizedEvent:
    created_at = datetime.fromisoformat(d["created_at"])
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return SummarizedEvent(
        source_type=SourceType(d["source"]),
        event_type=EventType(d.get("type", "Article")),
        classification=d.get("classification"),
        title=d["title"],
        url=d["url"],
        created_at=created_at,
        impact_level=ImpactLevel(d.get("impact_level", "Low")),
        ai_summary=d.get("ai_summary") or "",
        body=d.get("body"),
        tags=d.get("tags") or [],
        migration_steps=d.get("migration_steps") or [],
        feed_name=d.get("feed_name"),
        score=d.get("score"),
        authors=d.get("authors") or [],
        categories=d.get("categories") or [],
        arxiv_id=d.get("arxiv_id"),
    )


async def retry_summary(day_str: str, source: str) -> int:
    """補充當日 source 中缺少 ai_summary 的事件，回傳更新筆數。"""
    load_dotenv()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = AppConfig(**yaml.safe_load(f))

    await init_schema()

    data = await daily.load_run(day_str)
    if data is None:
        raise FileNotFoundError(f"PG 找不到日報：{day_str}")
    events = data.get("events", [])

    need_summary = [
        d for d in events
        if d.get("source") == source and not d.get("ai_summary")
    ]

    if not need_summary:
        logger.info(f"無需補充：{source} / {day_str} 已全有摘要")
        return 0

    logger.info(f"補充摘要：{source} / {day_str}，共 {len(need_summary)} 筆")
    llm = LLMGatewayClient(config.ai)
    step = SummarizeStep(llm, config.ai)

    updated = 0
    for d in need_summary:
        body_updated: str | None = None
        if not (d.get("body") or "").strip():
            logger.info(f"抓取內文：{d['url']}")
            fetched = await asyncio.to_thread(fetch_article_text, d["url"])
            if fetched:
                d["body"] = fetched
                body_updated = fetched
            else:
                logger.warning(f"抓取失敗，略過：{d['url']}")
                continue

        event = _dict_to_event(d)
        # SummarizeStep.apply 是同步呼叫，丟 thread 避免擋 event loop
        result = await asyncio.to_thread(step.apply, event)
        if result.ai_summary:
            await daily.update_event_summary(d["uid"], result.ai_summary, body_updated)
            updated += 1

    if updated:
        logger.info(f"補充完成：{updated}/{len(need_summary)} 筆")
    return updated


def cli():
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="補充缺少摘要的事件")
    parser.add_argument("date", help="日期，例如 2026-05-15")
    parser.add_argument("source", choices=["news", "paper", "finance"], help="來源類別")
    args = parser.parse_args()
    count = asyncio.run(retry_summary(args.date, args.source))
    print(f"更新 {count} 筆")


if __name__ == "__main__":
    cli()
