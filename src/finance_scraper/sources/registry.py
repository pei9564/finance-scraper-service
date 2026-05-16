"""來源與步驟的 registry — 把 config 的名稱對應到實例化的物件。

新增來源 = 一個 COLLECTOR_FACTORIES 條目 + repos.yaml 的一筆 sources 設定。
新增步驟 = 一個 ProcessingStep 類別 + 一筆 STEP_FACTORIES 條目。
orchestrator 不需更動。enabled 旗標在此解析，orchestrator 只看得到啟用的單元。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from finance_scraper.domain import AppConfig, Secrets, SourceType
from finance_scraper.interfaces import LLMGateway, ProcessingStep, SourceCollector

from .base import SourceUnit
from .finance import FinanceCollector
from .github import GitHubCollector
from .news import NewsCollector
from .paper import PaperCollector
from .steps import FetchBodyStep, SummarizeStep, TranslateStep

logger = logging.getLogger(__name__)


@dataclass
class BuildDeps:
    config: AppConfig
    secrets: Secrets
    llm: LLMGateway | None  # None 代表 gateway 不可用，依賴 LLM 的步驟會自行降級
    lookback: int


COLLECTOR_FACTORIES: dict[str, Callable[[BuildDeps], SourceCollector]] = {
    "github": lambda d: GitHubCollector(d.secrets.github_token, d.config.repos, d.lookback),
    "news": lambda d: NewsCollector(d.config.news, d.lookback),
    "paper": lambda d: PaperCollector(d.config.papers, d.lookback, d.llm),
    "finance": lambda d: FinanceCollector(d.config.finance, d.lookback),
}

def _non_en_feed_names(config: AppConfig) -> set[str]:
    """匯整所有非英文 RSS 來源的 feed_name,供 TranslateStep 跳過用。"""
    feeds = [*config.news.rss_feeds, *config.finance.rss_feeds]
    return {f.name for f in feeds if f.lang != "en"}


STEP_FACTORIES: dict[str, Callable[[BuildDeps], ProcessingStep]] = {
    "fetch_body": lambda d: FetchBodyStep(),
    "summarize": lambda d: SummarizeStep(d.llm, d.config.ai),
    "translate": lambda d: TranslateStep(d.llm, _non_en_feed_names(d.config)),
}


def build_source_units(
    config: AppConfig,
    secrets: Secrets,
    llm: LLMGateway | None,
    lookback: int,
) -> list[SourceUnit]:
    deps = BuildDeps(config=config, secrets=secrets, llm=llm, lookback=lookback)
    units: list[SourceUnit] = []

    for name, source_config in config.sources.items():
        if not source_config.enabled:
            logger.info(f"來源 '{name}' 已停用，略過")
            continue
        collector_factory = COLLECTOR_FACTORIES.get(name)
        if collector_factory is None:
            logger.warning(f"未知來源 '{name}'，略過")
            continue

        steps: list[ProcessingStep] = []
        for step_name in source_config.steps:
            step_factory = STEP_FACTORIES.get(step_name)
            if step_factory is None:
                logger.warning(f"來源 '{name}' 引用未知步驟 '{step_name}'，略過")
                continue
            steps.append(step_factory(deps))

        units.append(SourceUnit(
            source_type=SourceType(name),
            collector=collector_factory(deps),
            steps=steps,
        ))
        logger.info(f"來源 '{name}' 已啟用，步驟：{[s.name for s in steps]}")

    return units
