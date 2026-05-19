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
    "news": "📰 新聞",
    "paper": "📄 論文",
    "finance": "💰 財經",
    "youtube_tech": "📺 YT 科技",
    "youtube_fin": "📺 YT 財經",
    "podcast_tech": "🎙️ Podcast 科技",
    "podcast_fin": "🎙️ Podcast 財經",
}


def build_html() -> str:
    """以 DATA_URL_PREFIX 注入頁面 — 前端據此 fetch 日報 JSON 與 manifest。"""
    return _HTML_TEMPLATE.replace("__DATA_PREFIX__", DATA_URL_PREFIX)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Finance Scraper</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "Segoe UI", "Noto Sans TC", sans-serif;
         background: #0d1117; color: #c9d1d9; display: flex; min-height: 100vh; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* ── sidebar ── */
  #sidebar { width: 210px; background: #161b22; border-right: 1px solid #30363d;
             flex-shrink: 0; height: 100vh; position: sticky; top: 0;
             display: flex; flex-direction: column; }
  #sidebar-scroll { flex: 1; overflow-y: auto; padding: 16px 0 8px; }
  #sidebar-footer { padding: 10px 16px; border-top: 1px solid #30363d;
    background: #161b22; }
  #sidebar h1 { font-size: 15px; padding: 0 16px 10px; color: #f0f6fc; }

  .llm-test-btn { width: 100%; font-size: 12px; padding: 6px 0; background: transparent;
    border: 1px solid #30363d; border-radius: 5px; color: #8b949e; cursor: pointer; }
  .llm-test-btn:hover:not(:disabled) { border-color: #58a6ff; color: #58a6ff; }
  .llm-test-btn:disabled { opacity: 0.6; cursor: wait; }
  .llm-test-btn.ok { border-color: #3fb95066; color: #56d364; }
  .llm-test-btn.fail { border-color: #f8514966; color: #f85149; }
  #llm-test-detail { font-size: 11px; color: #6e7681; margin-top: 6px;
    word-break: break-all; line-height: 1.4; }

  .mode-toggle { display: flex; margin: 0 16px 12px; border: 1px solid #30363d;
                 border-radius: 6px; overflow: hidden; }
  .mode-btn { flex: 1; padding: 5px 0; font-size: 12px; text-align: center;
              cursor: pointer; background: transparent; color: #8b949e; border: none; }
  .mode-btn.active { background: #1f6feb; color: #fff; }

  #pipeline-status { padding: 2px 16px 8px; font-size: 12px; color: #8b949e; min-height: 18px;
    background: none; border: none; text-align: left; width: 100%; cursor: default;
    font-family: inherit; }
  #pipeline-status.running { color: #e3b341; cursor: pointer; }
  #pipeline-status.running:hover { color: #f0b850; }
  #pipeline-status.running::after { content: " ▾"; opacity: 0.6; font-size: 10px; }
  #pipeline-status.error { color: #f85149; }

  #pipeline-progress { padding: 6px 16px 10px; font-size: 11px; color: #c9d1d9;
    background: #0d1117; border-top: 1px solid #21262d; border-bottom: 1px solid #21262d;
    line-height: 1.6; }
  #pipeline-progress[hidden] { display: none; }
  #pipeline-progress .row { display: flex; justify-content: space-between; gap: 6px; }
  #pipeline-progress .key { color: #8b949e; }
  #pipeline-progress .val { color: #c9d1d9; text-align: right;
    overflow: hidden; text-overflow: ellipsis; max-width: 130px; white-space: nowrap; }
  #pipeline-progress .bar { background: #21262d; border-radius: 3px; height: 4px;
    margin: 4px 0; overflow: hidden; }
  #pipeline-progress .bar > div { background: #e3b341; height: 100%; transition: width 0.3s; }
  #pipeline-progress .src-row { display: flex; justify-content: space-between;
    color: #8b949e; font-size: 11px; }
  #pipeline-progress .src-row .src-name { color: #c9d1d9; }
  #pipeline-progress .src-row.error .src-name { color: #f85149; }

  .feed-source-label { padding: 12px 16px 4px; font-size: 11px;
    color: #6e7681; text-transform: uppercase; letter-spacing: 0.5px; }
  .feed-row { padding: 6px 16px; cursor: pointer; font-size: 13px;
    display: flex; align-items: center; gap: 6px; }
  .feed-row:hover { background: #21262d; }
  .feed-row.active { background: #1f6feb; color: #fff; }
  .feed-row.active .feed-count { color: #ffffffaa; }
  .feed-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .feed-count { font-size: 11px; color: #8b949e; flex-shrink: 0; }
  .feed-missing { font-size: 10px; color: #e3b341; flex-shrink: 0; }

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
  #feed-header { margin-bottom: 16px; }
  #feed-header h2 { font-size: 18px; color: #f0f6fc; }
  #feed-header .sub { font-size: 12px; color: #8b949e; margin-top: 4px; }

  .date-group { margin-bottom: 16px; border: 1px solid #30363d; border-radius: 8px;
    background: #161b22; overflow: hidden; }
  .date-group > summary { list-style: none; cursor: pointer;
    padding: 10px 14px; display: flex; align-items: center; gap: 10px;
    font-size: 14px; color: #f0f6fc; }
  .date-group > summary::-webkit-details-marker { display: none; }
  .date-group > summary::before { content: "▶"; font-size: 10px; color: #8b949e;
    transition: transform 0.15s; display: inline-block; flex-shrink: 0; }
  .date-group[open] > summary::before { transform: rotate(90deg); }
  .date-group > summary:hover { background: #1f242c; }
  .date-group .date-text { font-weight: 600; }
  .date-group .date-count { font-size: 12px; color: #8b949e; font-weight: 400;
    margin-left: auto; }
  .retry-source-btn { font-size: 11px; padding: 3px 10px; background: transparent;
    border: 1px solid #e3b34155; border-radius: 5px; color: #e3b341; cursor: pointer;
    white-space: nowrap; flex-shrink: 0; }
  .retry-source-btn:hover:not(:disabled) { background: #e3b34118; }
  .retry-source-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .date-group .cards { padding: 0 14px 14px; }

  /* ── cards ── */
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 14px 16px; margin-bottom: 12px; }
  .card-meta { font-size: 12px; color: #8b949e; margin-bottom: 6px;
               display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .badge { background: #21262d; border-radius: 4px; padding: 2px 8px; font-size: 11px; }
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

  /* ── releases ── */
  .release-group { margin-bottom: 16px; }
  .release-group > summary { list-style: none; cursor: pointer;
    font-size: 14px; font-weight: 600; color: #f0f6fc; margin-bottom: 8px;
    padding-bottom: 6px; border-bottom: 1px solid #30363d;
    display: flex; align-items: center; gap: 8px; }
  .release-group > summary::-webkit-details-marker { display: none; }
  .release-group > summary::before { content: "▶"; font-size: 10px; color: #8b949e;
    transition: transform 0.15s; display: inline-block; }
  .release-group[open] > summary::before { transform: rotate(90deg); }
  .release-group > summary a { color: #f0f6fc; }
  .release-count { font-size: 12px; color: #8b949e; font-weight: 400; }
  select.collection-action-btn { background: #161b22; }
</style>
</head>
<body>
<div id="sidebar">
  <div id="sidebar-scroll">
    <h1>📊 Finance Scraper</h1>
    <div class="mode-toggle">
      <button class="mode-btn active" id="btn-daily" onclick="setMode('daily')">日報</button>
      <button class="mode-btn" id="btn-collections" onclick="setMode('collections')">資料庫</button>
    </div>
    <button id="pipeline-status" onclick="toggleProgressPanel()"></button>
    <div id="pipeline-progress" hidden></div>
    <div id="daily-sidebar">
      <div style="padding: 4px 16px 8px">
        <button class="run-today-btn" id="run-today-btn" onclick="runToday()">▶ 蒐集今天</button>
      </div>
      <div id="feed-list"></div>
    </div>
    <div id="collections-sidebar" style="display:none">
      <div class="collection-section-label">分類</div>
      <div id="collection-list"></div>
      <div class="collection-section-label">月份</div>
      <div id="collection-month-list"></div>
    </div>
  </div>
  <div id="sidebar-footer">
    <button class="llm-test-btn" id="llm-test-btn" onclick="testLlm()">🔌 測試 LLM</button>
    <div id="llm-test-detail"></div>
  </div>
</div>
<div id="main">
  <!-- daily view -->
  <div id="daily-view">
    <div id="feed-header"></div>
    <div id="feed-content"></div>
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
// 來源 label — 從 /api/feeds 推出後備字典(實際 label 也由 server SOURCE_LABELS 帶)
const SOURCE_LABELS = {
  news: "📰 新聞",
  paper: "📄 論文",
  finance: "💰 財經",
  youtube_tech: "📺 YT 科技",
  youtube_fin: "📺 YT 財經",
  podcast_tech: "🎙️ Podcast 科技",
  podcast_fin: "🎙️ Podcast 財經",
};
// 每個 source 對應的 sidebar 分群標籤(以 medium 分,不用「科技/財經」字眼)
const SOURCE_CATEGORY = {
  news: "📰 科技新聞",
  paper: "📄 論文",
  finance: "💰 財經",
  youtube_tech: "📺 YouTube",
  youtube_fin: "📺 YouTube",
  podcast_tech: "🎙️ Podcast",
  podcast_fin: "🎙️ Podcast",
};
// FEEDS 由 /api/feeds 注入
let FEEDS = [];
// COLLECTIONS 由 /api/collections 注入；每筆含 key/label/type/months
let COLLECTIONS = [];
// type → render function；新增 collection type 時在這裡多加一筆
const COLLECTION_RENDERERS = {
  "monthly-list": renderMonthlyRepos,
  "bookmarks": renderBookmarks,
  "releases": renderReleases,
};
// releases 時間範圍下拉的當前值;切換 collection 時保留
let currentReleasesDays = 180;
// 已收藏 UID 集合 — 載入後決定每張卡的 ⭐ 是否實心
let BOOKMARKED_UIDS = new Set();
let mode = "daily";
// currentFeed: {source, feed_name} 或 {source:null, feed_name:null} 表全部
let currentFeed = { source: null, feed_name: null };
// currentFeedData: {source, feed_name, groups: [{date, events, missing}]}
let currentFeedData = null;
let currentCollection = null;       // collection 物件
let currentCollectionMonth = null;  // 'YYYY-MM'
let pollTimer = null;
let monthlyPollTimer = null;
let releasesPollTimer = null;

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
  pollReleasesStatus();
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
    const res = await fetch("/api/feeds?" + Date.now());
    const data = await res.json();
    FEEDS = data.feeds || [];
    renderFeedSidebar();
    // 預設選 currentFeed(初值是「全部」);polling 重跑後重入會保留當前選取
    await selectFeed(currentFeed.source, currentFeed.feed_name);
  } catch {
    document.getElementById("feed-content").innerHTML = '<div class="empty">尚無資料</div>';
  }
}

function feedKey(source, feed_name) {
  // sidebar dataset key — 用來標 active
  return (source || "all") + "|" + (feed_name || "");
}

function feedDisplayLabel(source, feed_name) {
  if (source === null) return "全部";
  if (source === "paper") return SOURCE_LABELS.paper + " (arxiv)";
  return SOURCE_LABELS[source]?.split(" ")[0] + " " + (feed_name || "(無 feed)");
}

function renderFeedSidebar() {
  const list = document.getElementById("feed-list");
  list.innerHTML = "";

  // 全部
  const allRow = document.createElement("div");
  allRow.className = "feed-row active";
  allRow.dataset.key = feedKey(null, null);
  const totalMissing = FEEDS.reduce((s, f) => s + (f.missing || 0), 0);
  const totalCount = FEEDS.reduce((s, f) => s + (f.count || 0), 0);
  allRow.innerHTML =
    '<span class="feed-name">📦 全部</span>' +
    '<span class="feed-count">' + totalCount + '</span>' +
    (totalMissing > 0 ? '<span class="feed-missing">!' + totalMissing + '</span>' : '');
  allRow.onclick = () => selectFeed(null, null);
  list.appendChild(allRow);

  // 依 source 分群,組內按 count 倒序(server 已排好)
  const groups = new Map();
  for (const f of FEEDS) {
    const cat = SOURCE_CATEGORY[f.source] || f.source;
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat).push(f);
  }
  for (const [cat, feeds] of groups) {
    const label = document.createElement("div");
    label.className = "feed-source-label";
    label.textContent = cat;
    list.appendChild(label);
    for (const f of feeds) {
      const row = document.createElement("div");
      row.className = "feed-row";
      row.dataset.key = feedKey(f.source, f.feed_name);
      const name = f.source === "paper" ? "arxiv" : (f.feed_name || "(無 feed)");
      row.innerHTML =
        '<span class="feed-name">' + escapeHtml(name) + '</span>' +
        '<span class="feed-count">' + f.count + '</span>' +
        (f.missing > 0 ? '<span class="feed-missing">!' + f.missing + '</span>' : '');
      row.onclick = () => selectFeed(f.source, f.feed_name);
      list.appendChild(row);
    }
  }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function selectFeed(source, feed_name) {
  currentFeed = { source, feed_name };
  document.querySelectorAll(".feed-row").forEach(x =>
    x.classList.toggle("active", x.dataset.key === feedKey(source, feed_name)));

  const params = new URLSearchParams();
  if (source !== null) params.set("source", source);
  if (feed_name !== null) params.set("feed_name", feed_name);
  params.set("_", Date.now());
  try {
    const res = await fetch("/api/feeds/events?" + params.toString());
    currentFeedData = await res.json();
    renderFeedView();
  } catch {
    document.getElementById("feed-content").innerHTML = '<div class="empty">載入失敗</div>';
  }
}

function renderFeedView() {
  const header = document.getElementById("feed-header");
  const content = document.getElementById("feed-content");
  if (!currentFeedData) { content.innerHTML = ""; return; }
  const groups = currentFeedData.groups || [];
  const total = groups.reduce((s, g) => s + g.events.length, 0);
  const missing = groups.reduce((s, g) => s + g.missing, 0);
  const title = feedDisplayLabel(currentFeedData.source, currentFeedData.feed_name);
  header.innerHTML =
    '<h2>' + escapeHtml(title) + '</h2>' +
    '<div class="sub">共 ' + total + ' 筆,涵蓋 ' + groups.length + ' 天'
      + (missing > 0 ? '，缺摘要 ' + missing + ' 筆' : '') + '</div>';

  if (!groups.length) {
    content.innerHTML = '<div class="empty">尚無資料</div>';
    return;
  }
  content.innerHTML = groups.map((g, i) => dateGroupHtml(g, i === 0)).join("");
  // 用 event delegation 接補摘要按鈕,避免把參數塞進 inline onclick
  content.onclick = (e) => {
    const btn = e.target.closest(".retry-source-btn[data-retry-date]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    retrySummary(
      btn.dataset.retryDate,
      currentFeedData.source,
      currentFeedData.feed_name,
    );
  };
}

function dateGroupHtml(g, isFirst) {
  // 摘要按鈕:在「特定 feed」(非全部)時永遠顯示,點下去強制重跑該日該 feed 全部摘要
  const showRetry = currentFeedData && currentFeedData.source !== null && g.events.length > 0;
  const retryBtn = showRetry
    ? '<button class="retry-source-btn" data-retry-date="' + g.date + '">'
      + '⚡ 摘要 ' + g.events.length + ' 篇</button>'
    : '';
  const cards = g.events.map(cardHtml).join("");
  return '<details class="date-group"' + (isFirst ? ' open' : '') + '>'
    + '<summary>'
    +   '<span class="date-text">📅 ' + g.date + '</span>'
    +   '<span class="date-count">' + g.events.length + ' 筆'
    +     (g.missing > 0 ? '，缺 ' + g.missing : '') + '</span>'
    +   retryBtn
    + '</summary>'
    + '<div class="cards">' + cards + '</div>'
    + '</details>';
}

async function reloadCurrentFeed() {
  if (!currentFeedData) return;
  await selectFeed(currentFeedData.source, currentFeedData.feed_name);
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
  if (c.type === "releases") {
    await loadReleases(currentReleasesDays);
    return;
  }
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
  if (c.key === "releases") return "追蹤 repo 的 release,依 repo 分組、近期在上";
  return "";
}

function _collectionEmptyHint(c) {
  if (c.key === "trending-repos") return "尚無資料，點右上「更新本月熱門」開始收集";
  if (c.key === "bookmarks") return "尚無收藏，去日報點 ⭐ 加入";
  if (c.key === "releases") return "尚無資料,點右上「更新 releases」開始收集";
  return "本 collection 尚無資料";
}

function renderCollectionActions() {
  const el = document.getElementById("collection-actions");
  if (!currentCollection) { el.innerHTML = ""; return; }
  if (currentCollection.key === "trending-repos") {
    el.innerHTML = `<button class="collection-action-btn" id="run-monthly-btn"
      onclick="runMonthly()">⚡ 更新本月熱門</button>`;
  } else if (currentCollection.key === "releases") {
    const days = [30, 90, 180, 365];
    const opts = days.map(d => `<option value="${d}"${d === currentReleasesDays ? " selected" : ""}>近 ${d} 天</option>`).join("");
    el.innerHTML = `
      <select id="releases-days" class="collection-action-btn"
        onchange="changeReleasesDays(this.value)">${opts}</select>
      <button class="collection-action-btn" id="run-releases-btn"
        onclick="runReleases()">⚡ 更新 releases</button>`;
  } else {
    el.innerHTML = "";
  }
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

// ── LLM health check ──────────────────────────────────────────────────────
async function testLlm() {
  const btn = document.getElementById("llm-test-btn");
  const detail = document.getElementById("llm-test-detail");
  btn.disabled = true;
  btn.className = "llm-test-btn";
  btn.textContent = "🔌 測試中…";
  detail.textContent = "";
  try {
    const res = await fetch("/api/llm-health?" + Date.now());
    const j = await res.json();
    if (j.ok) {
      btn.classList.add("ok");
      btn.textContent = "✅ LLM 通";
    } else {
      btn.classList.add("fail");
      btn.textContent = "❌ LLM 不通";
    }
    detail.textContent = j.base_url + "  / " + j.model;
  } catch (e) {
    btn.classList.add("fail");
    btn.textContent = "❌ 無法呼叫 API";
    detail.textContent = String(e);
  }
  btn.disabled = false;
}

// ── daily run / retry ─────────────────────────────────────────────────────
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

async function retrySummary(date, source, feed_name) {
  const params = new URLSearchParams({ date, source });
  if (feed_name !== null && feed_name !== undefined) params.set("feed_name", feed_name);
  const label = source + (feed_name ? "/" + feed_name : "");
  updateStatusBar({ running: true, date, mode: "retry:" + label });
  try {
    const res = await fetch("/api/retry-summary?" + params.toString(), { method: "POST" });
    const j = await res.json();
    if (!res.ok) { updateStatusBar({ running: false, error: j.error || "補摘要失敗" }); return; }
    startPolling();
  } catch {
    updateStatusBar({ running: false, error: "無法連線" });
  }
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
        // 重新拉 sidebar(數字更新)與當前 feed
        await initDaily();
      }
    } catch { stopPolling(); }
  }, 2000);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function updateStatusBar(s) {
  const el = document.getElementById("pipeline-status");
  const panel = document.getElementById("pipeline-progress");
  const btns = document.querySelectorAll(".retry-source-btn, .run-today-btn");
  if (s.running) {
    const label = s.mode && s.mode.startsWith("retry:") ? `補摘要 ${s.mode.split(":")[1]}` : "蒐集中";
    el.className = "running"; el.textContent = `⚡ ${label} ${s.date || ""}`;
    btns.forEach(b => b.disabled = true);
    renderProgressPanel(s);
  } else {
    if (s.error) { el.className = "error"; el.textContent = `❌ ${s.error}`; }
    else { el.className = ""; el.textContent = ""; }
    btns.forEach(b => b.disabled = false);
    // 不在跑時收起並清空
    panel.hidden = true;
    panel.innerHTML = "";
  }
}

let progressPanelOpen = false;
function toggleProgressPanel() {
  const panel = document.getElementById("pipeline-progress");
  const el = document.getElementById("pipeline-status");
  if (el.className !== "running") return;  // 沒在跑就不展開
  progressPanelOpen = !progressPanelOpen;
  panel.hidden = !progressPanelOpen;
}

function renderProgressPanel(s) {
  const panel = document.getElementById("pipeline-progress");
  const p = s.progress;
  if (!p) {
    panel.innerHTML = '<div class="row"><span class="key">尚未取得進度…</span></div>';
    return;
  }
  // retry 模式:有 total/done/updated/failed/current
  // pipeline 模式:有 kind="pipeline" + phase + sources_done/current_source/processed
  let html = "";
  if (p.kind === "pipeline") {
    const phaseLabel = {
      collect: "🌐 收集中", filter: "🔍 過濾", classify: "🏷️ 分類",
      process: "✍️ 處理(摘要/翻譯)", summarize: "📋 日報", output: "📤 輸出",
      done: "✅ 完成",
    }[p.phase] || p.phase;
    html += '<div class="row"><span class="key">階段</span>'
      + '<span class="val">' + escapeHtml(phaseLabel) + '</span></div>';
    if (p.current_source) {
      html += '<div class="row"><span class="key">目前</span>'
        + '<span class="val">' + escapeHtml(p.current_source) + '</span></div>';
    }
    if (p.total_raw != null) {
      html += '<div class="row"><span class="key">原始事件</span>'
        + '<span class="val">' + p.total_raw + '</span></div>';
    }
    if (p.processed != null && p.total_classified != null) {
      const pct = p.total_classified ? Math.round(p.processed * 100 / p.total_classified) : 0;
      html += '<div class="row"><span class="key">處理</span>'
        + '<span class="val">' + p.processed + ' / ' + p.total_classified + '</span></div>';
      html += '<div class="bar"><div style="width:' + pct + '%"></div></div>';
    }
    const sd = p.sources_done || {};
    const keys = Object.keys(sd);
    if (keys.length) {
      html += '<div class="key" style="margin-top:6px">已收集</div>';
      for (const k of keys) {
        const v = sd[k];
        const isErr = typeof v === "string" && v.startsWith("error");
        html += '<div class="src-row' + (isErr ? ' error' : '') + '">'
          + '<span class="src-name">' + escapeHtml(k) + '</span>'
          + '<span>' + (isErr ? "失敗" : v + " 筆") + '</span></div>';
      }
    }
  } else if (p.total != null) {
    // retry
    const pct = p.total ? Math.round(p.done * 100 / p.total) : 0;
    html += '<div class="row"><span class="key">進度</span>'
      + '<span class="val">' + (p.done || 0) + ' / ' + p.total + '</span></div>';
    html += '<div class="bar"><div style="width:' + pct + '%"></div></div>';
    html += '<div class="row"><span class="key">成功 / 失敗</span>'
      + '<span class="val">' + (p.updated || 0) + ' / ' + (p.failed || 0) + '</span></div>';
    if (p.current) {
      html += '<div class="row"><span class="key">當前</span>'
        + '<span class="val" title="' + escapeHtml(p.current) + '">'
        + escapeHtml(p.current) + '</span></div>';
    }
  } else {
    html = '<div class="row"><span class="key">尚未取得進度…</span></div>';
  }
  panel.innerHTML = html;
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

// ── releases: data flow ───────────────────────────────────────────────────
async function loadReleases(days) {
  try {
    const res = await fetch(`/api/collections/releases?days=${days}&_=${Date.now()}`);
    if (!res.ok) { renderCollectionEmpty("載入失敗"); return; }
    renderReleases(await res.json());
  } catch (e) { renderCollectionEmpty("載入失敗:" + e.message); }
}

function changeReleasesDays(v) {
  currentReleasesDays = parseInt(v, 10) || 180;
  loadReleases(currentReleasesDays);
}

function renderReleases(data) {
  const el = document.getElementById("collection-content");
  const items = data.items || [];
  if (!items.length) {
    el.innerHTML = `<div class="empty">近 ${data.days} 天無 release</div>`;
    return;
  }
  // 依 repo 分組,組內已是 published_at 倒序
  const groups = new Map();
  for (const it of items) {
    if (!groups.has(it.repo)) groups.set(it.repo, []);
    groups.get(it.repo).push(it);
  }
  const header = `<div style="font-size:12px;color:#8b949e;margin-bottom:16px">
    共 ${items.length} 筆 release,涵蓋 ${groups.size} 個 repo,近 ${data.days} 天
  </div>`;
  const parts = [];
  for (const [repo, rels] of groups.entries()) {
    parts.push(`<details class="release-group">
      <summary>📦 <a href="https://github.com/${esc(repo)}" target="_blank"
        onclick="event.stopPropagation()">${esc(repo)}</a>
        <span class="release-count">${rels.length} 個</span></summary>
      ${rels.map(releaseCardHtml).join("")}
    </details>`);
  }
  el.innerHTML = header + parts.join("");
}

function releaseCardHtml(r) {
  const date = (r.published_at || "").slice(0, 10);
  const pre = r.is_prerelease ? `<span class="badge" style="background:#f8514933;color:#ff7b72">pre-release</span>` : "";
  const tag = r.tag ? `<span class="badge">${esc(r.tag)}</span>` : "";
  const summary = r.ai_summary
    ? `<div class="card-summary">${esc(r.ai_summary)}</div>`
    : r.body ? `<div class="card-summary card-body-preview">${esc(r.body.slice(0, 280))}…</div>` : "";
  return `<div class="card">
    <div class="card-meta">
      ${tag}
      ${pre}
      <span style="color:#8b949e">📅 ${date}</span>
    </div>
    <div class="card-title"><a href="${esc(r.url)}" target="_blank">${esc(r.name)}</a></div>
    ${summary}
  </div>`;
}

// ── releases: run & polling ───────────────────────────────────────────────
async function runReleases() {
  updateReleasesStatus({ running: true, lookback: currentReleasesDays });
  try {
    const res = await fetch(`/api/run-releases?lookback=${currentReleasesDays}`, { method: "POST" });
    const j = await res.json();
    if (!res.ok) { updateReleasesStatus({ running: false, error: j.error || "失敗" }); return; }
    startReleasesPolling();
  } catch {
    updateReleasesStatus({ running: false, error: "無法連線" });
  }
}

async function pollReleasesStatus() {
  try {
    const res = await fetch("/api/releases-status");
    if (!res.ok) return;
    const s = await res.json();
    updateReleasesStatus(s);
    if (s.running) startReleasesPolling();
  } catch {}
}

function startReleasesPolling() {
  if (releasesPollTimer) return;
  releasesPollTimer = setInterval(async () => {
    try {
      const s = await (await fetch("/api/releases-status")).json();
      updateReleasesStatus(s);
      if (!s.running) {
        stopReleasesPolling();
        if (currentCollection && currentCollection.key === "releases") {
          await loadReleases(currentReleasesDays);
        }
      }
    } catch { stopReleasesPolling(); }
  }, 3000);
}

function stopReleasesPolling() {
  if (releasesPollTimer) { clearInterval(releasesPollTimer); releasesPollTimer = null; }
}

function updateReleasesStatus(s) {
  const el = document.getElementById("collection-status");
  const btn = document.getElementById("run-releases-btn");
  if (s.running) {
    el.className = "running"; el.textContent = `⚡ 收集 releases (近 ${s.lookback || "?"} 天)...`;
    if (btn) btn.disabled = true;
  } else if (s.error) {
    el.className = "error"; el.textContent = `❌ 失敗:${s.error}`;
    if (btn) btn.disabled = false;
  } else {
    if (btn) btn.disabled = false;
    if (el.textContent.startsWith("⚡ 收集 releases")) {
      el.className = ""; el.textContent = "";
    }
  }
}

// ── shared utils ──────────────────────────────────────────────────────────
function esc(s) {
  return (s || "").replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function cardHtml(e) {
  let origin = "";
  if (e.source === "paper") origin = esc((e.categories || []).slice(0, 2).join(", "));
  else origin = esc(e.feed_name || "");  // news / finance / youtube_* / podcast_* 都用 feed_name
  const noSummary = !e.ai_summary;
  const isOn = e.uid && BOOKMARKED_UIDS.has(e.uid);
  const star = e.uid
    ? `<button class="bookmark-btn ${isOn ? "on" : ""}" data-uid="${esc(e.uid)}"
        title="${isOn ? "取消收藏" : "收藏"}"
        onclick="toggleBookmark(this, '${esc(e.uid)}')">★</button>`
    : "";
  const date = (e.created_at || "").slice(0, 10);
  const meta = [
    `<span class="badge src-${e.source}">${e.source}</span>`,
    origin ? `<span>${origin}</span>` : "",
    date ? `<span style="color:#8b949e">📅 ${date}</span>` : "",
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
  // 從目前 feed 資料(各日期 group)中扁平化找事件 — 避免把 JSON 塞 HTML attribute
  const allEvents = ((currentFeedData && currentFeedData.groups) || [])
    .flatMap(g => g.events);
  const event = allEvents.find(e => e.uid === uid);
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
  const order = ["news", "paper", "finance", "youtube_tech", "youtube_fin",
                 "podcast_tech", "podcast_fin", "other"];
  const sections = order.filter(k => groups[k]).map(k => {
    const label = SOURCE_LABELS[k] || k;
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
  const publishedDate = (b.event_created_at || "").slice(0, 10);
  const meta = [
    `<span class="badge src-${b.source}">${b.source}</span>`,
    b.origin ? `<span>${esc(b.origin)}</span>` : "",
    publishedDate ? `<span style="color:#8b949e">📅 ${publishedDate}</span>` : "",
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
