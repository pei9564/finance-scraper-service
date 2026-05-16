"""Pipeline orchestrator — 串接收集 → 過濾 → 分類 → 逐則處理 → 日報 → 輸出。

只依賴 interfaces 與純 processing 函式；具體的 collector / step / output / LLM
client 全由 main.py 透過 registry 注入。
"""
from __future__ import annotations

import logging

from finance_scraper.domain import ClassifiedEvent, FilterConfig, RawEvent, SummarizedEvent
from finance_scraper.interfaces import OutputWriter
from finance_scraper.processing import DailySummarizer, classify_all, filter_events
from finance_scraper.sources import SourceUnit

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        source_units: list[SourceUnit],
        output_writers: list[OutputWriter],
        filter_config: FilterConfig,
        daily_summarizer: DailySummarizer,
    ):
        self.source_units = source_units
        self.output_writers = output_writers
        self.filter_config = filter_config
        self.daily_summarizer = daily_summarizer
        self._steps_by_source = {u.source_type: u.steps for u in source_units}

    async def run(self, day_str: str) -> None:
        raw_events = self._collect()
        logger.info(f"Stage 1 完成：共收集到 {len(raw_events)} 筆原始事件")
        if not raw_events:
            logger.warning("未收集到任何事件，流程結束。")
            return

        filtered = self._filter(raw_events)
        classified = self._classify(filtered)
        if not classified:
            return

        summarized = self._process_per_source(classified)
        daily_summary = self._summarize_daily(classified)
        await self._write_outputs(summarized, daily_summary, day_str)
        logger.info("✅ 流程全部完成")

    # ------------------------------------------------------------------
    # Stage 1: 收集（逐來源錯誤隔離）
    # ------------------------------------------------------------------

    def _collect(self) -> list[RawEvent]:
        all_raw: list[RawEvent] = []
        for unit in self.source_units:
            try:
                events = unit.collector.collect()
                all_raw.extend(events)
                logger.info(f"{unit.source_type.value} 收集：{len(events)} 筆")
            except Exception as e:
                logger.error(f"{unit.source_type.value} 收集失敗：{e}")
        return all_raw

    # ------------------------------------------------------------------
    # Stage 2: 過濾（失敗則退回原始事件）
    # ------------------------------------------------------------------

    def _filter(self, raw_events: list[RawEvent]) -> list[RawEvent]:
        try:
            filtered = filter_events(raw_events, self.filter_config)
            logger.info(f"Stage 2 完成：過濾後 {len(filtered)} 筆事件")
            return filtered
        except Exception as e:
            logger.error(f"Stage 2 過濾失敗，使用原始事件：{e}")
            return raw_events

    # ------------------------------------------------------------------
    # Stage 3: 分類（失敗則中止流程）
    # ------------------------------------------------------------------

    def _classify(self, events: list[RawEvent]) -> list[ClassifiedEvent]:
        try:
            classified = classify_all(events)
            logger.info("Stage 3 完成：分類完成")
            return classified
        except Exception as e:
            logger.error(f"Stage 3 分類失敗：{e}")
            return []

    # ------------------------------------------------------------------
    # Stage 4: 逐來源處理鏈
    # ------------------------------------------------------------------

    def _process_per_source(self, classified: list[ClassifiedEvent]) -> list[SummarizedEvent]:
        result: list[SummarizedEvent] = []
        for event in classified:
            summarized: ClassifiedEvent = SummarizedEvent(**event.model_dump())
            for step in self._steps_by_source.get(event.source_type, []):
                try:
                    summarized = step.apply(summarized)
                except Exception as e:
                    logger.error(f"步驟 '{step.name}' 失敗（{event.url}）：{e}")
            result.append(
                summarized if isinstance(summarized, SummarizedEvent)
                else SummarizedEvent(**summarized.model_dump())
            )
        logger.info("Stage 4 完成：逐來源處理鏈執行完畢")
        return result

    # ------------------------------------------------------------------
    # Stage 5: 跨來源日報摘要（吃 classified，與重構前行為一致）
    # ------------------------------------------------------------------

    def _summarize_daily(self, classified: list[ClassifiedEvent]) -> str:
        try:
            summary = self.daily_summarizer.summarize(classified)
            logger.info("Stage 5 完成：日報摘要產生")
            return summary
        except Exception as e:
            logger.error(f"Stage 5 摘要失敗：{e}")
            return ""

    # ------------------------------------------------------------------
    # Stage 6: 輸出（逐輸出錯誤隔離）
    # ------------------------------------------------------------------

    async def _write_outputs(
        self,
        events: list[SummarizedEvent],
        daily_summary: str,
        day_str: str,
    ) -> None:
        for writer in self.output_writers:
            try:
                await writer.write(events, daily_summary, day_str)
                logger.info(f"輸出 '{writer.name}' 完成")
            except Exception as e:
                logger.error(f"輸出 '{writer.name}' 失敗：{e}")
