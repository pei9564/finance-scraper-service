"""補充缺少 ai_summary 的事件摘要，不重抓資料。

用法：
  tech-intel-retry 2026-05-15 paper
  tech-intel-retry 2026-05-15 news
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from tech_intel.domain import AppConfig, EventType, ImpactLevel, SourceType, SummarizedEvent
from tech_intel.infrastructure import LLMGatewayClient
from tech_intel.outputs.site_generator import generate_site
from tech_intel.sources.steps import SummarizeStep

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "repos.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output" / "weekly"


def _fetch_body(url: str) -> str | None:
    """從 URL 抓取文章內文；失敗或內容過短回傳 None。"""
    try:
        import httpx
        import trafilatura
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TechIntelBot/1.0)"}
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
        r.raise_for_status()
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False)
        return text if text and len(text) > 100 else None
    except Exception as e:
        logger.debug(f"抓取內文失敗 {url}：{e}")
        return None


def _dict_to_event(d: dict) -> SummarizedEvent:
    created_at = datetime.fromisoformat(d["created_at"])
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return SummarizedEvent(
        source_type=SourceType(d["source"]),
        repo_full_name=d.get("repo"),
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


def retry_summary(date: str, source: str) -> int:
    """補充 date 當天 source 來源中缺少 ai_summary 的事件，回傳更新筆數。"""
    load_dotenv()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = AppConfig(**yaml.safe_load(f))

    json_path = OUTPUT_DIR / f"{date}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"找不到 {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    events = data.get("events", [])

    need_summary = [
        (i, d) for i, d in enumerate(events)
        if d.get("source") == source and not d.get("ai_summary")
    ]

    if not need_summary:
        logger.info(f"無需補充：{source} / {date} 已全有摘要")
        return 0

    logger.info(f"補充摘要：{source} / {date}，共 {len(need_summary)} 筆")
    llm = LLMGatewayClient(config.ai)
    step = SummarizeStep(llm, config.ai)

    updated = 0
    for i, d in need_summary:
        # 沒有內文先爬
        if not (d.get("body") or "").strip():
            logger.info(f"抓取內文：{d['url']}")
            fetched = _fetch_body(d["url"])
            if fetched:
                events[i]["body"] = fetched
                d = events[i]
            else:
                logger.warning(f"抓取失敗，略過：{d['url']}")
                continue

        event = _dict_to_event(d)
        result = step.apply(event)
        if result.ai_summary:
            events[i]["ai_summary"] = result.ai_summary
            updated += 1

    if updated:
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        generate_site(OUTPUT_DIR, site_root=PROJECT_ROOT)
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
    parser.add_argument("source", choices=["github", "news", "paper", "finance"], help="來源類別")
    args = parser.parse_args()
    count = retry_summary(args.date, args.source)
    print(f"更新 {count} 筆")


if __name__ == "__main__":
    cli()
