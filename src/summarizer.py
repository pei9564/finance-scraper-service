"""
AI 摘要器 - 使用 Google Gemini API 產生事件摘要
- Flash：一般 Release、Issue、Feature PR（快速省錢）
- Pro：Breaking Change、Security、PR diff 分析（精準）
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx
from google import genai
from google.genai import types as genai_types
from google.api_core.exceptions import ResourceExhausted, DeadlineExceeded, InternalServerError

from models import AIConfig, ClassifiedEvent, ImpactLevel, SummarizedEvent

logger = logging.getLogger(__name__)

# 需要 Pro 精細分析的分類
PRO_CLASSIFICATIONS = {"Breaking", "Security", "Release/Breaking"}

SYSTEM_PROMPT = "你是一位資深軟體工程師，專門為技術團隊整理 GitHub 動態。"


class Summarizer:
    def __init__(self, api_key: str, config: AIConfig, github_token: str = ""):
        self.client = genai.Client(api_key=api_key)
        self.config = config
        self.github_token = github_token

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def to_summarized(self, events: list[ClassifiedEvent]) -> list[SummarizedEvent]:
        """將 ClassifiedEvent 直接轉為 SummarizedEvent（不呼叫 AI）。"""
        return [self._fallback(e) for e in events]

    def summarize_daily(self, events: list[ClassifiedEvent]) -> str:
        """對所有事件產生一則日報摘要（單次 API 呼叫）。"""
        if not events:
            return "今日無新事件。"
        try:
            delays = [60, 120]
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    return self._call_daily_summary(events)
                except ResourceExhausted as e:
                    last_exc = e
                    if attempt < 2:
                        logger.warning(f"Rate limit，等待 {delays[attempt]}s 後重試...")
                        time.sleep(delays[attempt])
                except (DeadlineExceeded, InternalServerError) as e:
                    last_exc = e
                    if attempt < 2:
                        logger.warning(f"API 錯誤，等待 30s 後重試...")
                        time.sleep(30)
            logger.error(f"日報摘要重試耗盡：{last_exc}")
        except Exception as e:
            logger.error(f"日報摘要失敗：{e}")
        return self._fallback_daily(events)

    def _build_event_block(self, e: ClassifiedEvent) -> str:
        lines = [f"[{e.classification}] {e.repo_full_name}: {e.title}"]

        if e.event_type.value == "Release":
            if e.tag:
                lines.append(f"  版本：{e.tag}")
            if e.body:
                lines.append(f"  Release Notes：{e.body[:1500]}")
        else:
            if e.labels:
                lines.append(f"  Labels：{', '.join(e.labels)}")
            if e.comment_count or e.reactions:
                lines.append(f"  留言：{e.comment_count}，Reactions：{e.reactions}")
            if e.body:
                lines.append(f"  說明：{e.body[:500]}")

        return "\n".join(lines)

    def _call_daily_summary(self, events: list[ClassifiedEvent]) -> str:
        event_blocks = "\n\n".join(self._build_event_block(e) for e in events)
        prompt = f"""根據以下 GitHub 事件，直接輸出每日技術摘要。

規則：
- 全程使用繁體中文
- 不要有開場白、問候語、結語，直接從內容開始
- 若有 Breaking Change 或 Security 問題，放在最前面並加上 ⚠️
- 依 repo 分組，每個 repo 用 2-4 條重點說明
- Release 必須從 Release Notes 提取具體變更內容
- 每條重點控制在 40 字以內
- 純文字，不要任何 markdown 符號

