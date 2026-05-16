"""GitHub 熱門 repo 收集器 — 抓取近期建立、star 數竄升最快的 AI repo。

策略：搜尋 lookback_days 內建立的 AI 相關 repo，按 star 數降序排列。
新建立卻能在短時間累積大量 star = 確實是「竄升最快」的指標。
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from github import Github, RateLimitExceededException

logger = logging.getLogger(__name__)

# 分批查詢，每個 topic 獨立一次 search（GitHub API 不支援 topic: OR 組合）
AI_TOPICS = ["ai", "llm", "machine-learning", "generative-ai"]
DEFAULT_TOP_N = 50


@dataclass
class TrendingRepo:
    rank: int
    full_name: str
    description: str
    stars: int
    forks: int
    url: str
    created_at: str   # YYYY-MM-DD
    language: str
    topics: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class GitHubTrendingCollector:
    def __init__(self, token: str, lookback_days: int = 30, top_n: int = DEFAULT_TOP_N):
        self.gh = Github(token, per_page=100)
        self.lookback_days = lookback_days
        self.top_n = top_n

    def collect(self) -> list[TrendingRepo]:
        since_str = (date.today() - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")

        # 每個 topic 獨立查詢，取 top_n 後去重，最終按 star 排序
        seen: dict[str, dict] = {}  # full_name → raw repo data
        fetch_per_topic = self.top_n * 2  # 多抓一些以備去重後仍足量

        for topic in AI_TOPICS:
            query = f"topic:{topic} created:>{since_str} stars:>10"
            try:
                results = self.gh.search_repositories(query, sort="stars", order="desc")
                for i, repo in enumerate(results):
                    if i >= fetch_per_topic:
                        break
                    if repo.full_name not in seen:
                        seen[repo.full_name] = repo
                    time.sleep(0.2)
            except RateLimitExceededException:
                logger.error("GitHub rate limit 超限，trending 收集提前結束")
                break
            except Exception as e:
                logger.warning(f"topic:{topic} 查詢失敗：{e}")

        # 按 star 數排序、截取 top_n
        sorted_repos = sorted(seen.values(), key=lambda r: r.stargazers_count, reverse=True)
        sorted_repos = sorted_repos[: self.top_n]

        repos: list[TrendingRepo] = []
        for i, repo in enumerate(sorted_repos):
            try:
                topics = repo.get_topics()
            except Exception:
                topics = []
            repos.append(TrendingRepo(
                rank=i + 1,
                full_name=repo.full_name,
                description=repo.description or "",
                stars=repo.stargazers_count,
                forks=repo.forks_count,
                url=repo.html_url,
                created_at=repo.created_at.strftime("%Y-%m-%d"),
                language=repo.language or "",
                topics=topics,
            ))

        logger.info(f"trending 收集完成：{len(repos)} 個 repo")
        return repos
