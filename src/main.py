"""
GitHub Collector - 主程式
執行完整 pipeline：收集 → 過濾 → 分類 → 摘要 → 輸出
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

# 確保 src/ 在 path 中
sys.path.insert(0, str(Path(__file__).parent))

from classifier import classify_all
from collector import GitHubCollector
from filter import filter_events
from models import AppConfig, Secrets, SourceType, WeeklyReport
from news_collector import NewsCollector
from notion_writer import NotionWriter
from paper_collector import PaperCollector
from site_generator import generate_site, prune_old
from summarizer import Summarizer
from telegram_sender import TelegramSender

# ---------------------------------------------------------------------------
# 日誌設定
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# 設定載入
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 輸出 JSON artifact
# ---------------------------------------------------------------------------

def write_json_output(
    output_dir: Path, events: list, daily_summary: str, day_str: str
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{day_str}.json"

    events_data = [
        {
            "source": e.source_type.value,
            "repo": e.repo_full_name,
            "type": e.event_type.value,
            "classification": e.classification,
            "title": e.title,
            "url": e.url,
            "created_at": e.created_at.isoformat(),
            "impact_level": e.impact_level.value,
            "ai_summary": e.ai_summary,
            "tags": e.tags,
            "migration_steps": e.migration_steps,
            # source-specific display fields
            "feed_name": e.feed_name,
            "score": e.score,
            "authors": e.authors,
            "categories": e.categories,
            "arxiv_id": e.arxiv_id,
        }
        for e in events
    ]

    data = {
        "date": day_str,
        "daily_summary": daily_summary,
        "events": events_data,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"JSON artifact 寫入：{output_path}")
    return output_path


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run_pipeline() -> None:
    load_dotenv()

    # 設定
    config_path = Path(__file__).parent.parent / "config" / "repos.yaml"
    output_dir = Path(__file__).parent.parent / "output" / "weekly"
    CST = timezone(timedelta(hours=8))
    day_str = datetime.now(CST).strftime("%Y-%m-%d")

    config = load_config(config_path)

    # 允許從環境變數覆蓋 lookback_days（GitHub Actions workflow_dispatch 用）
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", config.filters.lookback_days))
    config.filters.lookback_days = lookback_days

    secrets = load_secrets()

    # 初始化各模組
    github_collector = GitHubCollector(secrets.github_token, lookback_days)
    news_collector = NewsCollector(config.news, lookback_days)
    paper_collector = PaperCollector(config.papers, lookback_days)
    summarizer = Summarizer(secrets.google_api_key, config.ai, secrets.github_token)
    notion_writer = NotionWriter(secrets.notion_key, secrets.notion_db_ids)
    telegram = TelegramSender(secrets.telegram_token, secrets.telegram_chat_id)

    # ------------------------------------------------------------------
    # Stage 1: 收集（三個來源）
    # ------------------------------------------------------------------
    all_raw_events: list = []

    # 1a. GitHub
    try:
        github_events = github_collector.collect_all(config)
        all_raw_events.extend(github_events)
        logger.info(f"GitHub 收集：{len(github_events)} 筆")
    except Exception as e:
        logger.error(f"GitHub 收集失敗：{e}")
        await _notify_error(telegram, "GitHub 收集", str(e))

    # 1b. News
    try:
        news_events = news_collector.collect_all()
        all_raw_events.extend(news_events)
        logger.info(f"News 收集：{len(news_events)} 筆")
    except Exception as e:
        logger.error(f"News 收集失敗：{e}")
        await _notify_error(telegram, "News 收集", str(e))

    # 1c. Papers
    try:
        paper_events = paper_collector.collect_all()
        all_raw_events.extend(paper_events)
        logger.info(f"Papers 收集：{len(paper_events)} 筆")
    except Exception as e:
        logger.error(f"Papers 收集失敗：{e}")
        await _notify_error(telegram, "Papers 收集", str(e))

    raw_events = all_raw_events
    logger.info(f"Stage 1 完成：共收集到 {len(raw_events)} 筆原始事件")

    if not raw_events:
        await telegram.send_text("⚠️ 本週未收集到任何事件，流程結束。")
        return

    # ------------------------------------------------------------------
    # Stage 2: 過濾
    # ------------------------------------------------------------------
    filtered_events = raw_events
    try:
        filtered_events = filter_events(raw_events, config.filters)
        logger.info(f"Stage 2 完成：過濾後 {len(filtered_events)} 筆事件")
    except Exception as e:
        logger.error(f"Stage 2 過濾失敗，使用原始事件：{e}")

    # ------------------------------------------------------------------
    # Stage 3: 分類
    # ------------------------------------------------------------------
    classified_events = []
    try:
        classified_events = classify_all(filtered_events)
        logger.info(f"Stage 3 完成：分類完成")
    except Exception as e:
        logger.error(f"Stage 3 分類失敗：{e}")
        await _notify_error(telegram, "分類", str(e))
        return

    # ------------------------------------------------------------------
    # Stage 4: 日報摘要（單次 AI 呼叫）
    # ------------------------------------------------------------------
    summarized_events = summarizer.to_summarized(classified_events)
    daily_summary = ""
    try:
        daily_summary = summarizer.summarize_daily(classified_events)
        logger.info("Stage 4 完成：日報摘要產生")
    except Exception as e:
        logger.error(f"Stage 4 摘要失敗：{e}")
        await _notify_error(telegram, "AI 摘要", str(e))

    # ------------------------------------------------------------------
    # Stage 5a: 寫入 Notion（失敗不中斷）
    # ------------------------------------------------------------------
    try:
        notion_writer.write_events(summarized_events)
        logger.info("Stage 5a 完成：Notion 寫入成功")
    except Exception as e:
        logger.error(f"Stage 5a Notion 寫入失敗：{e}")
        await _notify_error(telegram, "Notion 寫入", str(e))

    # ------------------------------------------------------------------
    # Stage 5b: 發送 Telegram 日報（失敗不中斷）
    # ------------------------------------------------------------------
    try:
        await telegram.send_daily_report(summarized_events, daily_summary)
        logger.info("Stage 5b 完成：Telegram 日報發送成功")
    except Exception as e:
        logger.error(f"Stage 5b Telegram 發送失敗：{e}")

    # ------------------------------------------------------------------
    # Stage 6: 寫入 JSON + 產生靜態網頁（無論如何都執行）
    # ------------------------------------------------------------------
    try:
        write_json_output(output_dir, summarized_events, daily_summary, day_str)
        prune_old(output_dir, keep_days=30)
        generate_site(output_dir)
    except Exception as e:
        logger.error(f"Stage 6 輸出失敗：{e}")

    logger.info("✅ 流程全部完成")


async def _notify_error(telegram: TelegramSender, stage: str, error: str) -> None:
    try:
        await telegram.send_text(f"❌ GitHub Collector 錯誤\n階段：{stage}\n原因：{error[:200]}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(run_pipeline())
