"""Finance Scraper — 進入點：載入設定、組裝 registry、執行 pipeline。"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from finance_scraper.domain import AppConfig, Secrets
from finance_scraper.infrastructure import LLMGatewayClient
from finance_scraper.outputs import build_output_writers
from finance_scraper.pipeline import Pipeline
from finance_scraper.processing import DailySummarizer
from finance_scraper.sources import build_source_units

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "repos.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output" / "weekly"


def load_config(config_path: Path) -> AppConfig:
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    config = AppConfig(**raw)
    logger.info(f"載入 {len(config.repos)} 個追蹤 repo")
    return config


def load_secrets() -> Secrets:
    try:
        secrets = Secrets.from_env()
        logger.info("Secrets 載入成功")
        return secrets
    except (KeyError, ValueError) as e:
        logger.error(f"Secrets 載入失敗：{e}")
        raise


async def run_pipeline() -> None:
    load_dotenv()

    config = load_config(CONFIG_PATH)
    secrets = load_secrets()

    # 允許從環境變數覆蓋 lookback_days（GitHub Actions workflow_dispatch 用）
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", config.filters.lookback_days))
    config.filters.lookback_days = lookback_days

    CST = timezone(timedelta(hours=8))
    day_str = os.environ.get("RUN_DATE") or datetime.now(CST).strftime("%Y-%m-%d")

    raw_llm = LLMGatewayClient(config.ai)
    llm = raw_llm if raw_llm.health() else None
    if llm is None:
        logger.warning("LLM gateway 不可用 — 依賴 LLM 的步驟（arxiv/逐則摘要/日報摘要）會自動降級")

    pipeline = Pipeline(
        source_units=build_source_units(config, secrets, llm, lookback_days),
        output_writers=build_output_writers(config, secrets, OUTPUT_DIR),
        filter_config=config.filters,
        daily_summarizer=DailySummarizer(llm),
    )
    await pipeline.run(day_str)


def cli() -> None:
    asyncio.run(run_pipeline())


if __name__ == "__main__":
    cli()
