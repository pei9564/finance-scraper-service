"""Monthly trending pipeline — 收集本月 AI 快速竄升 repo。

只需要 GITHUB_TOKEN，不依賴 LLM。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from tech_intel.outputs.site_generator import generate_site
from tech_intel.sources.github.trending import GitHubTrendingCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monthly")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TRENDING_DIR = PROJECT_ROOT / "output" / "collections" / "trending-repos"
DAILY_DIR = PROJECT_ROOT / "output" / "weekly"


def run_monthly() -> None:
    load_dotenv()
    token = os.environ["GITHUB_TOKEN"]
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", 180))

    TRENDING_DIR.mkdir(parents=True, exist_ok=True)

    collector = GitHubTrendingCollector(token, lookback_days=lookback_days, top_n=50)
    repos = collector.collect()

    month_str = date.today().strftime("%Y-%m")
    output_path = TRENDING_DIR / f"{month_str}.json"
    data = {
        "month": month_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "count": len(repos),
        "repos": [r.to_dict() for r in repos],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Monthly output 寫入：{output_path}")

    generate_site(DAILY_DIR, site_root=PROJECT_ROOT)
    logger.info("✅ Monthly trending 完成")


def cli() -> None:
    run_monthly()


if __name__ == "__main__":
    cli()
