"""論文收集器 - arXiv（LLM 篩選）+ Hugging Face Daily Papers（社群 upvotes）。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import arxiv
import httpx

from finance_scraper.domain import PaperConfig, RawPaperEvent, SourceType

if TYPE_CHECKING:
    from finance_scraper.interfaces import LLMGateway

logger = logging.getLogger(__name__)

_HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"

_CURATE_SYSTEM = "你是一位 AI/ML 領域的研究員，擅長判斷論文的學術價值與實務影響力。"

_CURATE_PROMPT_TMPL = """\
以下是今天 arXiv 的新論文（共 {total} 篇），請選出其中最具突破性、最值得關注的 {top_n} 篇。
判斷標準：方法創新、實驗結果顯著、對產業有實際影響，或解決長期未解的問題。

請只輸出一個 JSON 陣列，內含選中論文的 arxiv_id（例如 "2501.12345"），不需要其他說明。
格式範例：["2501.00001", "2501.00002"]

論文清單：
{papers}"""


class PaperCollector:
    source_type = SourceType.PAPER

    def __init__(
        self,
        config: PaperConfig,
        lookback_days: int = 1,
        llm: LLMGateway | None = None,
    ):
        self.config = config
        self.lookback_days = lookback_days
        self.llm = llm

    def collect(self) -> list[RawPaperEvent]:
        # arXiv：需要 LLM 篩 top_n，沒有 LLM 時整段跳過（避免回傳上百筆未過濾論文當噪音）
        arxiv_papers: list[RawPaperEvent] = []
        if self.llm:
            try:
                arxiv_papers = self._fetch_arxiv()
                logger.info(f"arXiv 抓取：{len(arxiv_papers)} 筆")
            except Exception as e:
                logger.error(f"arXiv 抓取失敗：{e}")
                arxiv_papers = []

            if self.config.arxiv_top_n > 0 and len(arxiv_papers) > self.config.arxiv_top_n:
                arxiv_papers = self._curate(arxiv_papers)
        else:
            logger.info("LLM gateway 不可用，跳過 arXiv 抓取（HF Daily Papers 仍會收集）")

        # HF Daily Papers：按 upvotes 排序取 top
        hf_papers: list[RawPaperEvent] = []
        if self.config.hf_papers_enabled and self.config.hf_top_n > 0:
            try:
                hf_papers = self._fetch_hf_papers()
                logger.info(f"HF Daily Papers 抓取：{len(hf_papers)} 筆")
            except Exception as e:
                logger.error(f"HF Daily Papers 抓取失敗：{e}")

        # 合併去重：以 arxiv_id（去版本號）為 key，arXiv 篩選結果優先
        combined: dict[str, RawPaperEvent] = {}
        for p in arxiv_papers + hf_papers:
            key = (p.arxiv_id or p.url).split("v")[0]
            if key not in combined:
                combined[key] = p

        result = list(combined.values())
        logger.info(f"Papers 收集完成（合併去重後）：{len(result)} 筆（arXiv {len(arxiv_papers)} + HF {len(hf_papers)}）")
        return result

    def _fetch_arxiv(self) -> list[RawPaperEvent]:
        """單一 OR 查詢取得所有類別的今日論文，依 arxiv_id 去重。"""
        cat_query = " OR ".join(f"cat:{c}" for c in self.config.arxiv_categories)
        query = cat_query
        if self.config.arxiv_keywords:
            kw_query = " OR ".join(f'abs:"{kw}"' for kw in self.config.arxiv_keywords)
            query = f"({cat_query}) AND ({kw_query})"

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=self.config.arxiv_fetch_limit,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        seen: set[str] = set()
        events: list[RawPaperEvent] = []

        for result in client.results(search):
            if result.published.replace(tzinfo=timezone.utc) < cutoff:
                break
            arxiv_id = result.entry_id.split("/")[-1] if result.entry_id else ""
            if arxiv_id in seen:
                continue
            seen.add(arxiv_id)
            events.append(RawPaperEvent(
                title=result.title.replace("\n", " ").strip(),
                url=result.entry_id,
                created_at=result.published.replace(tzinfo=timezone.utc),
                body=result.summary.replace("\n", " ").strip() if result.summary else None,
                body_lang="en",  # arXiv 摘要一律英文
                authors=[a.name for a in result.authors[:5]],
                categories=list(result.categories),
                arxiv_id=arxiv_id,
            ))

        return events

    def _fetch_hf_papers(self) -> list[RawPaperEvent]:
        """從 Hugging Face Daily Papers 取 upvotes 排名前 N 篇。

        不套 lookback_days 過濾：daily_papers endpoint 本身已是策展過的當日精選，
        而 publishedAt 是論文的 arXiv 發表日（常落後策展日數天），拿來當 cutoff 會把整批濾掉。
        """
        r = httpx.get(_HF_DAILY_PAPERS_URL, timeout=15)
        r.raise_for_status()
        items = r.json()

        events: list[RawPaperEvent] = []
        for item in items:
            paper = item.get("paper") or {}
            arxiv_id = (paper.get("id") or "").strip()
            if not arxiv_id:
                continue

            published_str = paper.get("publishedAt") or item.get("publishedAt")
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                published = datetime.now(timezone.utc)

            authors = [a.get("name", "") for a in paper.get("authors", [])[:5] if a.get("name")]
            events.append(RawPaperEvent(
                title=(paper.get("title") or item.get("title") or "").strip(),
                url=f"https://arxiv.org/abs/{arxiv_id}",
                created_at=published.astimezone(timezone.utc),
                body=(paper.get("summary") or item.get("summary") or "").strip() or None,
                body_lang="en",  # HF Daily Papers 摘要也是英文
                authors=authors,
                categories=["HF Daily"],
                arxiv_id=arxiv_id,
                score=paper.get("upvotes"),
            ))

        # 按 upvotes 排序取 top_n
        events.sort(key=lambda p: p.score or 0, reverse=True)
        return events[: self.config.hf_top_n]

    def _curate(self, papers: list[RawPaperEvent]) -> list[RawPaperEvent]:
        """把全部論文標題+摘要送給 LLM，請它挑出最重要的 top_n 篇。"""
        lines = []
        for i, p in enumerate(papers, 1):
            abstract = (p.body or "")[:800]
            lines.append(f"{i}. [{p.arxiv_id}] {p.title}\n   摘要：{abstract}")

        prompt = _CURATE_PROMPT_TMPL.format(
            total=len(papers),
            top_n=self.config.arxiv_top_n,
            papers="\n\n".join(lines),
        )

        try:
            raw = self.llm.chat(
                user_prompt=prompt,
                max_tokens=200,
                system_prompt=_CURATE_SYSTEM,
                temperature=0.1,
            )
            selected_ids: list[str] = json.loads(raw.strip())
            # 去除版本號後綴（LLM 可能回傳 "2501.12345v1" → "2501.12345"）
            id_set = {aid.split("v")[0] for aid in selected_ids}
            curated = [p for p in papers if p.arxiv_id.split("v")[0] in id_set]
            if not curated:
                raise ValueError(f"LLM 回傳 ID 與抓到的論文無法對應：{selected_ids[:3]}")
            # 依 LLM 回傳的順序排
            id_order = {aid.split("v")[0]: i for i, aid in enumerate(selected_ids)}
            curated.sort(key=lambda p: id_order.get(p.arxiv_id.split("v")[0], 999))
            logger.info(f"LLM 篩選完成：{len(curated)}/{len(papers)} 篇入選")
            return curated
        except Exception as e:
            logger.warning(f"LLM curation 失敗，回傳日期排序前 {self.config.arxiv_top_n} 篇：{e}")
            return papers[: self.config.arxiv_top_n]
