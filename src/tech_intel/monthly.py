"""Monthly trending pipeline — 收集本月 AI 快速竄升 repo。

只需要 GITHUB_TOKEN，不依賴 LLM。輸出寫入 PG (trending_runs / trending_repos)。
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from dotenv import load_dotenv

from tech_intel.sources.github.trending import GitHubTrendingCollector
from tech_intel.storage import init_schema, trending

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monthly")


async def run_monthly() -> None:
    load_dotenv()
    token = os.environ["GITHUB_TOKEN"]
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", 180))

    await init_schema()

    collector = GitHubTrendingCollector(token, lookback_days=lookback_days, top_n=50)
    # collect() 內部用 PyGithub 同步 I/O；丟到 thread executor 避免卡 event loop
    repos = await asyncio.to_thread(collector.collect)

    month_str = date.today().strftime("%Y-%m")
    await trending.upsert_run(month_str, lookback_days, [r.to_dict() for r in repos])
    logger.info(f"Monthly trending 寫入 PG：{month_str}（{len(repos)} 個 repo）")
    logger.info("✅ Monthly trending 完成")


def cli() -> None:
    asyncio.run(run_monthly())


if __name__ == "__main__":
    cli()