事件：
{event_blocks}"""

        response = self.client.models.generate_content(
            model=self.config.flash_model,
            contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
            config=genai_types.GenerateContentConfig(max_output_tokens=8192),
        )
        finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
        logger.debug(f"日報摘要 finish_reason: {finish_reason}")
        if str(finish_reason) == "FinishReason.MAX_TOKENS":
            logger.warning("日報摘要被 MAX_TOKENS 截斷，考慮縮短 prompt 或提高 token 上限")
        return response.text.strip()

    def _fallback_daily(self, events: list[ClassifiedEvent]) -> str:
        lines = [f"📋 今日共 {len(events)} 筆事件："]
        for e in events:
            lines.append(f"• [{e.classification}] {e.repo_full_name}: {e.title}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _summarize_with_retry(self, event: ClassifiedEvent) -> SummarizedEvent:
        delays = [60, 120]
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                return self._summarize_one(event)
            except ResourceExhausted as e:
                last_exc = e
                if attempt < 2:
                    wait = delays[attempt]
                    logger.warning(f"Rate limit，等待 {wait}s 後重試...")
                    time.sleep(wait)
            except DeadlineExceeded as e:
                last_exc = e
                if attempt < 2:
                    logger.warning(f"API timeout，等待 10s 後重試...")
                    time.sleep(10)
            except InternalServerError as e:
                last_exc = e
                if attempt < 2:
                    logger.warning(f"API 5xx 錯誤，等待 30s 後重試...")
                    time.sleep(30)
                else:
                    break

        logger.error(f"重試耗盡，使用 fallback：{last_exc}")
        return self._fallback(event)

    def _summarize_one(self, event: ClassifiedEvent) -> SummarizedEvent:
        use_pro = event.classification in PRO_CLASSIFICATIONS
        model = self.config.pro_model if use_pro else self.config.flash_model

        if use_pro:
            prompt = self._build_pro_prompt(event)
        else:
            prompt = self._build_flash_prompt(event)

        response = self.client.models.generate_content(
            model=model,
            contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
            config={"max_output_tokens": self.config.max_summary_tokens * 3},
        )

        raw_text = response.text.strip()
        return self._parse_response(raw_text, event)

    def _build_flash_prompt(self, event: ClassifiedEvent) -> str:
        body_excerpt = (event.body or "")[:3000]
        return f"""請摘要這個 GitHub {event.event_type.value}（來自 {event.repo_full_name}）：

標題：{event.title}
分類：{event.classification}
內文：
{body_excerpt}

請輸出以下 JSON 格式（不要加任何其他文字）：
{{
  "summary": "2-3 句技術摘要，說明這個變更做了什麼以及對使用者的影響",
  "impact_level": "High|Medium|Low",
  "tags": ["最多 5 個標籤，從以下選擇：api-change, performance, security, bug-fix, new-feature, deprecation, breaking, config-change"]
}}"""

    def _build_pro_prompt(self, event: ClassifiedEvent) -> str:
        body_excerpt = (event.body or "")[:5000]
        diff_section = ""

        if event.diff_url and self.github_token:
            diff_content = self._fetch_diff(event.diff_url)
            if diff_content:
                diff_section = f"\nDiff（部分）：\n{diff_content}\n"

        return f"""請分析這個重大變更（來自 {event.repo_full_name}）：

分類：{event.classification}
標題：{event.title}
內文：
{body_excerpt}
{diff_section}

請輸出以下 JSON 格式（不要加任何其他文字）：
{{
  "summary": "技術摘要：說明改變了什麼、為什麼改、對現有系統的影響",
  "impact_level": "Breaking|High|Medium|Low",
  "migration_steps": ["遷移步驟1（若有 breaking change）", "步驟2"],
  "tags": ["最多 5 個標籤：api-change, performance, security, bug-fix, new-feature, deprecation, breaking, config-change"]
}}"""

    def _fetch_diff(self, diff_url: str) -> str:
        try:
            headers = {"Accept": "application/vnd.github.v3.diff"}
            if self.github_token:
                headers["Authorization"] = f"token {self.github_token}"

            with httpx.Client(timeout=30) as client:
                resp = client.get(diff_url, headers=headers, follow_redirects=True)
                resp.raise_for_status()
                diff_text = resp.text

            if len(diff_text) > self.config.diff_chunk_size:
                diff_text = diff_text[:self.config.diff_chunk_size]
                diff_text += "\n\n[... diff 已截斷，以上為部分內容 ...]"

            return diff_text
        except Exception as e:
            logger.warning(f"抓取 diff 失敗：{e}")
            return ""

    def _parse_response(self, raw_text: str, event: ClassifiedEvent) -> SummarizedEvent:
        # 移除 Gemini 可能加的 markdown code block
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text).strip()

        data: dict[str, Any] = {}
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        summary = data.get("summary", raw_text[:500]) or raw_text[:500]

        raw_impact = str(data.get("impact_level", "Medium")).capitalize()
        try:
            impact_level = ImpactLevel(raw_impact)
        except ValueError:
            impact_level = ImpactLevel.HIGH if event.classification in PRO_CLASSIFICATIONS else ImpactLevel.MEDIUM

        tags = [str(t) for t in data.get("tags", [])][:5]
        migration_steps = [str(s) for s in data.get("migration_steps", [])]

        return SummarizedEvent(
            **event.model_dump(),
            ai_summary=summary,
            impact_level=impact_level,
            tags=tags,
            migration_steps=migration_steps,
        )

    def _fallback(self, event: ClassifiedEvent) -> SummarizedEvent:
        return SummarizedEvent(
            **event.model_dump(),
            ai_summary="[摘要暫時無法取得 - API 錯誤]",
            impact_level=ImpactLevel.MEDIUM,
            tags=[],
            migration_steps=[],
        )
