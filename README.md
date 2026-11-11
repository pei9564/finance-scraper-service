# Finance Scraper Service

自動化的金融與技術情報收集、翻譯、摘要系統。從新聞、論文、財經媒體、YouTube／Podcast、GitHub Releases 抓取最新內容，經 STT 轉逐字稿、LLM 翻譯與摘要，最後寫入 PostgreSQL 並產生每日簡報網頁。

本專案為 `ai-finance-infra` 生態系的一環，負責其中的採集與內容處理層。

## 功能

**五種來源**

| 來源 | 內容 |
|---|---|
| 新聞 | HackerNews（分數門檻可調）+ 任意 RSS |
| 論文 | arXiv（可選分類、抓取上限）+ HuggingFace Papers |
| 財經 | 經濟日報、CNBC、MarketWatch、Yahoo Finance 等 RSS |
| 影音 | YouTube 頻道、Podcast RSS — 交給 `stt-ai-worker` 轉逐字稿 |
| Releases | 追蹤 GitHub repo 的 release notes |

**處理流程**

```
collect    → filter（時間窗、去重、分數門檻）
           → classify（規則式分類，免 token）
           → STT（影音來源）
           → translate / summarize（LLM，可手動觸發）
           → output（PostgreSQL + 每日網頁）
```

- 以 `(source, url)` 為 key 快取，重跑不會重複呼叫 LLM
- LLM 或 STT 不可用時自動降級，不中斷採集
- 翻譯前先偵測內容是否已是中文，避免中文被「翻成中文」的 meta 回應覆蓋

## 執行

```bash
cp .env.example .env        # 填入 PG_DSN / GITHUB_TOKEN / VLLM_*
docker compose up -d --build
```

開 <http://localhost:8080> 操作，API 文件在 <http://localhost:8080/docs>。

K3s 部署請參考 `ai-finance-infra` repo；本 repo 的 `docker-compose.yml` 供本地開發使用。

## 設定

主要設定在 `config/repos.yaml`：追蹤的 repo、RSS 來源、arXiv 分類、各來源的摘要 prompt 與長度上限、輸出開關。改完不用 rebuild。

環境變數（`.env`）：

| 變數 | 用途 |
|---|---|
| `PG_DSN` | PostgreSQL 連線字串（必填） |
| `GITHUB_TOKEN` | 讀取 GitHub Releases（必填） |
| `VLLM_BASE_URL` | LLM gateway 位址（OpenAI 相容） |
| `VLLM_MODEL` | 模型名稱，留空自動向 gateway 偵測 |
| `VLLM_API_KEY` | gateway 金鑰（無驗證可留空） |
| `STT_BASE_URL` | `stt-ai-worker` 位址 |
| `LOOKBACK_DAYS` | 回溯天數，預設 1 |
| `RETENTION_DAYS` | 資料保留天數 |
| `PORT` | 服務埠號，預設 8080 |

## 架構

分層架構，相依方向由外往內：`interfaces/` 定義介面、`infrastructure/` 提供實作。
新增來源或處理步驟只需在 registry 註冊，orchestrator 不用改。

```
src/finance_scraper/
  server.py            FastAPI 進入點（HTTP API + 內建網頁）
  main.py              CLI 進入點（單次執行 pipeline）
  monthly.py           月度摘要 CLI
  releases.py          GitHub Releases 追蹤 CLI

  domain/              純資料模型與設定，不依賴框架
    events.py            RawEvent / ClassifiedEvent / SummarizedEvent
    config.py            AppConfig（對應 repos.yaml）
    enums.py             SourceType / EventType / Classification
    secrets.py           環境變數 → Secrets

  interfaces/          抽象介面
    source.py            SourceCollector / ProcessingStep
    llm.py               LLMGateway
    output.py            OutputTarget

  pipeline/
    orchestrator.py      Pipeline：collect → filter → classify → 逐來源處理 → 日報摘要
    progress.py          執行進度追蹤

  sources/             各來源的採集器
    news/                HackerNews + RSS
    paper/               arXiv + HuggingFace
    finance/            財經 RSS（繼承 NewsCollector）
    media/               YouTube / Podcast（委派 stt-ai-worker）
    github/              Releases
    steps/               fetch_body / translate / summarize
    registry.py          名稱 → 實例的工廠註冊表

  processing/          分類、過濾、逐日彙整、收藏摘要
  storage/             PostgreSQL 存取層
  outputs/             網頁產生器與輸出目標
  infrastructure/      LLM gateway client、STT client

config/
  repos.yaml           追蹤清單、來源設定、prompt 與長度
```

**要新增一種來源**：在 `sources/` 加一個 `SourceCollector` 實作，於 `registry.py` 的
`COLLECTOR_FACTORIES` 註冊，再寫進 `repos.yaml` 的 `sources` 區塊即可。

## 測試

44 個單元測試，不需要 PostgreSQL 或 LLM：

```bash
uv sync --group dev
uv run python -m pytest -q
```

CI 跑完測試後才 build image 並發佈到 GHCR。

## API

主要端點：

| 端點 | 說明 |
|---|---|
| `GET /healthz` `GET /readyz` | 健康檢查（readyz 會檢查 PG） |
| `POST /api/run` | 背景執行 pipeline（可帶 `?date=`） |
| `GET /api/status` | 目前執行狀態 |
| `GET /api/feeds` `GET /api/feeds/events` | 來源與事件列表 |
| `POST /api/translate-day` | 翻譯指定日期 |
| `POST /api/summarize-day` | 摘要指定日期 |
| `POST /api/transcribe-event` | 對影音事件補轉逐字稿 |
| `GET/POST/DELETE /api/bookmarks` | 收藏管理 |
| `POST /api/run-monthly` | 月度摘要 |
| `POST /api/run-releases` | 抓取 GitHub Releases |

完整清單見 <http://localhost:8080/docs>。

## 授權

MIT
