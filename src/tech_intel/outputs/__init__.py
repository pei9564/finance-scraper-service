"""Outputs 層 — 每個輸出目標一個 writer，藏在 OutputWriter 介面之後。"""
from .registry import build_output_writers

__all__ = ["build_output_writers"]
