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
  /* 蒐集鈕 + 狀態列 + 進度面板都搬到 footer,固定在側邊欄底部不跟著捲動。
     縱向堆疊 + 適度 gap,不會跟 LLM 測試擠在一起 */
  #sidebar-footer { padding: 10px 12px; border-top: 1px solid #30363d;
    background: #161b22; display: flex; flex-direction: column; gap: 8px; }
  #sidebar h1 { font-size: 17px; font-weight: 700; padding: 4px 16px 12px;
    color: #f0f6fc; letter-spacing: 0.2px; }

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

  /* 狀態列 — 沒在跑時為空字串,用 :empty 隱掉避免在 footer 留空隙 */
  #pipeline-status { padding: 4px 4px; font-size: 12px; color: #8b949e;
    background: none; border: none; text-align: left; width: 100%; cursor: default;
    font-family: inherit; line-height: 1.4; }
  #pipeline-status:empty { display: none; }
  #pipeline-status.running { color: #e3b341; cursor: pointer; }
  #pipeline-status.running:hover { color: #f0b850; }
  #pipeline-status.running::after { content: " ▾"; opacity: 0.6; font-size: 10px; }
  #pipeline-status.error { color: #f85149; }

  /* 進度面板 — 在 footer 內,給 card 樣式取代原本的 「橫條夾在 sidebar 中段」設計 */
  #pipeline-progress { padding: 8px 10px; font-size: 11px; color: #c9d1d9;
    background: #0d1117; border: 1px solid #21262d; border-radius: 6px;
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
    color: #6e7681; text-transform: uppercase; letter-spacing: 0.5px;
    display: flex; align-items: center; gap: 4px; }
  .feed-source-info { background: transparent; border: none; cursor: pointer;
    color: #6e7681; font-size: 12px; padding: 0 4px; line-height: 1;
    font-family: inherit; }
  .feed-source-info:hover { color: #8b949e; }
  .info-popover { position: fixed; background: #161b22; border: 1px solid #30363d;
    border-radius: 6px; padding: 10px 28px 10px 12px; max-width: 320px; z-index: 1000;
    font-size: 12px; color: #c9d1d9; line-height: 1.6; box-shadow: 0 4px 12px #0008;
    text-transform: none; letter-spacing: normal; }
  .info-popover strong { color: #58a6ff; }
  .info-popover code { background: #30363d; padding: 0 4px; border-radius: 3px;
    font-size: 11px; }
  .info-popover .info-close { position: absolute; top: 4px; right: 6px;
    background: transparent; border: none; color: #6e7681; cursor: pointer;
    font-size: 14px; line-height: 1; padding: 4px 6px; font-family: inherit; }
  .info-popover .info-close:hover { color: #f0f6fc; }
  /* 結構化排版:標題置頂,每列「標籤 + 值」對齊好掃讀 */
  .info-popover .info-title { font-size: 13px; font-weight: 600;
    color: #58a6ff; margin-bottom: 10px; padding-right: 16px; }
  .info-popover .info-row { display: flex; gap: 10px; line-height: 1.55;
    margin-bottom: 3px; font-size: 12px; }
  .info-popover .info-row:last-child { margin-bottom: 0; }
  .info-popover .info-row .info-label { color: #6e7681; flex-shrink: 0;
    width: 38px; }
  .info-popover .info-row .info-value { flex: 1; color: #c9d1d9; }
  .info-popover .info-row .info-value code { background: #30363d;
    padding: 0 4px; border-radius: 3px; font-size: 11px; }
  .feed-row { padding: 6px 16px; cursor: pointer; font-size: 13px;
    display: flex; align-items: center; gap: 6px; }
  .feed-row:hover { background: #21262d; }
  .feed-row.active { background: #1f6feb; color: #fff; }
  .feed-row.active .feed-count { color: #ffffffaa; }
  .feed-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .feed-count { font-size: 11px; color: #8b949e; flex-shrink: 0; }
  /* 健康度小圓點:綠=全部已摘要,黃=部分缺,紅=多數/全缺。title 帶實際數字 */
  .feed-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
    display: inline-block; }
  .feed-dot.ok { background: #3fb95066; }
  .feed-dot.warn { background: #e3b341; }
  .feed-dot.bad { background: #f85149; }
  .feed-dot.info { background: #58a6ff; }
  .feed-row.active .feed-dot.ok { background: #ffffff66; }

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
  /* margin:auto 讓主區在寬螢幕(>1110px)置中,避免右側大片空白 */
  #main { flex: 1; padding: 24px 32px; max-width: 900px; margin: 0 auto; }
  #feed-header { margin-bottom: 18px; }
  #feed-header h2 { font-size: 22px; font-weight: 700; color: #f0f6fc;
    line-height: 1.3; }
  #feed-header .sub { font-size: 12px; color: #8b949e; margin-top: 6px; }
  #feed-header .sub strong { color: #c9d1d9; font-weight: 600; }

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
  .stt-btn { font-size: 11px; padding: 3px 10px; background: transparent;
    border: 1px solid #d2992288; border-radius: 4px; color: #e3b341;
    cursor: pointer; font-family: inherit; }
  .stt-btn:hover:not(:disabled) { background: #d2992218; }
  .stt-btn:disabled { opacity: 0.6; cursor: not-allowed; }

  /* date-group 上的兩個 stage 鈕:翻譯(黃)/摘要(藍)。
     ≥1 時帶 border 凸顯,=0 時隱藏(沒事可做就別占位)。 */
  .stage-btn { font-size: 11px; padding: 3px 10px; background: transparent;
    border-radius: 5px; cursor: pointer; white-space: nowrap; flex-shrink: 0;
    font-family: inherit; }
  .stage-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .stage-btn[hidden] { display: none; }
  .stage-btn.translate { border: 1px solid #e3b34155; color: #e3b341; }
  .stage-btn.translate:hover:not(:disabled) { background: #e3b34118; }
  .stage-btn.summarize { border: 1px solid #1f6feb88; color: #58a6ff; }
  .stage-btn.summarize:hover:not(:disabled) { background: #1f6feb18; }
  .date-group .cards { padding: 0 14px 14px; }

  /* ── cards ── */
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 12px 14px; margin-bottom: 10px; }
  /* meta 分兩區：左 = 身份(來源/feed/分類/狀態)，右 = 動作(STT/收藏)
     避免動作鈕跟識別資訊混在同一視覺層級 */
  .card-meta { font-size: 12px; color: #8b949e; margin-bottom: 8px;
               display: flex; gap: 8px; align-items: center; }
  .card-meta-left { display: flex; flex-wrap: wrap; gap: 6px;
    align-items: center; flex: 1; min-width: 0; }
  .card-meta-actions { display: flex; gap: 6px; align-items: center;
    flex-shrink: 0; margin-left: auto; }
  .card-meta-actions .bookmark-btn { margin-left: 0; }
  .badge { background: #21262d; border-radius: 4px; padding: 2px 8px; font-size: 11px; }
  .badge.src-news { background: #d2992233; color: #e3b341; }
  .badge.src-paper { background: #3fb95033; color: #56d364; }
  .badge.src-finance { background: #39c5cf33; color: #39c5cf; }
  .badge.impact-Breaking { background: #f8514933; color: #f85149; }
  .badge.impact-High { background: #db6d2833; color: #db6d28; }
  .badge.no-summary { background: #30363d; color: #8b949e; font-style: italic; }
  /* 統一資料流的階段狀態徽章 — 顏色語意:STT=橙(需採集)、翻譯=黃、摘要=藍 */
  .badge.stage-stt { background: #d2992233; color: #e3b341; }
  .badge.stage-translate { background: #e3b34122; color: #e3b341; }
  .badge.stage-summarize { background: #1f6feb22; color: #58a6ff; }
  .badge.stage-empty { background: #30363d; color: #6e7681; }
  .badge.rank { background: #6e40c933; color: #bc8cff; font-weight: 600; }
  .badge.lang { background: #21262d; color: #8b949e; }
  .card-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
  .card-summary { font-size: 13px; color: #c9d1d9; line-height: 1.6; }
  .card-body-preview { color: #8b949e; }
  .card-tags { margin-top: 8px; font-size: 12px; color: #8b949e; }
  .empty { color: #8b949e; padding: 40px 0; text-align: center; }
  /* 空狀態升級版:大圖示 + 主標 + 副標 + 可選 CTA */
  .empty-rich { text-align: center; padding: 60px 20px; color: #8b949e; }
  .empty-rich .empty-icon { font-size: 48px; margin-bottom: 14px; opacity: 0.6; }
  .empty-rich .empty-title { font-size: 16px; color: #c9d1d9; margin-bottom: 6px;
    font-weight: 600; }
  .empty-rich .empty-sub { font-size: 13px; margin-bottom: 20px; line-height: 1.6; }
  .empty-cta-btn { font-size: 13px; padding: 8px 18px; background: transparent;
    border: 1px solid #1f6feb88; border-radius: 5px; color: #58a6ff;
    cursor: pointer; font-family: inherit; }
  .empty-cta-btn:hover { background: #1f6feb18; }

  .bookmark-btn { background: transparent; border: none; cursor: pointer;
    font-size: 14px; color: #6e7681; padding: 0 4px; line-height: 1;
    margin-left: auto; }
  .bookmark-btn:hover { color: #e3b341; }
  .bookmark-btn.on { color: #e3b341; }
  .bookmark-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  /* 卡片刪除鈕 — 放在 source badge 旁,平常低調(灰半透明),hover 才轉紅警示 */
  .card-delete-btn { background: transparent; border: none; cursor: pointer;
    font-size: 12px; color: #6e7681; padding: 0 4px; line-height: 1;
    font-family: inherit; opacity: 0.45; }
  .card-delete-btn:hover { color: #f85149; opacity: 1; }
  .card-delete-btn:disabled { opacity: 0.25; cursor: not-allowed; }

  /* ── collection header ── */
  #collection-header { display: flex; align-items: center; justify-content: space-between;
                       margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
  #collection-header h2 { font-size: 16px; color: #f0f6fc; }
  .collection-action-btn { font-size: 12px; padding: 5px 12px; background: transparent;
    border: 1px solid #1f6feb88; border-radius: 5px; color: #58a6ff; cursor: pointer; }
  .collection-action-btn:hover:not(:disabled) { background: #1f6feb18; }
  .collection-action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  /* days 下拉是被動選擇器、不是動作，改成中性灰避免跟「更新」鈕視覺競爭 */
  select.collection-action-btn { background: #161b22; border-color: #30363d;
    color: #c9d1d9; }
  select.collection-action-btn:hover { border-color: #8b949e; background: transparent; }
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

  /* ── responsive ──────────────────────────────────────────────────────
     ≤900px: sidebar 變抽屜(預設收起)+ 主區全寬 + 頂部 hamburger toolbar
     ≤600px: drawer 改全寬蓋上(手機) */
  #mobile-topbar, #sidebar-backdrop { display: none; }
  @media (max-width: 900px) {
    body { display: block; }
    #sidebar { position: fixed; left: 0; top: 0; height: 100vh;
      width: 280px; max-width: 85vw; transform: translateX(-100%);
      transition: transform 0.2s ease; z-index: 100;
      box-shadow: 4px 0 16px #000a; }
    #sidebar.open { transform: translateX(0); }
    #main { max-width: none; padding: 0 16px 24px; }
    #mobile-topbar { display: flex; position: sticky; top: 0;
      background: #0d1117; z-index: 50; padding: 10px 16px;
      border-bottom: 1px solid #21262d; align-items: center; gap: 12px;
      margin: 0 -16px 16px; }
    #mobile-topbar .hamburger { background: transparent;
      border: 1px solid #30363d; border-radius: 5px; color: #c9d1d9;
      padding: 4px 12px; font-size: 18px; cursor: pointer;
      line-height: 1; font-family: inherit; }
    #mobile-topbar .hamburger:hover { border-color: #58a6ff; color: #58a6ff; }
    #mobile-topbar .title { font-size: 14px; color: #f0f6fc; font-weight: 600; }
    #sidebar-backdrop { position: fixed; inset: 0; background: #000a;
      z-index: 99; }
    #sidebar-backdrop.show { display: block; }
  }
  @media (max-width: 600px) {
    #sidebar { width: 100vw; max-width: 100vw; }
    #main { padding: 0 12px 16px; }
    #mobile-topbar { margin: 0 -12px 12px; padding: 10px 12px; }
    .card { padding: 10px 12px; }
    #feed-header h2 { font-size: 16px; }
    #collection-header { flex-direction: column; align-items: stretch; }
    #collection-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  }
</style>
</head>
<body>
<div id="mobile-topbar">
  <button class="hamburger" onclick="toggleSidebar()" aria-label="開啟側欄">☰</button>
  <span class="title">📊 Finance Scraper</span>
</div>
<div id="sidebar-backdrop" onclick="toggleSidebar()"></div>
<div id="sidebar">
  <div id="sidebar-scroll">
    <h1>📊 Finance Scraper</h1>
    <div class="mode-toggle">
      <button class="mode-btn active" id="btn-daily" onclick="setMode('daily')">日報</button>
      <button class="mode-btn" id="btn-collections" onclick="setMode('collections')">資料庫</button>
    </div>
    <div id="daily-sidebar">
      <div id="feed-list"></div>
    </div>
    <div id="collections-sidebar" style="display:none">
      <div class="collection-section-label">分類</div>
      <div id="collection-list"></div>
      <div class="collection-section-label" id="collection-month-label">月份</div>
      <div id="collection-month-list"></div>
    </div>
  </div>
  <div id="sidebar-footer">
    <!-- 蒐集動作 + 進度狀態移到 footer:常駐視覺位置,切換 daily/collections 不消失 -->
    <button class="run-today-btn" id="run-today-btn" onclick="runToday()">▶ 蒐集今天</button>
    <button id="pipeline-status" onclick="toggleProgressPanel()"></button>
    <div id="pipeline-progress" hidden></div>
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
// 每個分類的處理鏈 / 手動觸發說明 — 點 ⓘ 顯示
// 結構化的 source 說明 — 每個 source 統一四欄(來源/蒐集/流程/備註),
// 渲染時自動拼成「標籤 + 值」表格,前端只負責照 schema 畫。
const SOURCE_INFO_TEXT = {
  news: {
    title: "📰 新聞",
    rows: [
      ["來源", "HackerNews + RSS (TechCrunch / The Verge)"],
      ["蒐集", "自動補爬全文 <code>fetch_body</code>"],
      ["流程", "🌐 翻譯 → 📝 摘要"],
      ["備註", "LLM 失敗 fallback Google 翻譯"],
    ],
  },
  paper: {
    title: "📄 論文",
    rows: [
      ["來源", "arXiv + HuggingFace Daily Papers"],
      ["蒐集", "title + abstract (英文)"],
      ["流程", "🌐 翻譯 → 📝 摘要"],
    ],
  },
  finance: {
    title: "💰 財經",
    rows: [
      ["來源", "CNBC / Yahoo / MarketWatch / 經濟日報"],
      ["流程", "🌐 翻譯 → 📝 摘要"],
      ["備註", "中文 feed (經濟日報) 跳翻譯,直接摘要"],
    ],
  },
  media: {
    title: "📺 YouTube / 🎙️ Podcast",
    rows: [
      ["蒐集", "只取 link + title,body 為空"],
      ["流程", "🎙️ STT → 🌐 翻譯 → 📝 摘要"],
      ["STT", "每張卡片右上鈕單獨觸發 (可並行)"],
      ["備註", "中文頻道 STT 後跳翻譯;url 不重蒐集"],
    ],
  },
};

function buildInfoHtml(info) {
  const rows = info.rows.map(([k, v]) =>
    '<div class="info-row"><span class="info-label">' + k +
    '</span><span class="info-value">' + v + '</span></div>'
  ).join("");
  return '<div class="info-title">' + info.title + '</div>' + rows;
}

function infoKeyForSource(source) {
  if (source.startsWith("youtube_") || source.startsWith("podcast_")) return "media";
  return source;  // news / paper / finance
}

let _infoPopover = null;
function closeSourceInfo() {
  if (_infoPopover) { _infoPopover.remove(); _infoPopover = null; }
}
function toggleSourceInfo(ev, btn) {
  ev.stopPropagation();
  const wasOpen = _infoPopover && _infoPopover.dataset.forKey === btn.dataset.infoKey;
  closeSourceInfo();
  if (wasOpen) return;  // 點同一個再點 = 關閉
  const info = SOURCE_INFO_TEXT[btn.dataset.infoKey];
  if (!info) return;
  const pop = document.createElement("div");
  pop.className = "info-popover";
  pop.dataset.forKey = btn.dataset.infoKey;
  // ✕ 鈕本身不需要 onclick — 任何 click 都會觸發既有的 document close handler
  pop.innerHTML = '<button class="info-close" aria-label="關閉">✕</button>' + buildInfoHtml(info);
  document.body.appendChild(pop);
  const r = btn.getBoundingClientRect();
  // 預設貼右側,若會超出視窗就改成貼左側下方
  const popW = pop.offsetWidth;
  let left = r.right + 6;
  if (left + popW > window.innerWidth - 8) left = Math.max(8, r.left - popW - 6);
  pop.style.left = left + "px";
  pop.style.top = r.top + "px";
  _infoPopover = pop;
  // 下個 tick 才掛 click,避免 stopPropagation 後仍命中自己
  setTimeout(() => document.addEventListener("click", closeSourceInfo, { once: true }), 0);
}

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

// ── mobile drawer ─────────────────────────────────────────────────────────
function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const bd = document.getElementById('sidebar-backdrop');
  const isOpen = sb.classList.toggle('open');
  bd.classList.toggle('show', isOpen);
}
function closeMobileSidebar() {
  if (!window.matchMedia('(max-width: 900px)').matches) return;
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-backdrop').classList.remove('show');
}
// 點 sidebar 內任何「選擇類」項目就自動關抽屜 — 避免每個 select 函式都要 patch
// script 在 body 尾,DOM 已就緒,直接綁
document.getElementById('sidebar').addEventListener('click', (ev) => {
  if (ev.target.closest('.feed-row, .month-row, .collection-row')) {
    closeMobileSidebar();
  }
});

// ── mode toggle ───────────────────────────────────────────────────────────
function setMode(m) {
  mode = m;
  document.getElementById("btn-daily").classList.toggle("active", m === "daily");
  document.getElementById("btn-collections").classList.toggle("active", m === "collections");
  document.getElementById("daily-sidebar").style.display = m === "daily" ? "" : "none";
  document.getElementById("collections-sidebar").style.display = m === "collections" ? "" : "none";
  document.getElementById("daily-view").style.display = m === "daily" ? "" : "none";
  document.getElementById("collection-view").style.display = m === "collections" ? "" : "none";
  // run-today 只在 daily 有意義;pipeline-status 留下來 — 蒐集/翻譯/摘要的進度
  // 跨 mode 也該被看到,不然切到 collections 就以為任務消失了
  document.getElementById("run-today-btn").style.display = m === "daily" ? "" : "none";
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

// 統一資料流:看 stt/translate/summarize 各段卡多少。顏色 = 最重的那段
//   red    需 STT(主因)
//   yellow 需翻譯(主因)
//   blue   需摘要(主因)
//   green  全部完成
function feedHealth(f) {
  const count = f.count || 0;
  const stt = f.missing_body || 0;
  const tr  = f.needs_translate || 0;
  const su  = f.needs_summary || 0;
  if (!count) return { cls: "ok", title: "尚無資料" };
  if (stt === 0 && tr === 0 && su === 0) return { cls: "ok", title: "全部完成" };
  const parts = [];
  if (stt > 0) parts.push("STT " + stt);
  if (tr > 0)  parts.push("翻譯 " + tr);
  if (su > 0)  parts.push("摘要 " + su);
  const title = "卡關:" + parts.join(" / ") + " (共 " + count + ")";
  // 優先序:STT > 翻譯 > 摘要 — 越前面越紅,因為越後段才會卡
  if (stt >= tr && stt >= su && stt > 0) return { cls: "bad", title };
  if (tr >= su && tr > 0) return { cls: "warn", title };
  return { cls: "info", title };
}

function renderFeedSidebar() {
  const list = document.getElementById("feed-list");
  list.innerHTML = "";

  // 全部
  const allRow = document.createElement("div");
  allRow.className = "feed-row active";
  allRow.dataset.key = feedKey(null, null);
  const totals = FEEDS.reduce((acc, f) => ({
    count: acc.count + (f.count || 0),
    missing_body: acc.missing_body + (f.missing_body || 0),
    needs_translate: acc.needs_translate + (f.needs_translate || 0),
    needs_summary: acc.needs_summary + (f.needs_summary || 0),
  }), { count: 0, missing_body: 0, needs_translate: 0, needs_summary: 0 });
  const allH = feedHealth(totals);
  allRow.title = allH.title;
  allRow.innerHTML =
    '<span class="feed-dot ' + allH.cls + '"></span>' +
    '<span class="feed-name">📦 全部</span>' +
    '<span class="feed-count">' + totals.count + '</span>';
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
    const infoKey = infoKeyForSource(feeds[0].source);
    label.innerHTML = '<span>' + escapeHtml(cat) + '</span>' +
      '<button class="feed-source-info" data-info-key="' + infoKey +
      '" onclick="toggleSourceInfo(event, this)" title="處理鏈與 fallback 說明">ⓘ</button>';
    list.appendChild(label);
    for (const f of feeds) {
      const row = document.createElement("div");
      row.className = "feed-row";
      row.dataset.key = feedKey(f.source, f.feed_name);
      const name = f.source === "paper" ? "arxiv" : (f.feed_name || "(無 feed)");
      const h = feedHealth(f);
      row.title = h.title;
      row.innerHTML =
        '<span class="feed-dot ' + h.cls + '"></span>' +
        '<span class="feed-name">' + escapeHtml(name) + '</span>' +
        '<span class="feed-count">' + f.count + '</span>';
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
    '<div class="sub">共 <strong>' + total + '</strong> 筆,涵蓋 <strong>'
      + groups.length + '</strong> 天'
      + (missing > 0 ? '，缺摘要 <strong>' + missing + '</strong> 筆' : '')
      + '</div>';

  if (!groups.length) {
    content.innerHTML = '<div class="empty">尚無資料</div>';
    return;
  }
  content.innerHTML = groups.map((g, i) => dateGroupHtml(g, i === 0)).join("");
  // event delegation:翻譯/摘要兩種 stage 鈕共用同一 handler,從 data-stage 區分
  content.onclick = (e) => {
    const btn = e.target.closest(".stage-btn[data-stage]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    triggerStage(
      btn.dataset.stage,
      btn.dataset.date,
      currentFeedData.source,
      currentFeedData.feed_name,
    );
  };
}

function dateGroupHtml(g, isFirst) {
  // 統一資料流:每個 date-group 上兩個 stage 鈕。
  //   翻譯(黃):body 有但 body_lang ≠ 'zh' 的數量(g.needs_translate)
  //   摘要(藍):body_lang='zh' 但無 ai_summary 的數量(g.needs_summary)
  // 都是 0 就 hidden。全部視圖(source=null)也顯示:點下去 = 那一天、所有來源
  // 一起翻譯/摘要(後端 by-day 已序列+節流,避免一次塞爆 LLM)。範圍仍限單日。
  const scoped = currentFeedData && g.events.length > 0;
  const nT = g.needs_translate || 0;
  const nS = g.needs_summary || 0;
  const btns = scoped
    ? '<button class="stage-btn translate" data-stage="translate" data-date="' + g.date + '"'
        + (nT > 0 ? '' : ' hidden')
        + ' title="把 ' + nT + ' 篇英文 body 翻成中文">🌐 翻譯 ' + nT + '</button>'
      + '<button class="stage-btn summarize" data-stage="summarize" data-date="' + g.date + '"'
        + (nS > 0 ? '' : ' hidden')
        + ' title="對 ' + nS + ' 篇中文 body 產生摘要">📝 摘要 ' + nS + '</button>'
    : '';
  const cards = g.events.map(cardHtml).join("");
  return '<details class="date-group"' + (isFirst ? ' open' : '') + '>'
    + '<summary>'
    +   '<span class="date-text">📅 ' + g.date + '</span>'
    +   '<span class="date-count">' + g.events.length + ' 筆</span>'
    +   btns
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
  const label = document.getElementById("collection-month-label");
  list.innerHTML = "";
  const months = (currentCollection && currentCollection.months) || [];
  // 沒有月份(如 Releases)就連 section 標籤一起隱藏,避免出現孤伶伶的「月份」字樣
  label.style.display = months.length ? "" : "none";
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
    document.getElementById("collection-content").innerHTML = _collectionEmptyHtml(c);
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

// 通用 rich empty 模板:大圖示 + 主標 + 副標 + 可選 CTA
function richEmptyHtml(opts) {
  const cta = opts.cta
    ? '<button class="empty-cta-btn" onclick="' + opts.cta.onclick + '">'
      + esc(opts.cta.label) + '</button>'
    : '';
  return '<div class="empty-rich">'
    + '<div class="empty-icon">' + opts.icon + '</div>'
    + '<div class="empty-title">' + esc(opts.title) + '</div>'
    + (opts.sub ? '<div class="empty-sub">' + esc(opts.sub) + '</div>' : '')
    + cta + '</div>';
}

function _collectionEmptyHtml(c) {
  if (c.key === "trending-repos") return richEmptyHtml({
    icon: "🚀", title: "尚無熱門 repo 資料",
    sub: "點右上「⚡ 更新本月熱門」開始第一次收集",
  });
  if (c.key === "bookmarks") return richEmptyHtml({
    icon: "⭐", title: "尚無收藏",
    sub: "在日報的卡片右上點 ★ 就會被收藏起來",
    cta: { label: "前往日報 →", onclick: "setMode('daily')" },
  });
  if (c.key === "releases") return richEmptyHtml({
    icon: "📦", title: "尚無 release 資料",
    sub: "點右上「⚡ 更新 releases」開始第一次收集",
  });
  return richEmptyHtml({ icon: "📭", title: "本 collection 尚無資料" });
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
    el.innerHTML = richEmptyHtml({
      icon: "🚀", title: "本月暫無熱門 repo 資料",
      sub: "點右上「⚡ 更新本月熱門」開始收集",
    });
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

async function triggerStage(stage, date, source, feed_name) {
  // stage = "translate" | "summarize" — 對應 /api/translate-day | /api/summarize-day
  const params = new URLSearchParams({ date });
  if (source) params.set("source", source);
  if (feed_name !== null && feed_name !== undefined) params.set("feed_name", feed_name);
  const scope = (source || "all") + (feed_name ? "/" + feed_name : "");
  updateStatusBar({ running: true, date, mode: stage + ":" + scope });
  try {
    const res = await fetch("/api/" + stage + "-day?" + params.toString(),
      { method: "POST" });
    const j = await res.json();
    if (!res.ok) { updateStatusBar({ running: false, error: j.error || (stage + " 失敗") }); return; }
    startPolling();
  } catch {
    updateStatusBar({ running: false, error: "無法連線" });
  }
}

// ── per-event STT (media 手動觸發) ────────────────────────────────────────
async function triggerStt(btn, uid) {
  btn.disabled = true;
  btn.textContent = "🎙️ STT 提交中…";
  try {
    const res = await fetch("/api/transcribe-event?uid=" + encodeURIComponent(uid),
      { method: "POST" });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) {
      btn.textContent = "❌ " + (j.detail || "提交失敗");
      setTimeout(() => { btn.disabled = false; btn.textContent = "🎙️ 送 STT"; }, 5000);
      return;
    }
    btn.textContent = "🎙️ STT 中…(可能數分鐘)";
    pollSttStatus(btn, uid);
  } catch {
    btn.textContent = "❌ 連線失敗";
    setTimeout(() => { btn.disabled = false; btn.textContent = "🎙️ 送 STT"; }, 5000);
  }
}

function pollSttStatus(btn, uid) {
  const timer = setInterval(async () => {
    // 按鈕已被重繪移除就停止輪詢
    if (!document.body.contains(btn)) { clearInterval(timer); return; }
    try {
      const r = await fetch("/api/transcribe-event/status?uid=" + encodeURIComponent(uid));
      const s = await r.json();
      if (s.status === "done") {
        clearInterval(timer);
        btn.textContent = "✅ 已轉錄 (" + (s.length || 0) + " 字)";
        // 重抓當前 feed 讓卡片更新(body 出現 → STT 按鈕消失)
        if (currentFeed) selectFeed(currentFeed.source, currentFeed.feed_name);
      } else if (s.status === "error") {
        clearInterval(timer);
        btn.textContent = "❌ " + (s.error || "失敗");
        setTimeout(() => { btn.disabled = false; btn.textContent = "🎙️ 送 STT"; }, 6000);
      }
    } catch {}
  }, 8000);
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
  const btns = document.querySelectorAll(".stage-btn, .run-today-btn");
  if (s.running) {
    let label = "蒐集中";
    if (s.mode && s.mode.startsWith("translate:")) label = `翻譯 ${s.mode.split(":")[1]}`;
    else if (s.mode && s.mode.startsWith("summarize:")) label = `摘要 ${s.mode.split(":")[1]}`;
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
    el.innerHTML = richEmptyHtml({
      icon: "📦", title: `近 ${data.days} 天無 release`,
      sub: "點右上「⚡ 更新 releases」重新收集,或選更長時間範圍",
    });
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
  const isMedia = e.source && (e.source.startsWith("youtube_") || e.source.startsWith("podcast_"));
  const hasBody = !!(e.body && e.body.trim());
  const isZh = e.body_lang === "zh";
  const hasSummary = !!(e.ai_summary && e.ai_summary.trim());
  // 卡片狀態徽章 — 對應統一流程「卡在哪一段」:
  //   無 body → 需 STT(媒體)/ 內文空
  //   有 body 但非中文 → 需翻譯
  //   中文 body 但無摘要 → 需摘要
  let stageBadge = "";
  if (!hasBody) {
    stageBadge = isMedia
      ? '<span class="badge stage-stt">🎙️ 需 STT</span>'
      : '<span class="badge stage-empty">內文空</span>';
  } else if (!isZh) {
    stageBadge = '<span class="badge stage-translate">🌐 需翻譯</span>';
  } else if (!hasSummary) {
    stageBadge = '<span class="badge stage-summarize">📝 需摘要</span>';
  }
  const sttBtn = (isMedia && !hasBody && e.uid)
    ? `<button class="stt-btn" data-stt-uid="${esc(e.uid)}"
        onclick="triggerStt(this, '${esc(e.uid)}')">🎙️ 送 STT</button>`
    : "";
  const isOn = e.uid && BOOKMARKED_UIDS.has(e.uid);
  const star = e.uid
    ? `<button class="bookmark-btn ${isOn ? "on" : ""}" data-uid="${esc(e.uid)}"
        title="${isOn ? "取消收藏" : "收藏"}"
        onclick="toggleBookmark(this, '${esc(e.uid)}')">★</button>`
    : "";
  // classification 與 source 同名(e.g. finance/Finance)時不重複顯示
  const showClass = e.classification &&
    e.classification.toLowerCase() !== (e.source || "").toLowerCase();
  // 刪除鈕貼在 source badge 旁(使用者要求),平常半透明 hover 才現紅
  const deleteBtn = e.uid
    ? `<button class="card-delete-btn" data-uid="${esc(e.uid)}"
        title="刪除這筆" onclick="deleteEvent(this, '${esc(e.uid)}')">🗑</button>`
    : "";
  // 日期由 date-group header 提供,卡片內不再重複顯示
  const leftMeta = [
    `<span class="badge src-${e.source}">${e.source}</span>`,
    deleteBtn,
    origin ? `<span>${origin}</span>` : "",
    showClass ? `<span class="badge">${esc(e.classification)}</span>` : "",
    (e.impact_level === "Breaking" || e.impact_level === "High")
      ? `<span class="badge impact-${e.impact_level}">${e.impact_level}</span>` : "",
    e.score ? `<span>▲ ${e.score}</span>` : "",
    stageBadge,
  ].filter(Boolean).join("");
  const rightActions = [sttBtn, star].filter(Boolean).join("");
  const tags = (e.tags || []).length
    ? `<div class="card-tags">${e.tags.map(t => "#" + esc(t)).join(" ")}</div>` : "";
  let summary = e.ai_summary
    ? `<div class="card-summary">${esc(e.ai_summary)}</div>`
    : e.body ? `<div class="card-summary card-body-preview">${esc(e.body.slice(0, 300))}…</div>` : "";
  return `<div class="card">
    <div class="card-meta">
      <div class="card-meta-left">${leftMeta}</div>
      ${rightActions ? `<div class="card-meta-actions">${rightActions}</div>` : ""}
    </div>
    <div class="card-title"><a href="${esc(e.url)}" target="_blank">${esc(e.title)}</a></div>
    ${summary}${tags}
  </div>`;
}

async function deleteEvent(btn, uid) {
  if (!confirm("確定要刪除這筆?(只刪 DB 內事件,收藏不受影響)")) return;
  btn.disabled = true;
  try {
    const res = await fetch("/api/events/" + encodeURIComponent(uid),
      { method: "DELETE" });
    if (!res.ok) { btn.disabled = false; alert("刪除失敗"); return; }
    // 移除整張卡 + 從 currentFeedData 拿掉,避免下次 render 又出現
    const card = btn.closest(".card");
    if (card) card.remove();
    if (currentFeedData && currentFeedData.groups) {
      currentFeedData.groups.forEach(g => {
        g.events = (g.events || []).filter(ev => ev.uid !== uid);
      });
    }
  } catch {
    btn.disabled = false;
    alert("無法連線");
  }
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
    el.innerHTML = richEmptyHtml({
      icon: "⭐", title: "本月尚無收藏",
      sub: "在日報的卡片右上點 ★ 就會被收藏起來",
      cta: { label: "前往日報 →", onclick: "setMode('daily')" },
    });
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
