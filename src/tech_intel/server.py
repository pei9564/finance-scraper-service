"""開發用 HTTP server — serve 靜態網頁 + pipeline 觸發 API。

GET  /api/status              → {"running": bool, "date": str|null, "error": str|null}
POST /api/run?date=...        → 背景執行 pipeline，date 省略時用今天
GET  /api/collections         → 列出資料庫中所有 collection 與其月份
GET  /api/collections/{key}/{YYYY-MM}  → 取該 collection 該月內容
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
COLLECTIONS_ROOT = PROJECT_ROOT / "output" / "collections"
_MONTH_RE = re.compile(r"^(\d{4}-\d{2})$")
_DIGEST_PATH_RE = re.compile(r"^/api/collections/bookmarks/(\d{4}-\d{2})/digest$")


# 已知 collection 的 metadata。新增 collection = 在這裡加一筆，前端會自動列出。
# type 對應前端 renderer dispatch 表（monthly-list / bookmarks）。
# storage 為 'fs'（讀 output/collections/<key>/<month>.json）或 'db'（查 SQLite）。
COLLECTIONS_REGISTRY: list[dict] = [
    {"key": "trending-repos", "label": "🚀 熱門 AI Repo",
     "type": "monthly-list", "storage": "fs"},
    {"key": "bookmarks",      "label": "⭐ 我的收藏",
     "type": "bookmarks",     "storage": "db"},
]


def _list_collection_months(coll: dict) -> list[str]:
    """各 storage 後端取月份清單。"""
    if coll["storage"] == "fs":
        coll_dir = COLLECTIONS_ROOT / coll["key"]
        if not coll_dir.exists():
            return []
        months = [f.stem for f in coll_dir.glob("*.json") if _MONTH_RE.match(f.stem)]
        months.sort(reverse=True)
        return months
    if coll["storage"] == "db" and coll["key"] == "bookmarks":
        from tech_intel.storage import bookmarks
        return bookmarks.months()
    return []


def _build_collections_manifest() -> dict:
    """組合 /api/collections 回應 — 每個 collection 自帶其 months。"""
    return {
        "collections": [
            {**c, "months": _list_collection_months(c)}
            for c in COLLECTIONS_REGISTRY
        ],
    }


def _load_collection_month(key: str, month: str) -> dict | None:
    if not _MONTH_RE.match(month):
        return None
    coll = next((c for c in COLLECTIONS_REGISTRY if c["key"] == key), None)
    if coll is None:
        return None
    if coll["storage"] == "fs":
        path = COLLECTIONS_ROOT / key / f"{month}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    if coll["storage"] == "db" and key == "bookmarks":
        from tech_intel.storage import bookmarks
        items = bookmarks.list_by_month(month)
        return {"month": month, "count": len(items), "items": items}
    return None

_lock = threading.Lock()
_state: dict = {"running": False, "date": None, "error": None}
_monthly_lock = threading.Lock()
_monthly_state: dict = {"running": False, "month": None, "error": None}


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    # ── GET ───────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            with _lock:
                self._json(dict(_state))
        elif path == "/api/monthly-status":
            with _monthly_lock:
                self._json(dict(_monthly_state))
        elif path == "/api/collections":
            self._json(_build_collections_manifest())
        elif (m := _DIGEST_PATH_RE.match(path)) is not None:
            from tech_intel.storage import digests
            cached = digests.get("bookmarks", m.group(1))
            if cached:
                self._json({
                    "digest": cached["digest_text"],
                    "model": cached.get("model"),
                    "source_count": cached.get("source_count"),
                    "generated_at": cached.get("generated_at"),
                })
            else:
                self._json({"digest": None, "generated_at": None})
        elif path.startswith("/api/collections/"):
            parts = path[len("/api/collections/"):].split("/")
            if len(parts) == 2:
                key, month = parts
                data = _load_collection_month(key, month)
                if data is None:
                    self._json({"error": "找不到該月份"}, 404)
                else:
                    self._json(data)
            else:
                self._json({"error": "路徑格式錯誤"}, 400)
        elif path == "/api/bookmarks/uids":
            from tech_intel.storage import bookmarks
            self._json({"uids": sorted(bookmarks.list_uids())})
        else:
            super().do_GET()

    # ── POST ──────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)

        if path == "/api/run":
            date = (qs.get("date") or [None])[0]
            with _lock:
                if _state["running"]:
                    self._json({"error": "pipeline 正在執行中"}, 409)
                    return
                _state.update(running=True, date=date, mode="full", error=None)
            threading.Thread(target=_run_pipeline, args=(date,), daemon=True).start()
            self._json({"started": True, "date": date, "mode": "full"})

        elif path == "/api/retry-summary":
            date = (qs.get("date") or [None])[0]
            source = (qs.get("source") or [None])[0]
            if not date or not source:
                self._json({"error": "需要 date 與 source 參數"}, 400)
                return
            with _lock:
                if _state["running"]:
                    self._json({"error": "pipeline 正在執行中"}, 409)
                    return
                _state.update(running=True, date=date, mode=f"retry:{source}", error=None)
            threading.Thread(target=_retry_summary, args=(date, source), daemon=True).start()
            self._json({"started": True, "date": date, "source": source})

        elif path == "/api/run-monthly":
            with _monthly_lock:
                if _monthly_state["running"]:
                    self._json({"error": "monthly pipeline 正在執行中"}, 409)
                    return
                from datetime import date
                month = date.today().strftime("%Y-%m")
                _monthly_state.update(running=True, month=month, error=None)
            threading.Thread(target=_run_monthly, daemon=True).start()
            self._json({"started": True, "month": month})

        elif path == "/api/bookmarks":
            event = self._read_body_json()
            if event is None:
                self._json({"error": "需要 JSON body"}, 400)
                return
            if not event.get("url") or not event.get("title") or not event.get("source"):
                self._json({"error": "缺少必要欄位 source/url/title"}, 400)
                return
            from tech_intel.storage import bookmarks
            result = bookmarks.add(event)
            self._json(result, 201)

        elif (m := _DIGEST_PATH_RE.match(path)) is not None:
            month = m.group(1)
            try:
                result = _generate_bookmark_digest(month)
            except Exception as e:
                logger.exception("產生摘要失敗")
                self._json({"error": str(e)}, 500)
                return
            self._json(result)

        else:
            self.send_error(404)

    # ── DELETE ────────────────────────────────────────────────────────────
    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/bookmarks/"):
            uid = path[len("/api/bookmarks/"):]
            if not uid:
                self._json({"error": "缺少 uid"}, 400)
                return
            from tech_intel.storage import bookmarks
            ok = bookmarks.remove(uid)
            if ok:
                self._json({"deleted": True})
            else:
                self._json({"error": "找不到 uid"}, 404)
        else:
            self.send_error(404)

    # ── helpers ───────────────────────────────────────────────────────────
    def _read_body_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return None
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None


    def _json(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # 靜音 access log


def _run_pipeline(date: str | None):
    env = os.environ.copy()
    if date:
        env["RUN_DATE"] = date
    python = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable
    try:
        subprocess.run(
            [python, "-m", "tech_intel.main"],
            cwd=PROJECT_ROOT,
            env=env,
            check=True,
        )
        with _lock:
            _state.update(running=False, error=None)
    except subprocess.CalledProcessError as e:
        with _lock:
            _state.update(running=False, error=str(e))


def _run_monthly():
    from tech_intel.monthly import run_monthly
    try:
        run_monthly()
        with _monthly_lock:
            _monthly_state.update(running=False, error=None)
    except Exception as e:
        with _monthly_lock:
            _monthly_state.update(running=False, error=str(e))


def _retry_summary(date: str, source: str):
    from tech_intel.retry import retry_summary
    try:
        retry_summary(date, source)
        with _lock:
            _state.update(running=False, error=None)
    except Exception as e:
        with _lock:
            _state.update(running=False, error=str(e))


def _generate_bookmark_digest(month: str) -> dict:
    """同步產生並寫入該月收藏的 LLM 回顧；回傳同 GET 的格式。"""
    import yaml
    from dotenv import load_dotenv

    from tech_intel.domain import AppConfig
    from tech_intel.infrastructure import LLMGatewayClient
    from tech_intel.processing.bookmark_digest import BookmarkDigester
    from tech_intel.storage import bookmarks, digests

    items = bookmarks.list_by_month(month)
    if not items:
        return {"digest": None, "generated_at": None, "source_count": 0}

    load_dotenv()
    with open(PROJECT_ROOT / "config" / "repos.yaml", encoding="utf-8") as f:
        cfg = AppConfig(**yaml.safe_load(f))
    llm = LLMGatewayClient(cfg.ai)

    digest_text = BookmarkDigester(llm).digest(month, items)
    model = getattr(llm, "model", None) or None
    digests.set("bookmarks", month, digest_text, model, len(items))
    cached = digests.get("bookmarks", month) or {}
    return {
        "digest": digest_text,
        "model": cached.get("model"),
        "source_count": cached.get("source_count", len(items)),
        "generated_at": cached.get("generated_at"),
    }


def serve(host: str = "0.0.0.0", port: int = 8080):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    from tech_intel.storage import init_schema
    init_schema()
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"Tech Intel server: http://{host}:{port}")
    server.serve_forever()


def cli():
    port = int(os.environ.get("PORT", 8080))
    serve(port=port)


if __name__ == "__main__":
    cli()
