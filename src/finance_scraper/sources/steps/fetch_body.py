"""FetchBodyStep - 在摘要前抓取文章內文寫入 event.body。

部分來源(例如 HN Algolia API)只回標題與 URL,沒有 body,SummarizeStep 因
無內文會跳過。本步驟用 trafilatura 抓正文補上去,讓後續摘要可正常進行。
"""
from __future__ import annotations

import logging

from finance_scraper.domain import ClassifiedEvent

logger = logging.getLogger(__name__)


def fetch_article_text(url: str, timeout: float = 15.0, min_length: int = 100) -> str | None:
    """從 URL 抓取文章內文;失敗或內容過短回傳 None。"""
    try:
        import httpx
        import trafilatura
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TechIntelBot/1.0)"}
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=timeout)
        r.raise_for_status()
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False)
        return text if text and len(text) >= min_length else None
    except Exception as e:
        logger.debug(f"抓取內文失敗 {url}：{e}")
        return None


class FetchBodyStep:
    name = "fetch_body"

    def apply(self, event: ClassifiedEvent) -> ClassifiedEvent:
        if (event.body or "").strip():
            return event
        if not event.url:
            return event

        text = fetch_article_text(event.url)
        if not text:
            logger.info(f"fetch_body 跳過(抓不到內文):{event.url}")
            return event

        logger.info(f"fetch_body 成功({len(text)} 字):{event.url}")
        # body_lang 沿用既有值;若還是 null(HN 沒帶 lang)預設 'en',
        # 後續走 translate-day 才會被處理
        updates: dict = {"body": text}
        if not event.body_lang:
            updates["body_lang"] = "en"
        return event.model_copy(update=updates)
