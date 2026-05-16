"""GitHub release collector + storage 純邏輯測試。

storage upsert / list_recent 需真實 PG,不在這裡涵蓋(e2e)。本檔聚焦:
- compute_uid 穩定性(同 url → 同 uid)
- GitHubReleaseCollector 對 lookback / 缺欄位 / pre-release 的處理
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from finance_scraper.domain import RepoConfig
from finance_scraper.sources.github.release_collector import GitHubReleaseCollector
from finance_scraper.storage.releases import compute_uid


def _fake_release(tag: str, title: str | None, published_at: datetime,
                  body: str = "", prerelease: bool = False):
    r = MagicMock()
    r.tag_name = tag
    r.title = title
    r.published_at = published_at
    r.created_at = published_at
    r.body = body
    r.prerelease = prerelease
    r.html_url = f"https://github.com/x/y/releases/tag/{tag}"
    return r


def test_compute_uid_is_stable_per_url():
    url = "https://github.com/x/y/releases/tag/v1"
    assert compute_uid(url) == compute_uid(url)
    assert compute_uid(url) != compute_uid(url + "1")


def test_collector_skips_releases_older_than_lookback():
    """超過 lookback_days 的 release 應被跳過(get_releases 是時間倒序,遇到舊的就 break)。"""
    now = datetime.now(timezone.utc)
    releases = [
        _fake_release("v3", "v3", now - timedelta(days=10)),
        _fake_release("v2", "v2", now - timedelta(days=50)),
        _fake_release("v1", "v1", now - timedelta(days=200)),  # 在 180 天外,break
    ]
    repo = MagicMock()
    repo.get_releases.return_value = releases

    collector = GitHubReleaseCollector(token="x", repos=[], lookback_days=180)
    collector.gh = MagicMock()
    collector.gh.get_repo.return_value = repo

    items = collector._collect_repo(RepoConfig(owner="x", name="y"))

    tags = [it["tag"] for it in items]
    assert tags == ["v3", "v2"]
    assert all(it["repo"] == "x/y" for it in items)


def test_collector_handles_prerelease_and_missing_title():
    now = datetime.now(timezone.utc)
    releases = [
        _fake_release("v9-rc1", title=None, published_at=now - timedelta(days=2),
                      body="dev preview", prerelease=True),
    ]
    repo = MagicMock()
    repo.get_releases.return_value = releases

    collector = GitHubReleaseCollector(token="x", repos=[], lookback_days=30)
    collector.gh = MagicMock()
    collector.gh.get_repo.return_value = repo

    items = collector._collect_repo(RepoConfig(owner="x", name="y"))

    assert len(items) == 1
    it = items[0]
    assert it["is_prerelease"] is True
    assert it["name"] == "v9-rc1"  # title 缺時 fallback tag
    assert it["body"] == "dev preview"
    assert it["uid"] == compute_uid(it["url"])


def test_collector_returns_empty_when_get_releases_raises():
    from github import GithubException
    repo = MagicMock()
    repo.get_releases.side_effect = GithubException(500, {"message": "boom"}, None)

    collector = GitHubReleaseCollector(token="x", repos=[], lookback_days=30)
    collector.gh = MagicMock()
    collector.gh.get_repo.return_value = repo

    items = collector._collect_repo(RepoConfig(owner="x", name="y"))
    assert items == []
