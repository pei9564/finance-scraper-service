"""Interfaces 層 — 只有 Protocol 定義，無實作。"""
from .llm import LLMGateway
from .output import OutputWriter
from .source import ProcessingStep, SourceCollector

__all__ = ["LLMGateway", "OutputWriter", "ProcessingStep", "SourceCollector"]
