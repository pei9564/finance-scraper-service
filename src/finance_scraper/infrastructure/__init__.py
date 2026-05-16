"""Infrastructure 層 — 具體 I/O adapter。"""
from .llm_gateway import LLMGatewayClient
from .stt_client import STTClient

__all__ = ["LLMGatewayClient", "STTClient"]
