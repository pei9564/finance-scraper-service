"""財經新聞收集器 — RSS only。

重用 NewsCollector 的 _fetch_rss / _parse_entry_date；不使用 HackerNews。
事件以 RawNewsEvent 承載並覆寫 source_type=FINANCE，避免新增一個幾乎相同的型別。
"""
from __future__ import annotations

import logging

from tech_intel.domain import FinanceConfig, RawNewsEvent, SourceType
from tech_intel.sources.news.collector import NewsCollector

logger = logging.getLogger(__name__)


class FinanceCollector(NewsCollector):
    source_type = SourceType.FINANCE

    def __init__(self, config: FinanceConfig, lookback_days: int = 1):
        # FinanceConfig 與 NewsConfig 都暴露 rss_feeds，父類別只讀這個欄位
        self.config = config
        self.lookback_days = lookback_days

    def collect(self) -> list[RawNewsEvent]:
        events: list[RawNewsEvent] = []
        for feed_cfg in self.config.rss_feeds:
            try:
                events.extend(self._fetch_rss(feed_cfg))
            except Exception as e:
                logger.error(f"Finance RSS '{feed_cfg.name}' 收集失敗：{e}")
        for ev in events:
            ev.source_type = SourceType.FINANCE
        logger.info(f"Finance 收集完成：{len(events)} 筆")
        return events
