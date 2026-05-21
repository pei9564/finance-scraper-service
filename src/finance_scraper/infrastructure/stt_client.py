"""STT(speech-to-text)Gateway client — 對接內部 stt-ai-worker 服務。

服務介面參考 stt-ai-worker:
- POST /transcribe_url form-encoded {url, language?, topic?} → 202 {job_id, status}
- GET /job/{id} → JobView 含 status (queued / processing / done / error) + text (done 時)

語意:
- submit_url() 立刻回 job_id;poll() 阻塞輪詢直到 done / error / timeout
- 整個 transcribe() helper 包好兩段流程,collector 端只要呼叫它即可
"""
from __future__ import annotations

import logging
import os
import time

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

_TERMINAL = {"done", "error", "cancelled"}


class TranscribeRequest(BaseModel):
    """POST /transcribe_url 的 form 欄位。"""
    url: str
    language: str = ""
    topic: str = ""


class JobView(BaseModel):
    """stt-ai-worker 的 job 回應；欄位全給預設,容忍部分缺漏。"""
    job_id: str = ""
    status: str = ""
    text: str | None = None
    error: str | None = None


class STTClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        poll_interval_seconds: int = 15,
        timeout_seconds: int = 900,
        language: str = "",
    ):
        # env var 覆蓋 config(避免設定檔寫死本機 URL)
        self.base_url = os.environ.get("STT_BASE_URL", base_url).rstrip("/")
        self.poll_interval = poll_interval_seconds
        self.timeout = timeout_seconds
        self.language = os.environ.get("STT_LANGUAGE", language)

    def submit_url(self, url: str, topic: str = "") -> str:
        """POST /transcribe_url,回 job_id;失敗拋 httpx.HTTPError。"""
        req = TranscribeRequest(url=url, language=self.language, topic=topic)
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.base_url}/transcribe_url", data=req.model_dump())
            resp.raise_for_status()
            job_id = JobView.model_validate(resp.json()).job_id
        if not job_id:
            raise httpx.HTTPError("STT 未回傳 job_id")
        return job_id

    def poll(self, job_id: str) -> JobView | None:
        """阻塞輪詢直到終止狀態或 timeout。回傳完成的 JobView;timeout / error 回 None。"""
        deadline = time.time() + self.timeout
        while True:
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.get(f"{self.base_url}/job/{job_id}")
                    if resp.status_code == 404:
                        logger.warning(f"STT job {job_id} 不存在(被刪?)")
                        return None
                    resp.raise_for_status()
                    job = JobView.model_validate(resp.json())
            except (httpx.HTTPError, ValidationError) as e:
                logger.warning(f"輪詢 STT job {job_id} 出錯:{e}")
                return None

            status = job.status.lower()
            if status == "done":
                return job
            if status in _TERMINAL:
                logger.warning(f"STT job {job_id} 結束狀態 {status}:{job.error}")
                return None

            if time.time() >= deadline:
                logger.warning(f"STT job {job_id} 輪詢超時({self.timeout}s)")
                return None
            time.sleep(self.poll_interval)

    def transcribe(self, url: str, topic: str = "") -> str | None:
        """submit + poll 的便捷組合 — 回 transcript text 或 None。"""
        try:
            job_id = self.submit_url(url, topic=topic)
        except httpx.HTTPError as e:
            logger.warning(f"提交 STT 任務失敗({url}):{e}")
            return None
        job = self.poll(job_id)
        if job is None:
            return None
        text = (job.text or "").strip()
        return text or None
