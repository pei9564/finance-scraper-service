"""pytest 設定"""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: 需要真實 API 的端對端測試")
