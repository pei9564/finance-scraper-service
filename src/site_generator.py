"""
靜態網頁產生器 - 將每日 JSON 包成一個可瀏覽的網頁
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


def generate_site(output_dir: Path) -> None:
    """掃描每日 JSON，產生 manifest.json 與 index.html。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    dates = []
    for f in output_dir.glob("*.json"):
        m = DATE_FILE_RE.match(f.name)
        if m:
            dates.append(m.group(1))
    dates.sort(reverse=True)

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fp:
        json.dump({"dates": dates}, fp, ensure_ascii=False, indent=2)

    index_path = output_dir / "index.html"
    with open(index_path, "w", encoding="utf-8") as fp:
        fp.write(_HTML)

    logger.info(f"網頁產生完成：{index_path}（{len(dates)} 個日期）")


_HTML = """<!DOCTYPE html>
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

  #sidebar { width: 200px; background: #161b22; border-right: 1px solid #30363d;
             padding: 16px 0; flex-shrink: 0; height: 100vh; overflow-y: auto;
             position: sticky; top: 0; }
  #sidebar h1 { font-size: 15px; padding: 0 16px 12px; color: #f0f6fc; }
  .date-item { padding: 8px 16px; cursor: pointer; font-size: 14px; }
  .date-item:hover { background: #21262d; }
  .date-item.active { background: #1f6feb; color: #fff; }

  #main { flex: 1; padding: 24px 32px; max-width: 900px; }
  #summary { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
             padding: 16px; margin-bottom: 20px; white-space: pre-wrap;
             font-size: 14px; line-height: 1.7; }
  #tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .tab { padding: 6px 14px; background: #21262d; border: 1px solid #30363d;
         border-radius: 6px; cursor: pointer; font-size: 13px; }
  .tab.active { background: #1f6feb; border-color: #1f6feb; color: #fff; }

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
  .card-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
  .card-summary { font-size: 13px; color: #c9d1d9; line-height: 1.6; }
  .card-body-preview { color: #8b949e; font-style: italic; }
  .card-tags { margin-top: 8px; font-size: 12px; color: #8b949e; }
  .empty { color: #8b949e; padding: 40px 0; text-align: center; }
</style>
</head>
<body>
<div id="sidebar">
  <h1>📊 Tech Intel</h1>
  <div id="date-list"></div>
</div>
<div id="main">
  <div id="summary"></div>
  <div id="tabs"></div>
  <div id="content"></div>
</div>

<script>
const SOURCES = [
  { key: "all", label: "全部" },
  { key: "github", label: "🔔 GitHub" },
  { key: "news", label: "📰 新聞" },
  { key: "paper", label: "📄 論文" },
];
let currentData = null;
let currentSource = "all";

async function init() {
  const res = await fetch("manifest.json");
  const manifest = await res.json();
  const list = document.getElementById("date-list");
  manifest.dates.forEach((d, i) => {
    const el = document.createElement("div");
    el.className = "date-item" + (i === 0 ? " active" : "");
    el.textContent = d;
    el.onclick = () => selectDate(d, el);
    list.appendChild(el);
  });
  renderTabs();
  if (manifest.dates.length) {
    selectDate(manifest.dates[0], list.firstChild);
  } else {
    document.getElementById("content").innerHTML =
      '<div class="empty">尚無資料</div>';
  }
}

async function selectDate(d, el) {
  document.querySelectorAll(".date-item").forEach(x => x.classList.remove("active"));
  el.classList.add("active");
  const res = await fetch(d + ".json");
  currentData = await res.json();
  document.getElementById("summary").textContent =
    currentData.daily_summary || "（無摘要）";
  updateTabCounts();
  render();
}

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
    const label = SOURCES.find(s => s.key === key).label;
    const count = key === "all"
      ? events.length
      : events.filter(e => e.source === key).length;
    el.textContent = `${label} (${count})`;
  });
}

function render() {
  if (!currentData) return;
  const events = currentData.events.filter(
    e => currentSource === "all" || e.source === currentSource
  );
  const content = document.getElementById("content");
  if (!events.length) {
    content.innerHTML = '<div class="empty">本分類無內容</div>';
    return;
  }
  content.innerHTML = events.map(cardHtml).join("");
}

function esc(s) {
  return (s || "").replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function cardHtml(e) {
  let origin = "";
  if (e.source === "github") origin = esc(e.repo || "");
  else if (e.source === "news") origin = esc(e.feed_name || "");
  else if (e.source === "paper") origin = esc((e.categories || []).join(", "));

  const meta = [
    `<span class="badge src-${e.source}">${e.source}</span>`,
    origin ? `<span>${origin}</span>` : "",
    e.classification ? `<span class="badge">${esc(e.classification)}</span>` : "",
    (e.impact_level === "Breaking" || e.impact_level === "High")
      ? `<span class="badge impact-${e.impact_level}">${e.impact_level}</span>` : "",
    e.score ? `<span>▲ ${e.score}</span>` : "",
  ].filter(Boolean).join("");

  const tags = (e.tags || []).length
    ? `<div class="card-tags">${e.tags.map(t => "#" + esc(t)).join(" ")}</div>` : "";

  let summary;
  if (e.ai_summary) {
    summary = `<div class="card-summary">${esc(e.ai_summary)}</div>`;
  } else if (e.body) {
    summary = `<div class="card-summary card-body-preview">${esc(e.body.slice(0, 200))}…</div>`;
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
