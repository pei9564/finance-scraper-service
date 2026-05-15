"""Sources 層 — 每個來源一個自足單元（收集器 + 處理步驟鏈）。"""
from .base import SourceUnit
from .registry import build_source_units

__all__ = ["SourceUnit", "build_source_units"]
