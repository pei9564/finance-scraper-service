"""GitHub Releases pipeline — 收集追蹤 repo 的 release、為新項目補 LLM 摘要、寫 PG。

特性:
- 共用 config.repos(跟 daily pipeline 同一份追蹤清單)
- 只對 storage 尚未存在的 uid 跑 LLM 摘要 → 重跑省 cost
- LLM 不可用時繼續存,ai_summary 留 None,日後可重跑(同 retry 概念)
- CLI: finance-scraper-releases [--lookback 180]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from finance_scraper.domain import AppConfig
from finance_scraper.infrastructure import LLMGatewayClient
from finance_scraper.sources.github.release_collector import GitHubReleaseCollector
from finance_scraper.storage import init_schema, releases as releases_store

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "repos.yaml"

_DEFAULT_INSTRUCTION = (
    "請用繁體中文,以大約 150 字摘要以下 GitHub release notes 的重點,"
    "聚焦在「這版改了什麼」、是否有破壞性更新、對使用者的影響。"
)


def _summarize_release(llm: LLMGatewayClient, profile_max_tokens: int, instruction: str,
                       item: dict) -> str | None:
    body = (item.get("body") or "").strip()
    if not body:
        return None
    head = (
        f"Repo:{item['repo']}\n"
        f"版本:{item['tag']}\n"
        f"標題:{item['name']}\n"
        f"Release notes:\n{body[:4000]}"
    )
    try:
        return llm.chat(f"{instruction}\n\n{head}", max_tokens=profile_max_tokens).strip()
    except Exception as e:
        logger.warning(f"release 摘要失敗({item['url']}):{e}")
        return None


async def run_releases(lookback_days: int = 180) -> int:
    """收集 + 摘要 + UPSERT。回傳寫入筆數。"""
    load_dotenv()
    token = os.environ["GITHUB_TOKEN"]

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = AppConfig(**yaml.safe_load(f))

    await init_schema()

    collector = GitHubReleaseCollector(token, cfg.repos, lookback_days=lookback_days)
    fetched = await asyncio.to_thread(collector.collect)
    if not fetched:
        logger.info("沒有收集到任何 release")
        return 0

    existing = await releases_store.list_existing_uids()
    new_items = [it for it in fetched if it["uid"] not in existing]
    logger.info(f"收集 {len(fetched)} 筆 release;{len(new_items)} 筆為新增,需摘要")

    # 為新增 release 跑 LLM 摘要(LLM 不可用就跳過,保留原文)
    if new_items:
        try:
            llm = LLMGatewayClient(cfg.ai)
            release_profile = cfg.ai.summary_profiles.get("release")
            max_tokens = release_profile.max_tokens if release_profile else 400
            instruction = release_profile.instruction.strip() if release_profile else _DEFAULT_INSTRUCTION
            for item in new_items:
                summary = await asyncio.to_thread(
                    _summarize_release, llm, max_tokens, instruction, item,
                )
                if summary:
                    item["ai_summary"] = summary
        except Exception as e:
            logger.warning(f"LLM gateway 初始化失敗,跳過摘要:{e}")

    written = await releases_store.upsert_many(fetched)
    logger.info(f"✅ release 寫入 PG:{written} 筆(其中 {len(new_items)} 新增)")
    return written


def cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="收集追蹤 repo 的 GitHub releases")
    parser.add_argument("--lookback", type=int, default=180, help="抓幾天內的 release(預設 180)")
    args = parser.parse_args()
    asyncio.run(run_releases(args.lookback))


if __name__ == "__main__":
    cli()
