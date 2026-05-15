"""收藏的月度 LLM 回顧 — 把當月所有收藏壓成一段繁中文字摘要。

呼叫端負責：
1. 從 storage.bookmarks.list_by_month 拿到當月項目
2. 呼叫 BookmarkDigester(llm).digest(month, items) → str
3. 把結果與項目數一起存進 storage.digests.set(...)，避免重複呼叫 vLLM

成本上限：MAX_ITEMS = 100，超出時只摘要最新 100 筆（已依 bookmarked_at 新→舊排序）。
"""
from __future__ import annotations

import logging
from typing import Any

from tech_intel.interfaces import LLMGateway

logger = logging.getLogger(__name__)

MAX_ITEMS = 100

SOURCE_LABELS_TC = {
    "github": "🔔 GitHub",
    "news": "📰 網路新聞",
    "paper": "📄 論文",
    "finance": "💰 財經",
}


class BookmarkDigester:
    def __init__(self, llm: LLMGateway):
        self.llm = llm

    def digest(self, month: str, items: list[dict[str, Any]]) -> str:
        if not items:
            return f"{month} 尚無收藏。"

        capped = items[:MAX_ITEMS]
        truncated_note = (
            f"（本月共 {len(items)} 筆，僅摘要最近 {MAX_ITEMS} 筆）\n\n"
            if len(items) > MAX_ITEMS else ""
        )

        groups: dict[str, list[dict]] = {}
        for it in capped:
            groups.setdefault(it.get("source") or "other", []).append(it)

        sections = []
        for src in ["github", "news", "paper", "finance", "other"]:
            if src not in groups:
                continue
            label = SOURCE_LABELS_TC.get(src, src)
            blocks = "\n\n".join(self._build_block(it) for it in groups[src])
            sections.append(f"{label}：\n{blocks}")
        all_blocks = "\n\n".join(sections)

        prompt = f"""請根據以下使用者本月（{month}）收藏的內容，產生一份「本月關注主題回顧」。

規則：
- 全程使用繁體中文
- 不要有開場白、問候語、結語，直接從內容開始
- 依來源分區塊：🔔 GitHub、📰 網路新聞、📄 論文、💰 財經（沒有的區塊就不要寫）
- 每個區塊先用一句話總結這位使用者該來源的關注主題，再列 3-5 條重點，每條 40 字以內
- 不要逐則重述，要有歸納感
- 純文字，不要任何 markdown 符號

{truncated_note}{all_blocks}"""

        return self.llm.chat(prompt, max_tokens=2048)

    def _build_block(self, it: dict[str, Any]) -> str:
        origin = it.get("origin") or ""
        cls = it.get("classification") or ""
        head = f"[{origin}] {it.get('title', '')}"
        if cls:
            head = f"[{cls}] {head}"
        body = (it.get("ai_summary") or it.get("body") or "")[:300]
        return f"{head}\n  {body}" if body else head
