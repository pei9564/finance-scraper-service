"""統一資料流的 by-day 批次處理 — translate-day 與 summarize-day。

兩個函式都是「對某發佈日(TW)+ 可選 source/feed 篩選下的 events 跑一輪」:
  translate_day:  body_lang ≠ 'zh' 的 events → 翻譯 title + body → 設 body_lang='zh'
  summarize_day:  body_lang = 'zh' 且 ai_summary 空的 events → 產 ai_summary

兩者共享一份 progress dict(server 持有 ref,/api/status 即時讀)。
失敗策略:partial commit — 成功的逐筆寫回,失敗只記在 progress.failed,不擋後面。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from finance_scraper.domain import AIConfig, EventType, ImpactLevel, SourceType, SummarizedEvent
from finance_scraper.interfaces import LLMGateway
from finance_scraper.sources.steps import SummarizeStep
from finance_scraper.storage import daily

logger = logging.getLogger(__name__)


# 翻譯 prompt:title 用短指令,body 用較完整的指令保留數字/人名/結構
_TITLE_PROMPT = (
    "請把以下英文標題翻成繁體中文,只輸出譯文本身,不要加引號或解釋:\n\n"
)
_BODY_PROMPT = (
    "請把以下英文文章內文翻成繁體中文,保留原文的重要數字、人名、機構名稱與段落結構。"
    "只輸出譯文本身,不要加開場白、結語或 markdown 符號。\n\n"
)
# body 翻譯送 LLM 的硬上限 — 超過會被截斷
_BODY_TRUNC = 6000


def _translate_via_package(text: str) -> str | None:
    """LLM 不可用時 fallback。失敗回 None。"""
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source="auto", target="zh-TW").translate(text)
        return result.strip() if result else None
    except Exception as e:
        logger.debug(f"deep-translator 失敗:{e}")
        return None


def _translate_text(llm: LLMGateway | None, text: str, prompt: str, max_tokens: int) -> str | None:
    """單次翻譯;LLM 失敗或回空字串時 fallback Google。"""
    text = (text or "").strip()
    if not text:
        return None
    if llm is not None:
        try:
            result = llm.chat(prompt + text, max_tokens=max_tokens).strip()
            if result:
                return result
        except Exception as e:
            logger.warning(f"LLM 翻譯失敗,改 fallback:{e}")
    return _translate_via_package(text)


async def translate_day(
    pub_date: str,
    source: str | None,
    feed_name: str | None,
    llm: LLMGateway | None,
    progress: Optional[dict] = None,
) -> dict[str, int]:
    """把指定發佈日的待翻譯 events 翻成中文。

    pub_date 是事件實際發佈日(TW),不是 pipeline run date —— 跟 UI sidebar 一致。
    source=None 表整日所有 source;否則只跑該 source(+feed_name)。
    回傳 {total, updated, failed}。
    """
    events = await daily.list_events_needing_translation(pub_date, source, feed_name)
    total = len(events)
    if progress is not None:
        progress.update(total=total, done=0, updated=0, failed=0, current=None,
                        stage="translate")
    if not total:
        logger.info(f"無待翻譯事件:{pub_date} / {source or '*'} / {feed_name or '*'}")
        return {"total": 0, "updated": 0, "failed": 0}

    logger.info(f"翻譯 {total} 筆:{pub_date} / {source or '*'} / {feed_name or '*'}")
    updated = 0
    failed = 0
    for d in events:
        if progress is not None:
            progress["current"] = d.get("title") or d.get("url") or "?"
        title_old = d.get("title") or ""
        body_old = d.get("body") or ""
        # title 與 body 各送一次 LLM(LLMGateway.chat 是同步,丟 thread)
        title_new = await asyncio.to_thread(
            _translate_text, llm, title_old, _TITLE_PROMPT, 300,
        )
        body_new = await asyncio.to_thread(
            _translate_text, llm, body_old[:_BODY_TRUNC], _BODY_PROMPT, 4000,
        )
        # 只要其中一個拿到譯文就算成功(title 通常會,body 可能 fallback 也成功)
        if not title_new and not body_new:
            failed += 1
            logger.warning(f"翻譯全部失敗:{d.get('url')}")
        else:
            ok = await daily.update_event_translation(
                d["uid"],
                title_new or title_old,
                body_new or body_old,
            )
            if ok:
                updated += 1
            else:
                failed += 1
        if progress is not None:
            progress.update(done=progress.get("done", 0) + 1,
                            updated=updated, failed=failed)
    logger.info(f"翻譯完成:成功 {updated} / 失敗 {failed} / 共 {total}")
    return {"total": total, "updated": updated, "failed": failed}


def _dict_to_event(d: dict) -> SummarizedEvent:
    """list_events_by_pub_date 的 dict 還原成 SummarizedEvent 供 SummarizeStep 用。"""
    from datetime import datetime, timezone
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
        body_lang=d.get("body_lang"),
        tags=d.get("tags") or [],
        migration_steps=d.get("migration_steps") or [],
        feed_name=d.get("feed_name"),
        score=d.get("score"),
        authors=d.get("authors") or [],
        categories=d.get("categories") or [],
        arxiv_id=d.get("arxiv_id"),
    )


async def summarize_day(
    pub_date: str,
    source: str | None,
    feed_name: str | None,
    llm: LLMGateway | None,
    ai_config: AIConfig,
    progress: Optional[dict] = None,
) -> dict[str, int]:
    """把指定發佈日的「已翻譯但無摘要」events 補上摘要。

    強制要求 body_lang='zh' — 翻譯先行,prompt 才不必處理多語。
    """
    events = await daily.list_events_needing_summary(pub_date, source, feed_name)
    total = len(events)
    if progress is not None:
        progress.update(total=total, done=0, updated=0, failed=0, current=None,
                        stage="summarize")
    if not total:
        logger.info(f"無待摘要事件:{pub_date} / {source or '*'} / {feed_name or '*'}")
        return {"total": 0, "updated": 0, "failed": 0}

    logger.info(f"摘要 {total} 筆:{pub_date} / {source or '*'} / {feed_name or '*'}")
    step = SummarizeStep(llm, ai_config)
    updated = 0
    failed = 0
    for d in events:
        if progress is not None:
            progress["current"] = d.get("title") or d.get("url") or "?"
        old_summary = (d.get("ai_summary") or "").strip()
        event = _dict_to_event(d)
        result = await asyncio.to_thread(step.apply, event)
        new_summary = (result.ai_summary or "").strip()
        if new_summary and new_summary != old_summary:
            await daily.update_event_summary(d["uid"], new_summary, None)
            updated += 1
        else:
            failed += 1
            logger.warning(f"摘要失敗或無變化:{d.get('url')}")
        if progress is not None:
            progress.update(done=progress.get("done", 0) + 1,
                            updated=updated, failed=failed)
    logger.info(f"摘要完成:成功 {updated} / 失敗 {failed} / 共 {total}")
    return {"total": total, "updated": updated, "failed": failed}
