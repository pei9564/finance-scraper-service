"""測試來源與輸出的 registry — enabled 旗標與名稱對應。"""
from pathlib import Path

from tech_intel.domain import (
    AppConfig, OutputConfig, RepoConfig, Secrets, SourceConfig, SourceType,
)
from tech_intel.outputs.registry import build_output_writers
from tech_intel.sources.registry import build_source_units


class StubGateway:
    def chat(self, user_prompt, max_tokens, system_prompt=None, temperature=0.3):
        return ""


def _secrets() -> Secrets:
    return Secrets(github_token="gh")


def _config(**overrides) -> AppConfig:
    base = dict(
        repos=[RepoConfig(owner="a", name="b")],
        sources={
            "github": SourceConfig(enabled=True, steps=[]),
            "news": SourceConfig(enabled=True, steps=["summarize"]),
            "paper": SourceConfig(enabled=False, steps=["summarize"]),
        },
        outputs={
            "web": OutputConfig(enabled=True),
        },
    )
    base.update(overrides)
    return AppConfig(**base)


def test_build_source_units_respects_enabled():
    units = build_source_units(_config(), _secrets(), StubGateway(), lookback=1)
    types = {u.source_type for u in units}
    assert types == {SourceType.GITHUB, SourceType.NEWS}  # paper disabled
    assert SourceType.PAPER not in types


def test_build_source_units_maps_step_names():
    units = build_source_units(_config(), _secrets(), StubGateway(), lookback=1)
    by_type = {u.source_type: u for u in units}
    assert [s.name for s in by_type[SourceType.GITHUB].steps] == []
    assert [s.name for s in by_type[SourceType.NEWS].steps] == ["summarize"]


def test_build_source_units_skips_unknown_step():
    config = _config(sources={"news": SourceConfig(enabled=True, steps=["summarize", "bogus"])})
    units = build_source_units(config, _secrets(), StubGateway(), lookback=1)
    assert [s.name for s in units[0].steps] == ["summarize"]


def test_build_output_writers_respects_enabled(tmp_path: Path):
    writers = build_output_writers(_config(), _secrets(), tmp_path)
    names = {w.name for w in writers}
    assert names == {"web"}


def test_build_output_writers_disabled(tmp_path: Path):
    config = _config(outputs={"web": OutputConfig(enabled=False)})
    writers = build_output_writers(config, _secrets(), tmp_path)
    assert writers == []
