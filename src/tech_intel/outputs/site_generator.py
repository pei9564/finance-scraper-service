"""靜態網頁產生器 - 將每日 JSON 包成一個可瀏覽的網頁
- 左側：日期清單
- 右側：依 source 切換，檢視當日內容
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def prune_old(output_dir: Path, keep_days: int = 30) -> None:
    """刪除超過 keep_days 天的每日 JSON 檔。"""
    cutoff = date.today() - timedelta(days=keep_days)
    removed = 0
    for f in output_dir.glob("*.json"):
        m = DATE_FILE_RE.match(f.name)
        if not m:
            continue
        try:
            file_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            f.unlink()
            removed += 1
    if removed:
        logger.info(f"清除 {removed} 筆超過 {keep_days} 天的舊資料")


def generate_site(output_dir: Path, site_root: Path | None = None) -> None:
    """掃描每日 JSON，產生 manifest.json 與 index.html。

    site_root: index.html 放置位置（預設與 output_dir 相同）。
               若與 output_dir 不同，fetch 路徑自動加上相對前綴。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    site_root = site_root or output_dir

    dates = []
    for f in output_dir.glob("*.json"):
        m = DATE_FILE_RE.match(f.name)
        if m:
            dates.append(m.group(1))
    dates.sort(reverse=True)

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fp:
        json.dump({"dates": dates}, fp, ensure_ascii=False, indent=2)

    try:
        rel = output_dir.relative_to(site_root)
        data_prefix = str(rel).replace("\\", "/") + "/"
    except ValueError:
        data_prefix = ""

    index_path = site_root / "index.html"
    with open(index_path, "w", encoding="utf-8") as fp:
        fp.write(_build_html(data_prefix))

    logger.info(f"網頁產生完成：{index_path}（{len(dates)} 個日期）")


