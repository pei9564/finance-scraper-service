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


async def retry_summary(
    day_str: str, source: str, feed_name: str | None = None,
    progress: dict | None = None,
) -> dict[str, int]:
    """強制重跑指定發佈日(TW) + source(+ feed_name)所有事件的摘要。

    day_str 是事件的「發佈日」(created_at, Asia/Taipei),不是 pipeline run date —
    sidebar / UI 都用發佈日分組,retry 自然也對齊。
    feed_name 為 None 時不過濾(paper 整類);非 None 時只跑該 feed。
    LLM 回傳新內容才覆寫;失敗或回相同內容則保留原 ai_summary。
    回傳 {"updated": 實際覆寫筆數, "failed": LLM 失敗或無變化筆數, "total": 處理總數}。
    """
    load_dotenv()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = AppConfig(**yaml.safe_load(f))

    await init_schema()  # CLI 直接跑時需要;server 啟動時已經跑過,重入無害

    # 強制重跑該發佈日該 feed 的所有事件;LLM 回新內容才覆寫
    need_summary = await daily.list_events_by_pub_date(day_str, source, feed_name)

    if not need_summary:
        logger.info(f"無事件可重跑：{source} / {day_str}")
        return {"updated": 0, "failed": 0, "total": 0}

    total = len(need_summary)
    logger.info(f"重跑摘要：{source} / {day_str}，共 {total} 筆")
    llm = LLMGatewayClient(config.ai)
    step = SummarizeStep(llm, config.ai)

    updated = 0
    failed = 0
    if progress is not None:
        # 共用 dict — server 持有相同 ref,/api/status 讀到的就是最新進度
        progress.update(total=total, done=0, updated=0, failed=0, current=None)
    for d in need_summary:
        if progress is not None:
            progress["current"] = d.get("title") or d.get("url") or "?"
        body_updated: str | None = None
        if not (d.get("body") or "").strip():
            logger.info(f"抓取內文：{d['url']}")
            fetched = await asyncio.to_thread(fetch_article_text, d["url"])
            if fetched:
                d["body"] = fetched
                body_updated = fetched
            else:
                logger.warning(f"抓取失敗，略過：{d['url']}")
                failed += 1
                if progress is not None:
                    progress.update(done=progress.get("done", 0) + 1,
                                    updated=updated, failed=failed)
                continue

        old_summary = (d.get("ai_summary") or "").strip()
        event = _dict_to_event(d)
        # SummarizeStep.apply 是同步呼叫，丟 thread 避免擋 event loop
        result = await asyncio.to_thread(step.apply, event)
        new_summary = (result.ai_summary or "").strip()
        # LLM 失敗時 SummarizeStep 會回原本的 event(ai_summary 不變);
        # 只有真的拿到不同內容才覆寫,避免把舊摘要當成新結果寫回去
        if new_summary and new_summary != old_summary:
            await daily.update_event_summary(d["uid"], new_summary, body_updated)
            updated += 1
        else:
            failed += 1
        if progress is not None:
            progress.update(done=progress.get("done", 0) + 1,
                            updated=updated, failed=failed)

    logger.info(f"補充完成：{updated} 成功 / {failed} 失敗 / {total} 待補")
    return {"updated": updated, "failed": failed, "total": total}


def cli():
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="補充缺少摘要的事件")
    parser.add_argument("date", help="日期，例如 2026-05-15")
    parser.add_argument("source", help="來源類別,例如 news / paper / finance / youtube_fin")
    parser.add_argument("--feed", default=None, help="可選:只補該 feed_name")
    args = parser.parse_args()
    result = asyncio.run(retry_summary(args.date, args.source, args.feed))
    print(f"更新 {result['updated']} 筆 / 失敗 {result['failed']} 筆 / 待補 {result['total']} 筆")


if __name__ == "__main__":
    cli()
