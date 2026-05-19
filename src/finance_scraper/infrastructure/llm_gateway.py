"""內部 LLM gateway client — OpenAI 相容的 /chat/completions adapter。

從舊 Summarizer 抽出：env var 覆蓋、model 自動探測、HTTP 呼叫。
實作 interfaces.LLMGateway。
"""
from __future__ import annotations

import logging
import os

import httpx

from finance_scraper.domain import AIConfig

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = "你是一位資深軟體工程師，專門為技術團隊整理技術情報。"


class LLMGatewayClient:
    def __init__(self, config: AIConfig):
        self.config = config
        # env var 覆蓋 config（真實的內部 gateway 位址/金鑰放 .env，不進公開 repo）
        self.base_url = os.environ.get("VLLM_BASE_URL", config.vllm_base_url)
        self.model = os.environ.get("VLLM_MODEL", config.vllm_model)
        self.api_key = os.environ.get("VLLM_API_KEY", "EMPTY")
        self._model_cache: str | None = None

    def chat(
        self,
        user_prompt: str,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        payload = {
            "model": self._model_name(),
            "messages": [
                {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            # 內部 gateway 後端模型(GLM / Qwen 系列)預設會啟用 reasoning,先把
            # max_tokens 預算花光在思考過程,content 就會空白。摘要只需要結果,
            # 關掉 thinking 速度也快很多。內部 gateway 已實測支援此 kwarg。
            "chat_template_kwargs": {"enable_thinking": False},
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            # gateway 偶爾會回 content=null(過載 / 內部錯誤),先轉空字串再 strip,
            # 否則上層會吃到 NoneType.strip 例外
            content = (msg.get("content") or "").strip()
            if not content:
                # reasoning 模型(GLM 等)會先寫 reasoning,token 用完才寫 content;
                # 若 content 空但 reasoning 有東西且 finish_reason=length,代表
                # max_tokens 不夠,需要在 config 加大
                reasoning_len = len(msg.get("reasoning") or "")
                logger.warning(
                    f"LLM 回傳空 content(finish_reason={choice.get('finish_reason')}, "
                    f"reasoning_chars={reasoning_len}) — 可能 max_tokens 太低"
                )
            return content

    def _model_name(self) -> str:
        if self.model:
            return self.model
        if self._model_cache:
            return self._model_cache
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            self._model_cache = resp.json()["data"][0]["id"]
        logger.info(f"gateway 自動偵測 model：{self._model_cache}")
        return self._model_cache

    def health(self, timeout: float = 3.0) -> bool:
        """快速探測 gateway 是否可用 — pipeline 啟動時用，避免拖慢整個流程。

        True：可呼叫 chat()，arxiv curation / 摘要會啟動。
        False：跳過依賴 LLM 的步驟（arxiv 抓取、SummarizeStep、DailySummarizer），
        其他來源照常收集，事件無摘要可後續用「補摘要」按鈕補。
        """
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"LLM gateway 不可用：{e}")
            return False
