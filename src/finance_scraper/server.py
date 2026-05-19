"""HTTP server — FastAPI + uvicorn，整合 asyncpg pool。

GET  /                          → 動態渲染 index.html（template + DATA_URL_PREFIX）
GET  /output/weekly/manifest.json → {dates, sources}（從 PG 動態組）
GET  /output/weekly/<date>.json → 該日報的 events JSON（從 PG 組）
GET  /api/status                → {"running": bool, "date": str|null, "error": str|null}
POST /api/run?date=...          → 背景執行 pipeline；date 省略時用今天
GET  /api/collections           → collection 與其月份列表
GET  /api/collections/{key}/{YYYY-MM} → 取該 collection 該月內容
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import date as date_t
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from finance_scraper.outputs.site_generator import DATA_URL_PREFIX, SOURCE_LABELS, build_html
from finance_scraper.storage import bookmarks, close_pool, daily, digests, init_schema, releases as releases_store, trending

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


# 已知 collection 的 metadata。新增 collection = 在這裡加一筆，前端會自動列出。
# type 對應前端 renderer dispatch 表（monthly-list / bookmarks）。
COLLECTIONS_REGISTRY: list[dict] = [
    {"key": "trending-repos", "label": "🚀 熱門 AI Repo",
     "type": "monthly-list", "backend": "trending"},
    {"key": "releases",       "label": "📦 GitHub Releases",
     "type": "releases",      "backend": "releases"},
    {"key": "bookmarks",      "label": "⭐ 我的收藏",
     "type": "bookmarks",     "backend": "bookmarks"},
]


# ── pipeline 狀態 ────────────────────────────────────────────────────────────
_run_lock = asyncio.Lock()
# progress 是 retry / pipeline 用的細節進度;retry 同 process 直接共用 dict ref,
# pipeline 透過 /tmp 檔案 IPC,讀取時合進這份。
_run_state: dict = {
    "running": False, "date": None, "mode": None, "error": None, "progress": None,
}
_monthly_lock = asyncio.Lock()
_monthly_state: dict = {"running": False, "month": None, "error": None}
_releases_lock = asyncio.Lock()
_releases_state: dict = {"running": False, "lookback": None, "error": None}
# 手動 STT — 每個 uid 一筆狀態,允許多支影片同時送 STT。
# status: "running" / "done" / "error";error 時帶 error 訊息。done 後過幾秒會被前端讀走清掉。
_transcribe_jobs: dict[str, dict] = {}
_transcribe_lock = asyncio.Lock()


# ── lifespan / app ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    await init_schema()
    logger.info("Finance Scraper server 啟動")
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)


# ── static / data routes ────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=build_html(), headers={"Cache-Control": "no-cache"})


@app.get(f"{DATA_URL_PREFIX}manifest.json")
async def manifest():
    dates = await daily.list_dates()
    sources = [{"key": k, "label": v} for k, v in SOURCE_LABELS.items()]
    return _no_cache_json({"dates": dates, "sources": sources})


@app.get(DATA_URL_PREFIX + "{date}.json")
async def daily_json(date: str):
    if not _DATE_RE.match(date):
        raise HTTPException(400, "日期格式錯誤")
    data = await daily.load_run(date)
    if data is None:
        raise HTTPException(404, f"找不到日報：{date}")
    return _no_cache_json(data)


@app.get("/api/feeds")
async def list_feeds():
    """日報 sidebar 用 — 列出所有 (source, feed_name) 及其總數/缺摘要數。"""
    feeds = await daily.list_feeds()
    return _no_cache_json({"feeds": feeds})


@app.get("/api/feeds/events")
async def feed_events(source: str | None = None, feed_name: str | None = None,
                      limit_dates: int = 30):
    """依 feed 撈最近 N 天的事件,server 端已按日期分組。"""
    if source is not None and source not in SOURCE_LABELS:
        raise HTTPException(400, f"未知 source：{source}")
    groups = await daily.load_feed_events(source, feed_name, limit_dates)
    return _no_cache_json({"source": source, "feed_name": feed_name, "groups": groups})


# ── collections ─────────────────────────────────────────────────────────────
async def _collection_months(coll: dict) -> list[str]:
    if coll["backend"] == "trending":
        return await trending.list_months()
    if coll["backend"] == "bookmarks":
        return await bookmarks.months()
    if coll["backend"] == "releases":
        return []  # releases 不依月份分頁,前端直接 fetch /api/collections/releases
    return []


@app.get("/api/collections")
async def list_collections():
    out = []
    for c in COLLECTIONS_REGISTRY:
        public = {"key": c["key"], "label": c["label"], "type": c["type"]}
        public["months"] = await _collection_months(c)
        out.append(public)
    return _no_cache_json({"collections": out})


@app.get("/api/collections/{key}/{month}")
async def get_collection_month(key: str, month: str):
    if not _MONTH_RE.match(month):
        raise HTTPException(400, "月份格式錯誤")
    coll = next((c for c in COLLECTIONS_REGISTRY if c["key"] == key), None)
    if coll is None:
        raise HTTPException(404, "未知 collection")
    if coll["backend"] == "trending":
        data = await trending.load_month(month)
        if data is None:
            raise HTTPException(404, "找不到該月份")
        return _no_cache_json(data)
    if coll["backend"] == "bookmarks":
        items = await bookmarks.list_by_month(month)
        return _no_cache_json({"month": month, "count": len(items), "items": items})
    raise HTTPException(404, "未知 backend")


@app.get("/api/collections/releases")
async def get_releases_collection(days: int = 180):
    """回傳近 N 天 releases,前端負責依 repo 分組與排序。"""
    if days < 1 or days > 3650:
        raise HTTPException(400, "days 必須在 1..3650")
    items = await releases_store.list_recent(days=days)
    return _no_cache_json({"days": days, "count": len(items), "items": items})


@app.get("/api/collections/bookmarks/{month}/digest")
async def get_bookmark_digest(month: str):
    if not _MONTH_RE.match(month):
        raise HTTPException(400, "月份格式錯誤")
    cached = await digests.get("bookmarks", month)
    if cached:
        return _no_cache_json({
            "digest": cached["digest_text"],
            "model": cached.get("model"),
            "source_count": cached.get("source_count"),
            "generated_at": cached.get("generated_at"),
        })
    return _no_cache_json({"digest": None, "generated_at": None})


@app.post("/api/collections/bookmarks/{month}/digest")
async def post_bookmark_digest(month: str):
    if not _MONTH_RE.match(month):
        raise HTTPException(400, "月份格式錯誤")
    try:
        return _no_cache_json(await _generate_bookmark_digest(month))
    except Exception as e:
        logger.exception("產生摘要失敗")
        raise HTTPException(500, str(e))


# ── bookmarks ───────────────────────────────────────────────────────────────
@app.get("/api/bookmarks/uids")
async def bookmark_uids():
    uids = sorted(await bookmarks.list_uids())
    return _no_cache_json({"uids": uids})


@app.post("/api/bookmarks", status_code=201)
async def add_bookmark(request: Request):
    try:
        event = await request.json()
    except Exception:
        raise HTTPException(400, "需要 JSON body")
    if not isinstance(event, dict) or not event.get("url") or not event.get("title") or not event.get("source"):
        raise HTTPException(400, "缺少必要欄位 source/url/title")
    return _no_cache_json(await bookmarks.add(event))


@app.delete("/api/bookmarks/{uid}")
async def delete_bookmark(uid: str):
    if not uid:
        raise HTTPException(400, "缺少 uid")
    ok = await bookmarks.remove(uid)
    if not ok:
        raise HTTPException(404, "找不到 uid")
    return _no_cache_json({"deleted": True})


@app.get("/api/llm-health")
async def get_llm_health():
    """快速探測 LLM gateway 是否可用 — 重跑摘要前可先按按看,確認連線。"""
    import yaml
    from dotenv import load_dotenv

    from finance_scraper.domain import AppConfig
    from finance_scraper.infrastructure import LLMGatewayClient

    load_dotenv()
    with open(PROJECT_ROOT / "config" / "repos.yaml", encoding="utf-8") as f:
        cfg = AppConfig(**yaml.safe_load(f))
    client = LLMGatewayClient(cfg.ai)
    ok = await asyncio.to_thread(client.health, 5.0)
    return _no_cache_json({
        "ok": ok,
        "base_url": client.base_url,
        "model": client.model or "(auto-detect)",
    })


# ── pipeline 觸發 ────────────────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    from finance_scraper.pipeline import progress as pipeline_progress
    async with _run_lock:
        out = dict(_run_state)
        # 若 pipeline 正在跑(subprocess),retry-style 的 in-memory progress 為空 —
        # 讀檔取得子進程寫入的進度。pipeline 結束後檔案也保留一段時間,只在 running 時合併。
        if out.get("running") and not out.get("progress"):
            file_prog = pipeline_progress.read()
            if file_prog:
                out["progress"] = file_prog
    return _no_cache_json(out)


@app.get("/api/monthly-status")
async def get_monthly_status():
    async with _monthly_lock:
        return _no_cache_json(dict(_monthly_state))


@app.post("/api/run")
async def run_pipeline(date: str | None = None):
    async with _run_lock:
        if _run_state["running"]:
            raise HTTPException(409, "pipeline 正在執行中")
        _run_state.update(running=True, date=date, mode="full", error=None)
    asyncio.create_task(_spawn_pipeline(date))
    return _no_cache_json({"started": True, "date": date, "mode": "full"})


@app.post("/api/transcribe-event")
async def post_transcribe_event(uid: str):
    """手動觸發單一 media 事件的 STT。背景跑,前端用 /api/transcribe-event/status?uid 輪詢。

    回 202 後直接 fire-and-forget;結果寫進 events.body 並更新 _transcribe_jobs[uid]。
    """
    if not uid:
        raise HTTPException(400, "需要 uid 參數")
    event = await daily.get_event_by_uid(uid)
    if event is None:
        raise HTTPException(404, "事件不存在")
    if not (event.get("source") or "").startswith(("youtube_", "podcast_")):
        raise HTTPException(400, "只支援 media 事件(youtube_* / podcast_*)")
    if (event.get("body") or "").strip():
        raise HTTPException(409, "已有逐字稿,如要重做請先清空 body")
    async with _transcribe_lock:
        cur = _transcribe_jobs.get(uid)
        if cur and cur.get("status") == "running":
            raise HTTPException(409, "此事件已在 STT 中")
        _transcribe_jobs[uid] = {"status": "running"}
    asyncio.create_task(_run_transcribe(uid, event["url"], event["title"]))
    return _no_cache_json({"uid": uid, "status": "running"})


@app.get("/api/transcribe-event/status")
async def get_transcribe_status(uid: str):
    if not uid:
        raise HTTPException(400, "需要 uid 參數")
    return _no_cache_json(_transcribe_jobs.get(uid) or {"status": "idle"})


@app.post("/api/retry-summary")
async def post_retry_summary(date: str, source: str, feed_name: str | None = None):
    if not date or not source:
        raise HTTPException(400, "需要 date 與 source 參數")
    async with _run_lock:
        if _run_state["running"]:
            raise HTTPException(409, "pipeline 正在執行中")
        mode_label = f"retry:{source}" + (f"/{feed_name}" if feed_name else "")
        _run_state.update(running=True, date=date, mode=mode_label, error=None)
    asyncio.create_task(_run_retry(date, source, feed_name))
    return _no_cache_json(
        {"started": True, "date": date, "source": source, "feed_name": feed_name}
    )


@app.post("/api/run-monthly")
async def post_run_monthly():
    async with _monthly_lock:
        if _monthly_state["running"]:
            raise HTTPException(409, "monthly pipeline 正在執行中")
        month = date_t.today().strftime("%Y-%m")
        _monthly_state.update(running=True, month=month, error=None)
    asyncio.create_task(_run_monthly_task())
    return _no_cache_json({"started": True, "month": month})


@app.get("/api/releases-status")
async def get_releases_status():
    async with _releases_lock:
        return _no_cache_json(dict(_releases_state))


@app.post("/api/run-releases")
async def post_run_releases(lookback: int = 180):
    if lookback < 1 or lookback > 3650:
        raise HTTPException(400, "lookback 必須在 1..3650")
    async with _releases_lock:
        if _releases_state["running"]:
            raise HTTPException(409, "releases pipeline 正在執行中")
        _releases_state.update(running=True, lookback=lookback, error=None)
    asyncio.create_task(_run_releases_task(lookback))
    return _no_cache_json({"started": True, "lookback": lookback})


# ── helpers ─────────────────────────────────────────────────────────────────
def _no_cache_json(payload) -> JSONResponse:
    return JSONResponse(content=payload, headers={"Cache-Control": "no-cache"})


async def _spawn_pipeline(date: str | None) -> None:
    from finance_scraper.pipeline import progress as pipeline_progress
    pipeline_progress.clear()  # 清掉前次殘留,避免 /api/status 撿到舊資料

    env = os.environ.copy()
    if date:
        env["RUN_DATE"] = date
    python = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable
    try:
        proc = await asyncio.create_subprocess_exec(
            python, "-m", "finance_scraper.main",
            cwd=str(PROJECT_ROOT), env=env,
        )
        rc = await proc.wait()
        async with _run_lock:
            if rc == 0:
                _run_state.update(running=False, error=None)
            else:
                _run_state.update(running=False, error=f"exit code {rc}")
    except Exception as e:
        async with _run_lock:
            _run_state.update(running=False, error=str(e))
    finally:
        pipeline_progress.clear()


async def _run_retry(date: str, source: str, feed_name: str | None = None) -> None:
    from finance_scraper.retry import retry_summary
    # progress 是 retry_summary 邊跑邊 mutate 的同一份 dict;塞進 _run_state["progress"]
    # 後,/api/status 讀到的就是即時狀態
    progress: dict = {}
    async with _run_lock:
        _run_state["progress"] = progress
    try:
        result = await retry_summary(date, source, feed_name, progress=progress)
        label = source + (f"/{feed_name}" if feed_name else "")
        err = (
            f"補摘要 {label}：{result['failed']} 篇全部失敗(查 server log)"
            if result["failed"] > 0 and result["updated"] == 0
            else None
        )
        async with _run_lock:
            _run_state.update(running=False, error=err)
    except Exception as e:
        async with _run_lock:
            _run_state.update(running=False, error=str(e))


async def _run_monthly_task() -> None:
    from finance_scraper.monthly import run_monthly
    try:
        await run_monthly()
        async with _monthly_lock:
            _monthly_state.update(running=False, error=None)
    except Exception as e:
        async with _monthly_lock:
            _monthly_state.update(running=False, error=str(e))


async def _run_transcribe(uid: str, url: str, title: str) -> None:
    """背景跑 STT(在 thread 內阻塞輪詢),完成後寫回 events.body。"""
    from finance_scraper.infrastructure import STTClient
    try:
        stt = STTClient()  # base_url / language 都從 env(STT_BASE_URL / STT_LANGUAGE)
        text = await asyncio.to_thread(stt.transcribe, url, (title or "")[:80])
        if not text:
            _transcribe_jobs[uid] = {"status": "error", "error": "STT 無回應或失敗"}
            return
        ok = await daily.update_event_body(uid, text)
        if not ok:
            _transcribe_jobs[uid] = {"status": "error", "error": "寫入 DB 失敗(uid 不存在?)"}
            return
        _transcribe_jobs[uid] = {"status": "done", "length": len(text)}
        logger.info(f"手動 STT 完成 uid={uid} ({len(text)} 字)")
    except Exception as e:
        logger.exception("手動 STT 失敗")
        _transcribe_jobs[uid] = {"status": "error", "error": str(e)}


async def _run_releases_task(lookback: int) -> None:
    from finance_scraper.releases import run_releases
    try:
        await run_releases(lookback_days=lookback)
        async with _releases_lock:
            _releases_state.update(running=False, error=None)
    except Exception as e:
        async with _releases_lock:
            _releases_state.update(running=False, error=str(e))


async def _generate_bookmark_digest(month: str) -> dict:
    """同步產生並寫入該月收藏的 LLM 回顧；回傳同 GET 的格式。"""
    import yaml
    from dotenv import load_dotenv

    from finance_scraper.domain import AppConfig
    from finance_scraper.infrastructure import LLMGatewayClient
    from finance_scraper.processing.bookmark_digest import BookmarkDigester

    items = await bookmarks.list_by_month(month)
    if not items:
        return {"digest": None, "generated_at": None, "source_count": 0}

    load_dotenv()
    with open(PROJECT_ROOT / "config" / "repos.yaml", encoding="utf-8") as f:
        cfg = AppConfig(**yaml.safe_load(f))
    llm = LLMGatewayClient(cfg.ai)

    # Digester 是同步呼叫；丟 thread 避免擋 event loop
    digest_text = await asyncio.to_thread(BookmarkDigester(llm).digest, month, items)
    model = getattr(llm, "model", None) or None
    await digests.set("bookmarks", month, digest_text, model, len(items))
    cached = await digests.get("bookmarks", month) or {}
    return {
        "digest": digest_text,
        "model": cached.get("model"),
        "source_count": cached.get("source_count", len(items)),
        "generated_at": cached.get("generated_at"),
    }


def cli() -> None:
    """python -m finance_scraper.server → 用 uvicorn 起服務。"""
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    cli()
