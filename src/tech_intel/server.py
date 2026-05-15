"""開發用 HTTP server — serve 靜態網頁 + pipeline 觸發 API。

GET  /api/status        → {"running": bool, "date": str|null, "error": str|null}
POST /api/run?date=...  → 背景執行 pipeline，date 省略時用今天
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

_lock = threading.Lock()
_state: dict = {"running": False, "date": None, "error": None}


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    # ── GET ───────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            with _lock:
                self._json(dict(_state))
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

        else:
            self.send_error(404)

    # ── helpers ───────────────────────────────────────────────────────────
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


def _retry_summary(date: str, source: str):
    from tech_intel.retry import retry_summary
    try:
        retry_summary(date, source)
        with _lock:
            _state.update(running=False, error=None)
    except Exception as e:
        with _lock:
            _state.update(running=False, error=str(e))


def serve(host: str = "0.0.0.0", port: int = 8080):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"Tech Intel server: http://{host}:{port}")
    server.serve_forever()


def cli():
    port = int(os.environ.get("PORT", 8080))
    serve(port=port)


if __name__ == "__main__":
    cli()
