"""內部 LLM gateway client — OpenAI 相容的 /chat/completions adapter。

從舊 Summarizer 抽出：env var 覆蓋、model 自動探測、HTTP 呼叫。
實作 interfaces.LLMGateway。
"""
from __future__ import annotations

import logging
import os

import httpx

from tech_intel.domain import AIConfig

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
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

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
