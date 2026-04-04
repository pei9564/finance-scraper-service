# GitHub Collector Engine - Implementation Plan

## Context
Build a fully automated GitHub monitoring system that weekly collects releases, issues, and PRs from tracked AI/backend repos, uses Claude API for analysis, writes to Notion, and sends Telegram notifications. Zero manual operation once deployed.

---

## Architecture
Linear pipeline: Collect → Filter → Classify → Summarize → Output (Notion + Telegram)

---

## File Structure to Create
```
├── .github/workflows/weekly_intel.yml
├── src/
│   ├── main.py          # Orchestrator
│   ├── models.py        # Pydantic data models
│   ├── collector.py     # PyGitHub fetcher
│   ├── filter.py        # Significance scoring
│   ├── classifier.py    # Rule-based classification
│   ├── summarizer.py    # Claude API calls
│   ├── notion_writer.py # Notion DB writer
│   └── telegram_sender.py
├── config/repos.yaml
├── output/weekly/.gitkeep
├── tests/
│   ├── test_filter.py
│   ├── test_classifier.py
│   ├── test_models.py
│   ├── test_collector.py
│   └── test_summarizer.py
├── .env.example
└── requirements.txt
```

---

## Module Details

### `src/models.py`
Pydantic v2 models: `RepoPriority`, `EventType`, `ImpactLevel`, `RepoConfig`, `RawGitHubEvent`, `ClassifiedEvent`, `SummarizedEvent`, `WeeklyReport`, `NotionIds`, `Secrets`

### `config/repos.yaml`
- Repos with priority (critical/high)
- Filter thresholds: `min_comments_for_issue: 3`, `min_comments_for_pr: 2`, `lookback_days: 7`
- AI model names: `haiku_model: claude-haiku-4-5-20251001`, `sonnet_model: claude-sonnet-4-6`

### `src/collector.py`
- PyGitHub with `per_page=100`
- Fetch releases, issues (excluding PRs), merged PRs since `now - lookback_days`
- Rate limit check before each repo; sleep until reset if remaining < 200
- Per-repo error isolation; kubernetes capped at 20 events

### `src/filter.py`
- Scoring: breaking labels (+0.5), security (+0.4), comment engagement (capped +0.2), reactions (capped +0.15), release (+0.3), merged PR (+0.1)
- Releases always pass; issues score >= 0.15; PRs score >= 0.2

### `src/classifier.py`
- Pure rule-based (no LLM): Release → Release/Breaking → Breaking → Security → Performance → Bug → Feature → Other
- Priority: first match wins; no API cost

### `src/summarizer.py`
- **Haiku** for: Release, Issue, Feature PR
- **Sonnet** for: Breaking, Security, Release/Breaking, PR diffs
- Diff handling: fetch from `diff_url`, truncate to 50K chars with "partial diff" note
- Retry: RateLimitError → sleep 60s retry once; fallback to `[Summary unavailable]`
- JSON response parsing; Pydantic validation; safe defaults on failure

### `src/notion_writer.py`
- **Repositories DB**: upsert by Name
- **Activity Logs DB**: dedup by URL before insert
- **Weekly Tech Radar DB**: upsert by (week_start, repo)
- 0.4s sleep between API calls (Notion 3 req/sec limit)

### `src/telegram_sender.py`
- HTML parse mode (avoids Markdown escape issues)
- Breaking/Security sent first as individual alerts
- Per-repo weekly digest messages
- Final summary stats message
- 1s sleep between messages

### `src/main.py`
- Load config + secrets (env vars only; `python-dotenv` for local dev)
- `NOTION_DB_IDS` as JSON string (one secret for three IDs)
- Each stage in try/except; Notion and Telegram are independent output stages
- Always write `output/weekly/{YYYY-WNN}.json` artifact

### `.github/workflows/weekly_intel.yml`
- Cron: `0 15 * * 0` (Sunday 15:00 UTC = 23:00 CST)
- `workflow_dispatch` with optional `lookback_days` override
- `timeout-minutes: 60`
- Upload artifact with `if: always()`, 90-day retention
- Test job gates intel job

---

## Key Design Decisions
| Decision | Choice | Reason |
|---|---|---|
| Classification | Rule-based | Free, fast, deterministic |
| Summary model | Haiku | ~12x cheaper than Sonnet |
| Breaking change model | Sonnet | Accuracy matters for migration guidance |
| Notion dedup | URL match before insert | Idempotent re-runs |
| Diff truncation | First 50K chars | Avoids huge token bills |
| kubernetes cap | 20 events max | Prevents dominating output |
| NOTION_DB_IDS | Single JSON secret | Fewer GitHub Actions secrets |

---

## Implementation Order
1. `src/models.py`
2. `config/repos.yaml` + `.env.example` + `requirements.txt`
3. `src/collector.py`
4. `src/filter.py` + `src/classifier.py`
5. `src/summarizer.py` (Haiku path first, then Sonnet)
6. `src/notion_writer.py`
7. `src/telegram_sender.py`
8. `src/main.py`
9. `.github/workflows/weekly_intel.yml`
10. `tests/`

---

## Verification
1. Run `python src/collector.py` standalone to verify GitHub API connectivity
2. Run `pytest tests/ -m "not e2e"` for unit tests
3. `workflow_dispatch` with `lookback_days=1` on a small repo (pydantic/pydantic) for E2E
4. Check Notion DBs populated and Telegram messages received
5. Re-run same week to verify dedup (no duplicate Notion pages)
