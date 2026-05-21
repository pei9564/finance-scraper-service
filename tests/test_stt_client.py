"""STTClient 行為測試 — 用 monkeypatch 假掉 httpx 與 time.sleep。"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from finance_scraper.infrastructure.stt_client import STTClient


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock())


def _patch_httpx(monkeypatch, post=None, get=None):
    """讓 STTClient 內的 httpx.Client() with-block 用 fake post/get。"""
    class FakeClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, data=None): return post(url, data) if post else FakeResponse()
        def get(self, url): return get(url) if get else FakeResponse()
    monkeypatch.setattr("finance_scraper.infrastructure.stt_client.httpx.Client", FakeClient)


def test_submit_url_returns_job_id(monkeypatch):
    seen: dict = {}
    def post(url, data):
        seen["url"] = url
        seen["data"] = data
        return FakeResponse(202, {"job_id": "JOB-1", "status": "queued"})

    _patch_httpx(monkeypatch, post=post)

    client = STTClient(base_url="http://stt", language="zh")
    job_id = client.submit_url("https://yt/abc", topic="標題")

    assert job_id == "JOB-1"
    assert seen["url"] == "http://stt/transcribe_url"
    assert seen["data"] == {"url": "https://yt/abc", "language": "zh", "topic": "標題"}


def test_poll_returns_job_when_done(monkeypatch):
    states = iter([
        FakeResponse(200, {"status": "queued"}),
        FakeResponse(200, {"status": "processing"}),
        FakeResponse(200, {"status": "done", "text": "transcript"}),
    ])
    _patch_httpx(monkeypatch, get=lambda url: next(states))
    monkeypatch.setattr("finance_scraper.infrastructure.stt_client.time.sleep", lambda s: None)

    client = STTClient(base_url="http://stt", poll_interval_seconds=0)
    job = client.poll("JOB-1")

    assert job is not None
    assert job.text == "transcript"


def test_poll_returns_none_on_error_status(monkeypatch):
    _patch_httpx(monkeypatch, get=lambda url: FakeResponse(200, {"status": "error", "error": "boom"}))
    monkeypatch.setattr("finance_scraper.infrastructure.stt_client.time.sleep", lambda s: None)

    client = STTClient(base_url="http://stt", poll_interval_seconds=0)
    assert client.poll("JOB-X") is None


def test_poll_returns_none_when_job_missing(monkeypatch):
    _patch_httpx(monkeypatch, get=lambda url: FakeResponse(404))
    client = STTClient(base_url="http://stt", poll_interval_seconds=0)
    assert client.poll("JOB-MISSING") is None


def test_transcribe_returns_text_end_to_end(monkeypatch):
    states = iter([FakeResponse(200, {"status": "done", "text": " 全文 "})])
    _patch_httpx(
        monkeypatch,
        post=lambda u, d: FakeResponse(202, {"job_id": "J", "status": "queued"}),
        get=lambda u: next(states),
    )
    monkeypatch.setattr("finance_scraper.infrastructure.stt_client.time.sleep", lambda s: None)

    client = STTClient(base_url="http://stt", poll_interval_seconds=0)
    text = client.transcribe("https://yt/x")

    assert text == "全文"
