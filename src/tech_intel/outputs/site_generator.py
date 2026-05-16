"""靜態網頁模板 + 來源 label — 由 server 動態渲染回應。

只保留 HTML template 與 SOURCE_LABELS；資料（日期清單、manifest、events）
皆由 server 直接查 PG 後組合，不再有靜態檔案生成。
"""
from __future__ import annotations

# 前端 fetch 每日 JSON 用的 URL 前綴；server 對應路徑 /output/weekly/<date>.json
DATA_URL_PREFIX = "/output/weekly/"

# 單一事實來源 — 新增 SourceType 時只需在這裡補一筆 label，tab 與徽章
# 顏色（CSS 端）也會自動套用。
SOURCE_LABELS: dict[str, str] = {
    "github": "🔔 GitHub",
    "news": "📰 新聞",
    "paper": "📄 論文",
    "finance": "💰 財經",
}


def build_html() -> str:
    """以 DATA_URL_PREFIX 注入頁面 — 前端據此 fetch 日報 JSON 與 manifest。"""
    return _HTML_TEMPLATE.replace("__DATA_PREFIX__", DATA_URL_PREFIX)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tech Intel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "Segoe UI", "Noto Sans TC", sans-serif;
         background: #0d1117; color: #c9d1d9; display: flex; min-height: 100vh; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* ── sidebar ── */
  #sidebar { width: 210px; background: #161b22; border-right: 1px solid #30363d;
             padding: 16px 0; flex-shrink: 0; height: 100vh; overflow-y: auto;
             position: sticky; top: 0; }
  #sidebar h1 { font-size: 15px; padding: 0 16px 10px; color: #f0f6fc; }

  .mode-toggle { display: flex; margin: 0 16px 12px; border: 1px solid #30363d;
                 border-radius: 6px; overflow: hidden; }
  .mode-btn { flex: 1; padding: 5px 0; font-size: 12px; text-align: center;
              cursor: pointer; background: transparent; color: #8b949e; border: none; }
  .mode-btn.active { background: #1f6feb; color: #fff; }

  #pipeline-status { padding: 2px 16px 8px; font-size: 12px; color: #8b949e; min-height: 18px; }
  #pipeline-status.running { color: #e3b341; }
  #pipeline-status.error { color: #f85149; }

  .date-row { display: flex; align-items: center; gap: 4px; padding: 2px 8px 2px 16px; }
  .date-label { flex: 1; padding: 6px 0; cursor: pointer; font-size: 14px; }
  .date-row:hover { background: #21262d; }
  .date-row.active { background: #1f6feb; color: #fff; }
  .date-row.active .rerun-btn { color: #ffffffaa; border-color: #ffffff44; }
  .rerun-btn { font-size: 11px; padding: 2px 6px; background: transparent;
               border: 1px solid #30363d; border-radius: 4px; color: #8b949e;
               cursor: pointer; white-space: nowrap; flex-shrink: 0; }
  .rerun-btn:hover:not(:disabled) { border-color: #58a6ff; color: #58a6ff; }
  .rerun-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .run-today-btn { width: 100%; font-size: 12px; padding: 6px 0; background: transparent;
    border: 1px solid #1f6feb88; border-radius: 5px; color: #58a6ff; cursor: pointer; }
  .run-today-btn:hover:not(:disabled) { background: #1f6feb18; }
  .run-today-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .month-row { padding: 6px 16px; cursor: pointer; font-size: 14px; }
  .month-row:hover { background: #21262d; }
  .month-row.active { background: #1f6feb; color: #fff; }

  .collection-row { padding: 6px 16px; cursor: pointer; font-size: 14px; }
  .collection-row:hover { background: #21262d; }
  .collection-row.active { background: #1f6feb; color: #fff; }
  .collection-section-label { padding: 12px 16px 4px; font-size: 11px;
    color: #6e7681; text-transform: uppercase; letter-spacing: 0.5px; }

  /* ── main ── */
  #main { flex: 1; padding: 24px 32px; max-width: 900px; }
  #tabs { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }
  .tab { padding: 6px 14px; background: #21262d; border: 1px solid #30363d;
         border-radius: 6px; cursor: pointer; font-size: 13px; }
  .tab.active { background: #1f6feb; border-color: #1f6feb; color: #fff; }
  #retry-action { margin-bottom: 12px; min-height: 28px; }
  .retry-source-btn { font-size: 12px; padding: 4px 10px; background: transparent;
    border: 1px solid #e3b34155; border-radius: 5px; color: #e3b341; cursor: pointer; }
  .retry-source-btn:hover:not(:disabled) { background: #e3b34118; }
  .retry-source-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── cards ── */
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 14px 16px; margin-bottom: 12px; }
  .card-meta { font-size: 12px; color: #8b949e; margin-bottom: 6px;
               display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .badge { background: #21262d; border-radius: 4px; padding: 2px 8px; font-size: 11px; }
  .badge.src-github { background: #1f6feb33; color: #58a6ff; }
  .badge.src-news { background: #d2992233; color: #e3b341; }
  .badge.src-paper { background: #3fb95033; color: #56d364; }
  .badge.src-finance { background: #39c5cf33; color: #39c5cf; }
  .badge.impact-Breaking { background: #f8514933; color: #f85149; }
  .badge.impact-High { background: #db6d2833; color: #db6d28; }
  .badge.no-summary { background: #30363d; color: #8b949e; font-style: italic; }
  .badge.rank { background: #6e40c933; color: #bc8cff; font-weight: 600; }
  .badge.lang { background: #21262d; color: #8b949e; }
  .card-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
  .card-summary { font-size: 13px; color: #c9d1d9; line-height: 1.6; }
  .card-body-preview { color: #8b949e; }
  .card-tags { margin-top: 8px; font-size: 12px; color: #8b949e; }
  .empty { color: #8b949e; padding: 40px 0; text-align: center; }

  .bookmark-btn { background: transparent; border: none; cursor: pointer;
    font-size: 14px; color: #6e7681; padding: 0 4px; line-height: 1;
    margin-left: auto; }
  .bookmark-btn:hover { color: #e3b341; }
  .bookmark-btn.on { color: #e3b341; }
  .bookmark-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── collection header ── */
  #collection-header { display: flex; align-items: center; justify-content: space-between;
                       margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
  #collection-header h2 { font-size: 16px; color: #f0f6fc; }
  .collection-action-btn { font-size: 12px; padding: 5px 12px; background: transparent;
    border: 1px solid #6e40c955; border-radius: 5px; color: #bc8cff; cursor: pointer; }
  .collection-action-btn:hover:not(:disabled) { background: #6e40c918; }
  .collection-action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  #collection-status { font-size: 12px; color: #8b949e; margin-bottom: 12px; min-height: 18px; }
  #collection-status.running { color: #e3b341; }
  #collection-status.error { color: #f85149; }
</style>
</head>
<body>
<div id="sidebar">
  <h1>📊 Tech Intel</h1>
  <div class="mode-toggle">
    <button class="mode-btn active" id="btn-daily" onclick="setMode('daily')">日報</button>
    <button class="mode-btn" id="btn-collections" onclick="setMode('collections')">資料庫</button>
  </div>
  <div id="pipeline-status"></div>
  <div id="daily-sidebar">
    <div style="padding: 4px 16px 8px">
      <button class="run-today-btn" id="run-today-btn" onclick="runToday()">▶ 執行今天</button>
    </div>
    <div id="date-list"></div>
  </div>
  <div id="collections-sidebar" style="display:none">
    <div class="collection-section-label">分類</div>
    <div id="collection-list"></div>
    <div class="collection-section-label">月份</div>
    <div id="collection-month-list"></div>
  </div>
</div>
<div id="main">
  <!-- daily view -->
  <div id="daily-view">
    <div id="tabs"></div>
    <div id="retry-action"></div>
    <div id="content"></div>
  </div>
  <!-- collections view -->
  <div id="collection-view" style="display:none">
    <div id="collection-header">
      <div>
        <h2 id="collection-title"></h2>
        <div id="collection-subtitle" style="font-size:12px;color:#8b949e;margin-top:4px"></div>
      </div>
      <div id="collection-actions"></div>
    </div>
    <div id="collection-status"></div>
    <div id="collection-content"></div>
  </div>
</div>

<script>
const DATA_PREFIX = "__DATA_PREFIX__";
// SOURCES 由 manifest.json 注入；初始只放「全部」，initDaily 會 append 後端列出的來源
let SOURCES = [
  { key: "all", label: "全部" },
];
// COLLECTIONS 由 /api/collections 注入；每筆含 key/label/type/months
let COLLECTIONS = [];
// type → render function；新增 collection type 時在這裡多加一筆
const COLLECTION_RENDERERS = {
  "monthly-list": renderMonthlyRepos,
  "bookmarks": renderBookmarks,
};
// 已收藏 UID 集合 — 載入後決定每張卡的 ⭐ 是否實心
let BOOKMARKED_UIDS = new Set();
let mode = "daily";
let currentData = null;
let currentSource = "all";
let currentDate = null;
let currentCollection = null;       // collection 物件
let currentCollectionMonth = null;  // 'YYYY-MM'
let pollTimer = null;
let monthlyPollTimer = null;

// ── mode toggle ───────────────────────────────────────────────────────────
function setMode(m) {
  mode = m;
  document.getElementById("btn-daily").classList.toggle("active", m === "daily");
  document.getElementById("btn-collections").classList.toggle("active", m === "collections");
  document.getElementById("daily-sidebar").style.display = m === "daily" ? "" : "none";
  document.getElementById("collections-sidebar").style.display = m === "collections" ? "" : "none";
  document.getElementById("daily-view").style.display = m === "daily" ? "" : "none";
  document.getElementById("collection-view").style.display = m === "collections" ? "" : "none";
  document.getElementById("pipeline-status").style.display = m === "daily" ? "" : "none";
}

// ── init ──────────────────────────────────────────────────────────────────
async function init() {
  await loadBookmarkUids();
  await initDaily();
  await initCollections();
  pollStatus();
  pollMonthlyStatus();
}

async function loadBookmarkUids() {
  try {
    const res = await fetch("/api/bookmarks/uids");
    if (!res.ok) return;
    const data = await res.json();
    BOOKMARKED_UIDS = new Set(data.uids || []);
  } catch {}
}

async function initDaily() {
  try {
    const res = await fetch(DATA_PREFIX + "manifest.json?" + Date.now());
    const manifest = await res.json();
    // 每次 init 都從 [{all}] 重建，避免重跑後 SOURCES / 日期 / tab 重複
    SOURCES = [{ key: "all", label: "全部" }];
    if (Array.isArray(manifest.sources)) {
      SOURCES = SOURCES.concat(manifest.sources);
    }
    const list = document.getElementById("date-list");
    list.innerHTML = "";
    document.getElementById("tabs").innerHTML = "";
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
  } catch { document.getElementById("content").innerHTML = '<div class="empty">尚無資料</div>'; }
}

async function initCollections() {
  try {
    const res = await fetch("/api/collections?" + Date.now());
    if (!res.ok) { renderCollectionEmpty("無法載入 collections"); return; }
    const data = await res.json();
    COLLECTIONS = data.collections || [];
    renderCollectionList();
    if (COLLECTIONS.length) {
      await selectCollection(COLLECTIONS[0]);
    } else {
      renderCollectionEmpty("尚未設定任何 collection");
    }
  } catch (e) { renderCollectionEmpty("載入失敗：" + e.message); }
}

function renderCollectionList() {
  const list = document.getElementById("collection-list");
  list.innerHTML = "";
  COLLECTIONS.forEach(c => {
    const row = document.createElement("div");
    row.className = "collection-row";
    row.dataset.key = c.key;
    row.textContent = c.label;
    row.onclick = () => selectCollection(c);
    list.appendChild(row);
  });
}

function renderCollectionMonthList() {
  const list = document.getElementById("collection-month-list");
  list.innerHTML = "";
  const months = (currentCollection && currentCollection.months) || [];
  months.forEach(m => {
    const row = document.createElement("div");
    row.className = "month-row";
    row.dataset.month = m;
    row.textContent = m;
    row.onclick = () => selectCollectionMonth(m);
    list.appendChild(row);
  });
}

async function selectCollection(c) {
  currentCollection = c;
  currentCollectionMonth = null;
  document.querySelectorAll(".collection-row").forEach(x =>
    x.classList.toggle("active", x.dataset.key === c.key));
  document.getElementById("collection-title").textContent = c.label;
  document.getElementById("collection-subtitle").textContent = _collectionSubtitle(c);
  renderCollectionActions();
  renderCollectionMonthList();
  if ((c.months || []).length) {
    await selectCollectionMonth(c.months[0]);
  } else {
    renderCollectionEmpty(_collectionEmptyHint(c));
  }
}

async function selectCollectionMonth(m) {
  currentCollectionMonth = m;
  document.querySelectorAll(".month-row").forEach(x =>
    x.classList.toggle("active", x.dataset.month === m));
  try {
    const res = await fetch(`/api/collections/${currentCollection.key}/${m}?` + Date.now());
    if (!res.ok) { renderCollectionEmpty("載入失敗"); return; }
    const data = await res.json();
    const renderer = COLLECTION_RENDERERS[currentCollection.type];
    if (!renderer) { renderCollectionEmpty(`未知的 collection type: ${currentCollection.type}`); return; }
    renderer(data);
  } catch (e) { renderCollectionEmpty("載入失敗：" + e.message); }
}

function renderCollectionEmpty(msg) {
  document.getElementById("collection-content").innerHTML =
    `<div class="empty">${esc(msg)}</div>`;
}

function _collectionSubtitle(c) {
  if (c.key === "trending-repos") return "近半年內新建立、具 AI 相關 topic 的 repo，依 star 數排序";
  if (c.key === "bookmarks") return "你在日報上收藏的內容，依月份分組";
  return "";
}

function _collectionEmptyHint(c) {
  if (c.key === "trending-repos") return "尚無資料，點右上「更新本月熱門」開始收集";
  if (c.key === "bookmarks") return "尚無收藏，去日報點 ⭐ 加入";
  return "本 collection 尚無資料";
}

function renderCollectionActions() {
  const el = document.getElementById("collection-actions");
  if (currentCollection && currentCollection.key === "trending-repos") {
    el.innerHTML = `<button class="collection-action-btn" id="run-monthly-btn"
      onclick="runMonthly()">⚡ 更新本月熱門</button>`;
  } else {
    el.innerHTML = "";
  }
}

// ── date selection ────────────────────────────────────────────────────────
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

// ── collection renderers ──────────────────────────────────────────────────
function renderMonthlyRepos(data) {
  const el = document.getElementById("collection-content");
  if (!data.repos || !data.repos.length) {
    el.innerHTML = '<div class="empty">本月無資料</div>';
    return;
  }
  const generated = data.generated_at
    ? `<div style="font-size:12px;color:#8b949e;margin-bottom:16px">
        共 ${data.count} 個 repo，涵蓋近 ${data.lookback_days} 天，
        更新於 ${data.generated_at.slice(0,16).replace("T"," ")} UTC
       </div>` : "";
  el.innerHTML = generated + data.repos.map(trendingCardHtml).join("");
}

function trendingCardHtml(r) {
  const topicBadges = (r.topics || []).slice(0, 4)
    .map(t => `<span class="badge">${esc(t)}</span>`).join("");
  const lang = r.language ? `<span class="badge lang">${esc(r.language)}</span>` : "";
  return `<div class="card">
    <div class="card-meta">
      <span class="badge rank">#${r.rank}</span>
      ${lang}
      <span>⭐ ${r.stars.toLocaleString()}</span>
      <span>🍴 ${r.forks.toLocaleString()}</span>
      <span style="color:#8b949e">建立 ${r.created_at}</span>
      ${topicBadges}
    </div>
    <div class="card-title"><a href="${esc(r.url)}" target="_blank">${esc(r.full_name)}</a></div>
    ${r.description ? `<div class="card-summary">${esc(r.description)}</div>` : ""}
  </div>`;
}

// ── daily re-run / retry ──────────────────────────────────────────────────
async function rerun(date) {
  updateStatusBar({ running: true, date, mode: "full" });
  try {
    const res = await fetch(`/api/run?date=${date}`, { method: "POST" });
    const j = await res.json();
    if (!res.ok) { updateStatusBar({ running: false, error: j.error || "重跑失敗" }); return; }
    startPolling();
  } catch {
    updateStatusBar({ running: false, error: "無法連線" });
  }
}

async function runToday() {
  updateStatusBar({ running: true, mode: "full" });
  try {
    const res = await fetch("/api/run", { method: "POST" });
    const j = await res.json();
    if (!res.ok) { updateStatusBar({ running: false, error: j.error || "執行失敗" }); return; }
    startPolling();
  } catch {
    updateStatusBar({ running: false, error: "無法連線" });
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
    updateStatusBar({ running: false, error: "無法連線" });
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

// ── monthly run ───────────────────────────────────────────────────────────
async function runMonthly() {
  updateMonthlyStatus({ running: true });
  try {
    const res = await fetch("/api/run-monthly", { method: "POST" });
    const j = await res.json();
    if (!res.ok) { updateMonthlyStatus({ running: false, error: j.error || "失敗" }); return; }
    startMonthlyPolling();
  } catch {
    updateMonthlyStatus({ running: false, error: "無法連線" });
  }
}

// ── daily status polling ──────────────────────────────────────────────────
async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const s = await res.json();
    updateStatusBar(s);
    if (s.running) startPolling();
  } catch {}
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const s = await (await fetch("/api/status")).json();
      updateStatusBar(s);
      if (!s.running) {
        stopPolling();
        if (currentDate) {
          await reloadCurrentDate();
        } else {
          // 第一次跑（空白狀態）— 重新拉 manifest 與日期清單
          document.getElementById("date-list").innerHTML = "";
          await initDaily();
        }
      }
    } catch { stopPolling(); }
  }, 2000);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function updateStatusBar(s) {
  const el = document.getElementById("pipeline-status");
  const btns = document.querySelectorAll(".rerun-btn, .retry-source-btn, .run-today-btn");
  if (s.running) {
    const label = s.mode && s.mode.startsWith("retry:") ? `補摘要 ${s.mode.split(":")[1]}` : "執行中";
    el.className = "running"; el.textContent = `⚡ ${label} ${s.date || ""}`;
    btns.forEach(b => b.disabled = true);
  } else if (s.error) {
    el.className = "error"; el.textContent = "❌ 執行失敗";
    btns.forEach(b => b.disabled = false);
  } else {
    el.className = ""; el.textContent = "";
    btns.forEach(b => b.disabled = false);
  }
}

// ── monthly status polling ────────────────────────────────────────────────
async function pollMonthlyStatus() {
  try {
    const res = await fetch("/api/monthly-status");
    if (!res.ok) return;
    const s = await res.json();
    updateMonthlyStatus(s);
    if (s.running) startMonthlyPolling();
  } catch {}
}

function startMonthlyPolling() {
  if (monthlyPollTimer) return;
  monthlyPollTimer = setInterval(async () => {
    try {
      const s = await (await fetch("/api/monthly-status")).json();
      updateMonthlyStatus(s);
      if (!s.running) {
        stopMonthlyPolling();
        // 收集完成 — 重新拉 collections manifest 並回到 trending-repos
        await initCollections();
      }
    } catch { stopMonthlyPolling(); }
  }, 3000);
}

function stopMonthlyPolling() {
  if (monthlyPollTimer) { clearInterval(monthlyPollTimer); monthlyPollTimer = null; }
}

function updateMonthlyStatus(s) {
  const el = document.getElementById("collection-status");
  const btn = document.getElementById("run-monthly-btn");
  if (s.running) {
    el.className = "running"; el.textContent = `⚡ 收集中 ${s.month || ""}...`;
    if (btn) btn.disabled = true;
  } else if (s.error) {
    el.className = "error"; el.textContent = `❌ 失敗：${s.error}`;
    if (btn) btn.disabled = false;
  } else {
    el.className = ""; el.textContent = "";
    if (btn) btn.disabled = false;
  }
}

// ── daily tabs ────────────────────────────────────────────────────────────
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
    const count = key === "all" ? events.length : events.filter(e => e.source === key).length;
    el.textContent = `${s.label} (${count})`;
  });
}

function render() {
  if (!currentData) return;
  const events = currentData.events.filter(e => currentSource === "all" || e.source === currentSource);
  const content = document.getElementById("content");
  content.innerHTML = events.length ? events.map(cardHtml).join("") : '<div class="empty">本分類無內容</div>';
  updateRetryAction();
}

// ── shared utils ──────────────────────────────────────────────────────────
function esc(s) {
  return (s || "").replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function cardHtml(e) {
  let origin = "";
  if (e.source === "github") origin = esc(e.repo || "");
  else if (e.source === "news") origin = esc(e.feed_name || "");
  else if (e.source === "paper") origin = esc((e.categories || []).slice(0, 2).join(", "));
  else if (e.source === "finance") origin = esc(e.feed_name || "");
  const noSummary = !e.ai_summary && (e.source === "news" || e.source === "paper" || e.source === "finance");
  const isOn = e.uid && BOOKMARKED_UIDS.has(e.uid);
  const star = e.uid
    ? `<button class="bookmark-btn ${isOn ? "on" : ""}" data-uid="${esc(e.uid)}"
        title="${isOn ? "取消收藏" : "收藏"}"
        onclick="toggleBookmark(this, '${esc(e.uid)}')">★</button>`
    : "";
  const meta = [
    `<span class="badge src-${e.source}">${e.source}</span>`,
    origin ? `<span>${origin}</span>` : "",
    e.classification ? `<span class="badge">${esc(e.classification)}</span>` : "",
    (e.impact_level === "Breaking" || e.impact_level === "High")
      ? `<span class="badge impact-${e.impact_level}">${e.impact_level}</span>` : "",
    e.score ? `<span>▲ ${e.score}</span>` : "",
    noSummary ? `<span class="badge no-summary">摘要待重跑</span>` : "",
    star,
  ].filter(Boolean).join("");
  const tags = (e.tags || []).length
    ? `<div class="card-tags">${e.tags.map(t => "#" + esc(t)).join(" ")}</div>` : "";
  let summary = e.ai_summary
    ? `<div class="card-summary">${esc(e.ai_summary)}</div>`
    : e.body ? `<div class="card-summary card-body-preview">${esc(e.body.slice(0, 300))}…</div>` : "";
  return `<div class="card">
    <div class="card-meta">${meta}</div>
    <div class="card-title"><a href="${esc(e.url)}" target="_blank">${esc(e.title)}</a></div>
    ${summary}${tags}
  </div>`;
}

async function toggleBookmark(btn, uid) {
  // 從目前 daily 資料找到完整事件物件（避免把 JSON 塞進 HTML 屬性的逸脫風險）
  const event = (currentData && currentData.events || []).find(e => e.uid === uid);
  if (!event) return;
  btn.disabled = true;
  const turningOn = !BOOKMARKED_UIDS.has(uid);
  try {
    if (turningOn) {
      const res = await fetch("/api/bookmarks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(event),
      });
      if (res.ok) {
        BOOKMARKED_UIDS.add(uid);
        btn.classList.add("on");
        btn.title = "取消收藏";
      }
    } else {
      const res = await fetch(`/api/bookmarks/${encodeURIComponent(uid)}`,
        { method: "DELETE" });
      if (res.ok) {
        BOOKMARKED_UIDS.delete(uid);
        btn.classList.remove("on");
        btn.title = "收藏";
      }
    }
  } catch {}
  btn.disabled = false;
}

function renderBookmarks(data) {
  const el = document.getElementById("collection-content");
  const items = data.items || [];
  if (!items.length) {
    el.innerHTML = '<div class="empty">本月尚無收藏</div>';
    return;
  }
  // 依 source 分組，每組組內已是新→舊（server 已 ORDER BY bookmarked_at DESC）
  const groups = {};
  items.forEach(it => {
    const k = it.source || "other";
    (groups[k] = groups[k] || []).push(it);
  });
  const order = ["github", "news", "paper", "finance", "other"];
  const sections = order.filter(k => groups[k]).map(k => {
    const label = (SOURCES.find(s => s.key === k) || {}).label || k;
    const cards = groups[k].map(bookmarkCardHtml).join("");
    return `<h3 style="font-size:13px;color:#8b949e;margin:18px 0 8px">${label} (${groups[k].length})</h3>${cards}`;
  }).join("");
  el.innerHTML = `
    <div style="font-size:12px;color:#8b949e;margin-bottom:8px">
      ${data.month}：共 ${data.count} 筆
    </div>
    <div id="digest-area" style="margin-bottom:16px"></div>
    ${sections}`;
  // 載入已快取的摘要（不阻塞渲染）
  refreshDigest(data.month);
}

async function refreshDigest(month) {
  try {
    const res = await fetch(`/api/collections/bookmarks/${month}/digest?` + Date.now());
    if (!res.ok) return;
    const d = await res.json();
    renderDigestArea(month, d);
  } catch {}
}

function renderDigestArea(month, d) {
  const el = document.getElementById("digest-area");
  if (!el) return;
  const hasDigest = d && d.digest;
  const btnLabel = hasDigest ? "🪄 重新產生回顧" : "🪄 用 LLM 產生本月回顧";
  const meta = hasDigest && d.generated_at
    ? `<span style="font-size:11px;color:#6e7681;margin-left:8px">
        產生於 ${d.generated_at} · ${d.source_count || 0} 筆</span>`
    : "";
  const body = hasDigest
    ? `<div class="card" style="white-space:pre-wrap;line-height:1.7">${esc(d.digest)}</div>`
    : "";
  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <button class="collection-action-btn" id="digest-btn"
        onclick="generateDigest('${month}')">${btnLabel}</button>
      ${meta}
    </div>
    ${body}`;
}

async function generateDigest(month) {
  const btn = document.getElementById("digest-btn");
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = "🪄 產生中…可能需要幾秒";
  try {
    const res = await fetch(`/api/collections/bookmarks/${month}/digest`, { method: "POST" });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      btn.textContent = `❌ 失敗：${j.error || res.status}`;
      btn.disabled = false;
      return;
    }
    const d = await res.json();
    renderDigestArea(month, d);
  } catch (e) {
    btn.textContent = `❌ ${e.message}`;
    btn.disabled = false;
  }
}

function bookmarkCardHtml(b) {
  const meta = [
    `<span class="badge src-${b.source}">${b.source}</span>`,
    b.origin ? `<span>${esc(b.origin)}</span>` : "",
    b.classification ? `<span class="badge">${esc(b.classification)}</span>` : "",
    `<span style="color:#6e7681">收藏於 ${(b.bookmarked_at || "").slice(0,10)}</span>`,
    `<button class="bookmark-btn on" data-uid="${esc(b.event_uid)}"
      title="取消收藏" onclick="unbookmarkInList(this, '${esc(b.event_uid)}')">★</button>`,
  ].filter(Boolean).join("");
  const summary = b.ai_summary
    ? `<div class="card-summary">${esc(b.ai_summary)}</div>` : "";
  return `<div class="card">
    <div class="card-meta">${meta}</div>
    <div class="card-title"><a href="${esc(b.url)}" target="_blank">${esc(b.title)}</a></div>
    ${summary}
  </div>`;
}

async function unbookmarkInList(btn, uid) {
  btn.disabled = true;
  try {
    const res = await fetch(`/api/bookmarks/${encodeURIComponent(uid)}`, { method: "DELETE" });
    if (res.ok) {
      BOOKMARKED_UIDS.delete(uid);
      // 重新拉這個月份；若該月已空 reload collections manifest
      await selectCollectionMonth(currentCollectionMonth);
    }
  } catch {}
  btn.disabled = false;
}

init();
</script>
</body>
</html>
"""
