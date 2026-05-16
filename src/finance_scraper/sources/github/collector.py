"""GitHub 資料收集器 - 抓取 release、issue、PR"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from github import Github, GithubException
from github.Repository import Repository

from finance_scraper.domain import EventType, RawGitHubEvent, RepoConfig, SourceType

logger = logging.getLogger(__name__)

# 高流量 repo 的事件上限（依留言數取 top N）
HIGH_VOLUME_REPOS: dict[str, int] = {
    "kubernetes/kubernetes": 20,
    "vllm-project/vllm": 30,
}


class GitHubCollector:
    source_type = SourceType.GITHUB

    def __init__(self, token: str, repos: list[RepoConfig], lookback_days: int = 7):
        self.gh = Github(token, per_page=100)
        self.repos = repos
        self.lookback_days = lookback_days
        # GitHub API 使用 UTC naive datetime
        self.since: datetime = datetime.utcnow() - timedelta(days=lookback_days)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def collect(self) -> list[RawGitHubEvent]:
        """依序收集所有追蹤 repo 的事件，kubernetes 最後處理（API 消耗最多）。"""
        repos = sorted(self.repos, key=lambda r: r.full_name == "kubernetes/kubernetes")
        all_events: list[RawGitHubEvent] = []
        failed: list[str] = []

        for repo_config in repos:
            self._check_rate_limit()
            try:
                events = self._collect_repo(repo_config)
                # 高流量 repo 限制上限
                cap = HIGH_VOLUME_REPOS.get(repo_config.full_name)
                if cap and len(events) > cap:
                    events.sort(key=lambda e: e.comment_count, reverse=True)
                    events = events[:cap]
                    logger.info(f"{repo_config.full_name} 事件截斷至 {cap} 筆")
                all_events.extend(events)
                logger.info(f"[{repo_config.full_name}] 收集到 {len(events)} 筆事件")
                time.sleep(1)  # 禮貌性延遲
            except Exception as exc:
                logger.error(f"[{repo_config.full_name}] 收集失敗：{exc}")
                failed.append(repo_config.full_name)

        if failed:
            logger.warning(f"以下 repo 收集失敗：{failed}")

        return all_events

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _collect_repo(self, repo_config: RepoConfig) -> list[RawGitHubEvent]:
        repo = self.gh.get_repo(repo_config.full_name)
        return self._collect_releases(repo, repo_config)

    def _collect_releases(self, repo: Repository, repo_config: RepoConfig) -> list[RawGitHubEvent]:
        events = []
        try:
            for release in repo.get_releases():
                if release.created_at.replace(tzinfo=None) < self.since:
                    break
                events.append(RawGitHubEvent(
                    repo_full_name=repo_config.full_name,
                    event_type=EventType.RELEASE,
                    title=release.title or release.tag_name,
                    tag=release.tag_name,
                    url=release.html_url,
                    created_at=release.created_at.replace(tzinfo=None),
                    body=release.body,
                    labels=[],
                    comment_count=0,
                    reactions=0,
                ))
        except GithubException as e:
            logger.warning(f"[{repo_config.full_name}] 抓取 release 失敗：{e}")
        return events

    def _collect_issues(self, repo: Repository, repo_config: RepoConfig) -> list[RawGitHubEvent]:
        events = []
        try:
            for issue in repo.get_issues(state="all", since=self.since, sort="updated"):
                # get_issues 包含 PR，需過濾掉
                if issue.pull_request:
                    continue
                if issue.updated_at.replace(tzinfo=None) < self.since:
                    break
                reactions = 0
                try:
                    reactions = issue.get_reactions().totalCount
                except Exception:
                    pass
                events.append(RawGitHubEvent(
                    repo_full_name=repo_config.full_name,
                    event_type=EventType.ISSUE,
                    title=issue.title,
                    number=issue.number,
                    url=issue.html_url,
                    created_at=issue.created_at.replace(tzinfo=None),
                    body=issue.body,
                    labels=[label.name for label in issue.labels],
                    comment_count=issue.comments,
                    reactions=reactions,
                ))
        except GithubException as e:
            logger.warning(f"[{repo_config.full_name}] 抓取 issue 失敗：{e}")
        return events

    def _collect_prs(self, repo: Repository, repo_config: RepoConfig) -> list[RawGitHubEvent]:
        events = []
        try:
            for pr in repo.get_pulls(state="closed", sort="updated", direction="desc"):
                if pr.updated_at.replace(tzinfo=None) < self.since:
                    break
                # 只取已 merge 的，或者高互動的 open PR
                if not pr.merged:
                    continue
                reactions = 0
                try:
                    reactions = pr.get_reactions().totalCount
                except Exception:
                    pass
                events.append(RawGitHubEvent(
                    repo_full_name=repo_config.full_name,
                    event_type=EventType.PR,
                    title=pr.title,
                    number=pr.number,
                    url=pr.html_url,
                    created_at=pr.created_at.replace(tzinfo=None),
                    body=pr.body,
                    labels=[label.name for label in pr.labels],
                    comment_count=pr.comments + pr.review_comments,
                    reactions=reactions,
                    is_merged=pr.merged,
                    diff_url=pr.diff_url,
                ))
        except GithubException as e:
            logger.warning(f"[{repo_config.full_name}] 抓取 PR 失敗：{e}")
        return events

    def _check_rate_limit(self) -> None:
        """若剩餘 API 配額不足，等到重置後再繼續。"""
        try:
            rate = self.gh.get_rate_limit().core
            logger.debug(f"Rate limit 剩餘：{rate.remaining}/{rate.limit}")
            if rate.remaining < 200:
                reset_time = rate.reset.replace(tzinfo=None)
                wait_secs = (reset_time - datetime.utcnow()).total_seconds() + 5
                if wait_secs > 0:
                    logger.warning(f"Rate limit 不足，等待 {wait_secs:.0f} 秒後繼續...")
                    time.sleep(wait_secs)
        except Exception as e:
            logger.warning(f"無法取得 rate limit 資訊：{e}")
