"""GitHub Release 收集器 — 獨立於 daily pipeline,服務 releases collection。

抓 config.repos 每個 repo 的 release,以 release.published_at 為時間軸
(無 published_at 的 draft 退回 created_at)。skip 邏輯由 pipeline 端依
storage.list_existing_uids() 過濾,本 collector 不做去重。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from github import Github, GithubException

from finance_scraper.domain import RepoConfig
from finance_scraper.storage.releases import compute_uid

logger = logging.getLogger(__name__)

# 每個 repo 最多保留幾筆 release — 用來擋掉每次 CI build 都發 release 的 repo
# (例如 ggerganov/llama.cpp 一週可以有幾十個 b\d+ tag),避免淹沒 UI
MAX_RELEASES_PER_REPO = 10


class GitHubReleaseCollector:
    def __init__(self, token: str, repos: list[RepoConfig], lookback_days: int = 180):
        self.gh = Github(token, per_page=100)
        self.repos = repos
        self.lookback_days = lookback_days
        self.since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    def collect(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for repo_cfg in self.repos:
            try:
                items = self._collect_repo(repo_cfg)
                out.extend(items)
                logger.info(f"[{repo_cfg.full_name}] release {len(items)} 筆")
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"[{repo_cfg.full_name}] release 收集失敗:{e}")
        return out

    def _collect_repo(self, repo_cfg: RepoConfig) -> list[dict[str, Any]]:
        repo = self.gh.get_repo(repo_cfg.full_name)
        items: list[dict[str, Any]] = []
        try:
            for release in repo.get_releases():
                published = release.published_at or release.created_at
                if published is None:
                    continue
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if published < self.since:
                    break
                url = release.html_url
                items.append({
                    "uid": compute_uid(url),
                    "repo": repo_cfg.full_name,
                    "tag": release.tag_name or "",
                    "name": release.title or release.tag_name or "",
                    "url": url,
                    "body": release.body or "",
                    "is_prerelease": bool(release.prerelease),
                    "published_at": published,
                })
                # 已達上限就停止迭代,避免高頻 CI release 浪費 API
                if len(items) >= MAX_RELEASES_PER_REPO:
                    break
        except GithubException as e:
            logger.warning(f"[{repo_cfg.full_name}] get_releases 失敗:{e}")
        # 雙保險:倒序後再 cap(get_releases 已是 created_at desc,但 published_at 可能略不同)
        items.sort(key=lambda it: it["published_at"], reverse=True)
        return items[:MAX_RELEASES_PER_REPO]