def _build_html(data_prefix: str = "") -> str:
    return _HTML_TEMPLATE.replace("__DATA_PREFIX__", data_prefix)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tech Intel 日報</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "Segoe UI", "Noto Sans TC", sans-serif;
         background: #0d1117; color: #c9d1d9; display: flex; min-height: 100vh; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }

  #sidebar { width: 210px; background: #161b22; border-right: 1px solid #30363d;
             padding: 16px 0; flex-shrink: 0; height: 100vh; overflow-y: auto;
             position: sticky; top: 0; }
  #sidebar h1 { font-size: 15px; padding: 0 16px 8px; color: #f0f6fc; }
  #pipeline-status { padding: 4px 16px 10px; font-size: 12px; color: #8b949e; min-height: 20px; }
  #pipeline-status.running { color: #e3b341; }
  #pipeline-status.error { color: #f85149; }

  .date-row { display: flex; align-items: center; gap: 4px;
              padding: 2px 8px 2px 16px; }
  .date-label { flex: 1; padding: 6px 0; cursor: pointer; font-size: 14px; }
  .date-row:hover { background: #21262d; }
  .date-row.active { background: #1f6feb; color: #fff; }
  .date-row.active .rerun-btn { color: #ffffffaa; border-color: #ffffff44; }
  .rerun-btn { font-size: 11px; padding: 2px 6px; background: transparent;
               border: 1px solid #30363d; border-radius: 4px; color: #8b949e;
               cursor: pointer; white-space: nowrap; flex-shrink: 0; }
  .rerun-btn:hover:not(:disabled) { border-color: #58a6ff; color: #58a6ff; }
  .rerun-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  #main { flex: 1; padding: 24px 32px; max-width: 900px; }
  #tabs { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }
  .tab { padding: 6px 14px; background: #21262d; border: 1px solid #30363d;
         border-radius: 6px; cursor: pointer; font-size: 13px; }
  .tab.active { background: #1f6feb; border-color: #1f6feb; color: #fff; }
  #retry-action { margin-bottom: 12px; min-height: 28px; }
  .retry-source-btn { font-size: 12px; padding: 4px 10px; background: transparent;
    border: 1px solid #e3b34155; border-radius: 5px; color: #e3b341;
    cursor: pointer; }
  .retry-source-btn:hover:not(:disabled) { background: #e3b34118; }
  .retry-source-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 14px 16px; margin-bottom: 12px; }
  .card-meta { font-size: 12px; color: #8b949e; margin-bottom: 6px;
               display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .badge { background: #21262d; border-radius: 4px; padding: 2px 8px; font-size: 11px; }
  .badge.src-github { background: #1f6feb33; color: #58a6ff; }
  .badge.src-news { background: #d2992233; color: #e3b341; }
  .badge.src-paper { background: #3fb95033; color: #56d364; }
  .badge.impact-Breaking { background: #f8514933; color: #f85149; }
  .badge.impact-High { background: #db6d2833; color: #db6d28; }
  .badge.no-summary { background: #30363d; color: #8b949e; font-style: italic; }
  .card-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
  .card-summary { font-size: 13px; color: #c9d1d9; line-height: 1.6; }
  .card-body-preview { color: #8b949e; }
  .card-tags { margin-top: 8px; font-size: 12px; color: #8b949e; }
  .empty { color: #8b949e; padding: 40px 0; text-align: center; }
</style>
</head>
<body>
<div id="sidebar">
  <h1>📊 Tech Intel</h1>
  <div id="pipeline-status"></div>
  <div id="date-list"></div>
</div>
<div id="main">
  <div id="tabs"></div>
  <div id="retry-action"></div>
  <div id="content"></div>
</div>

<script>
const DATA_PREFIX = "__DATA_PREFIX__";
const SOURCES = [
  { key: "all", label: "全部" },
  { key: "github", label: "🔔 GitHub" },
  { key: "news", label: "📰 新聞" },
  { key: "paper", label: "📄 論文" },
];
let currentData = null;
let currentSource = "all";
let currentDate = null;
let pollTimer = null;

// ── init ──────────────────────────────────────────────────────────────────
async function init() {
  const res = await fetch(DATA_PREFIX + "manifest.json");
  const manifest = await res.json();
  const list = document.getElementById("date-list");
  manifest.dates.forEach((d, i) => {
    const row = makeDateRow(d, i === 0);
    list.appendChild(row);
  });
  renderTabs();
  if (manifest.dates.length) {
    await selectDate(manifest.dates[0], list.firstChild);
  } else {
    document.getElementById("content").innerHTML = '<div class="empty">尚無資料</div>';
  }
  pollStatus();
}

function makeDateRow(d, active) {
  const row = document.createElement("div");
  row.className = "date-row" + (active ? " active" : "");
  row.dataset.date = d;

  const label = document.createElement("span");
  label.className = "date-label";
  label.textContent = d;
  label.onclick = () => selectDate(d, row);

  const btn = document.createElement("button");
  btn.className = "rerun-btn";
  btn.textContent = "重跑";
  btn.onclick = (e) => { e.stopPropagation(); rerun(d); };

  row.appendChild(label);
  row.appendChild(btn);
  return row;
}

// ── date selection ────────────────────────────────────────────────────────
async function selectDate(d, row) {
  document.querySelectorAll(".date-row").forEach(x => x.classList.remove("active"));
  row.classList.add("active");
  currentDate = d;
  const res = await fetch(DATA_PREFIX + d + ".json?" + Date.now());
  currentData = await res.json();
  updateTabCounts();
  render();
}

async function reloadCurrentDate() {
  if (!currentDate) return;
  const row = document.querySelector(`.date-row[data-date="${currentDate}"]`);
  if (row) await selectDate(currentDate, row);
}

// ── re-run / retry ────────────────────────────────────────────────────────
async function rerun(date) {
  updateStatusBar({ running: true, date, mode: "full" });
  try {
    const res = await fetch(`/api/run?date=${date}`, { method: "POST" });
    const j = await res.json();
    if (!res.ok) { updateStatusBar({ running: false, error: j.error || "重跑失敗" }); return; }
    startPolling();
  } catch {
    updateStatusBar({ running: false, error: "無法連線，請確認使用 tech-intel-server 啟動" });
  }
}

async function retrySummary(date, source) {
  updateStatusBar({ running: true, date, mode: `retry:${source}` });
  try {
    const res = await fetch(`/api/retry-summary?date=${date}&source=${source}`, { method: "POST" });
    const j = await res.json();
    if (!res.ok) { updateStatusBar({ running: false, error: j.error || "補摘要失敗" }); return; }
    startPolling();
  } catch {
    updateStatusBar({ running: false, error: "無法連線，請確認使用 tech-intel-server 啟動" });
  }
}

function updateRetryAction() {
  const el = document.getElementById("retry-action");
  if (!currentData || currentSource === "all") { el.innerHTML = ""; return; }
  const missing = currentData.events.filter(
    e => e.source === currentSource && !e.ai_summary
  ).length;
  const label = SOURCES.find(s => s.key === currentSource)?.label || currentSource;
  const hint = missing > 0 ? ` (${missing} 篇待補)` : "";
  el.innerHTML = `<button class="retry-source-btn"
    onclick="retrySummary('${currentDate}','${currentSource}')">
    ⚡ 補摘要 ${label}${hint}
  </button>`;
}

// ── status polling ────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const s = await res.json();
    updateStatusBar(s);
    if (s.running) {
      startPolling();
    } else {
      stopPolling();
    }
  } catch {
    // server 不支援 /api/status（用舊的 python -m http.server），靜默忽略
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/status");
      const s = await res.json();
      updateStatusBar(s);
      if (!s.running) {
        stopPolling();
        await reloadCurrentDate();
      }
    } catch { stopPolling(); }
  }, 2000);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function updateStatusBar(s) {
  const el = document.getElementById("pipeline-status");
  const allBtns = document.querySelectorAll(".rerun-btn, .retry-source-btn");
  if (s.running) {
    const modeLabel = s.mode && s.mode.startsWith("retry:")
      ? `補摘要 ${s.mode.split(":")[1]}` : "執行中";
    el.className = "running";
    el.textContent = `⚡ ${modeLabel} ${s.date || ""}`;
    allBtns.forEach(b => b.disabled = true);
  } else if (s.error) {
    el.className = "error";
    el.textContent = "❌ 執行失敗";
    allBtns.forEach(b => b.disabled = false);
  } else {
    el.className = "";
    el.textContent = "";
    allBtns.forEach(b => b.disabled = false);
  }
}

// ── tabs ──────────────────────────────────────────────────────────────────
function renderTabs() {
  const tabs = document.getElementById("tabs");
  SOURCES.forEach(s => {
    const el = document.createElement("div");
    el.className = "tab" + (s.key === currentSource ? " active" : "");
    el.dataset.key = s.key;
    el.textContent = s.label;
    el.onclick = () => {
      currentSource = s.key;
      document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
      el.classList.add("active");
      render();
    };
    tabs.appendChild(el);
  });
}

function updateTabCounts() {
  const events = (currentData && currentData.events) || [];
  document.querySelectorAll(".tab").forEach(el => {
    const key = el.dataset.key;
    const s = SOURCES.find(s => s.key === key);
    const count = key === "all" ? events.length
      : events.filter(e => e.source === key).length;
    el.textContent = `${s.label} (${count})`;
  });
}

// ── render ────────────────────────────────────────────────────────────────
function render() {
  if (!currentData) return;
  const events = currentData.events.filter(
    e => currentSource === "all" || e.source === currentSource
  );
  const content = document.getElementById("content");
  if (!events.length) {
    content.innerHTML = '<div class="empty">本分類無內容</div>';
  } else {
    content.innerHTML = events.map(cardHtml).join("");
  }
  updateRetryAction();
}

function esc(s) {
  return (s || "").replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function cardHtml(e) {
  let origin = "";
  if (e.source === "github") origin = esc(e.repo || "");
  else if (e.source === "news") origin = esc(e.feed_name || "");
  else if (e.source === "paper") origin = esc((e.categories || []).slice(0, 2).join(", "));

  const noSummary = !e.ai_summary && (e.source === "news" || e.source === "paper");
  const meta = [
    `<span class="badge src-${e.source}">${e.source}</span>`,
    origin ? `<span>${origin}</span>` : "",
    e.classification ? `<span class="badge">${esc(e.classification)}</span>` : "",
    (e.impact_level === "Breaking" || e.impact_level === "High")
      ? `<span class="badge impact-${e.impact_level}">${e.impact_level}</span>` : "",
    e.score ? `<span>▲ ${e.score}</span>` : "",
    noSummary ? `<span class="badge no-summary">摘要待重跑</span>` : "",
  ].filter(Boolean).join("");

  const tags = (e.tags || []).length
    ? `<div class="card-tags">${e.tags.map(t => "#" + esc(t)).join(" ")}</div>` : "";

  let summary;
  if (e.ai_summary) {
    summary = `<div class="card-summary">${esc(e.ai_summary)}</div>`;
  } else if (e.body) {
    summary = `<div class="card-summary card-body-preview">${esc(e.body.slice(0, 300))}…</div>`;
  } else {
    summary = "";
  }

  return `<div class="card">
    <div class="card-meta">${meta}</div>
    <div class="card-title"><a href="${esc(e.url)}" target="_blank">${esc(e.title)}</a></div>
    ${summary}
    ${tags}
  </div>`;
}

init();
</script>
</body>
</html>
"""
