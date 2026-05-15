"""SourceUnit - 一個自足的來源單元：收集器 + 逐則處理步驟鏈。"""
from __future__ import annotations

from dataclasses import dataclass, field

from tech_intel.domain import SourceType
from tech_intel.interfaces import ProcessingStep, SourceCollector


@dataclass
class SourceUnit:
    source_type: SourceType
    collector: SourceCollector
    steps: list[ProcessingStep] = field(default_factory=list)
