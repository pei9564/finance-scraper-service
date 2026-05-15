"""設定資料模型 — 對應 config/repos.yaml。"""
from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class RepoConfig(BaseModel):
    owner: str
    name: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class FilterConfig(BaseModel):
    min_reactions: int = 0
    min_comments_for_issue: int = 3
    min_comments_for_pr: int = 2
    include_labels: list[str] = Field(default_factory=list)
    lookback_days: int = 7


class SummaryProfile(BaseModel):
    max_tokens: int = 600
    instruction: str = ""


class AIConfig(BaseModel):
    # 內部 LLM gateway（OpenAI 相容），用於逐則與日報摘要
    vllm_enabled: bool = True
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model: str = ""  # 留空則自動向 /models 探測
    # 各來源的逐則摘要設定，key 為 SourceType 值（news / paper / ...）
    summary_profiles: dict[str, SummaryProfile] = Field(default_factory=dict)


class TelegramConfig(BaseModel):
    max_events_per_message: int = 10
    critical_only_for_immediate: bool = True


class RSSFeedConfig(BaseModel):
    name: str
    url: str


class NewsConfig(BaseModel):
    hackernews_enabled: bool = True
    hackernews_top_n: int = 20
    hackernews_min_score: int = 50
    rss_feeds: list[RSSFeedConfig] = Field(default_factory=list)


class FinanceConfig(BaseModel):
    """財經來源 — 純 RSS（無 HN），鏡像 NewsConfig 的 rss_feeds 欄位以共用 RSS 解析。"""
    rss_feeds: list[RSSFeedConfig] = Field(default_factory=list)


class PaperConfig(BaseModel):
    arxiv_categories: list[str] = Field(default_factory=lambda: ["cs.AI", "cs.CL", "cs.LG"])
    arxiv_fetch_limit: int = 200   # 送 LLM 前最多抓幾篇（去重後）
    arxiv_top_n: int = 5           # LLM 篩選後保留幾篇
    arxiv_keywords: list[str] = Field(default_factory=list)
    hf_papers_enabled: bool = True  # Hugging Face Daily Papers
    hf_top_n: int = 5               # HF 按 upvotes 取前幾篇


class SourceConfig(BaseModel):
    """單一來源的開關與逐則處理步驟鏈（步驟名稱對應 STEP_FACTORIES）。"""
    enabled: bool = True
    steps: list[str] = Field(default_factory=list)


class OutputConfig(BaseModel):
    """單一輸出的開關。"""
    enabled: bool = False


# 缺 sources: / outputs: 區塊的舊設定檔仍可運作的預設值
DEFAULT_SOURCES: dict[str, SourceConfig] = {
    "github": SourceConfig(enabled=True, steps=[]),
    "news": SourceConfig(enabled=True, steps=["summarize"]),
    "paper": SourceConfig(enabled=True, steps=["summarize"]),
    "finance": SourceConfig(enabled=True, steps=["summarize"]),
}
DEFAULT_OUTPUTS: dict[str, OutputConfig] = {
    "web": OutputConfig(enabled=True),
    "telegram": OutputConfig(enabled=False),
    "notion": OutputConfig(enabled=False),
}


class AppConfig(BaseModel):
    repos: list[RepoConfig]
    news: NewsConfig = Field(default_factory=NewsConfig)
    papers: PaperConfig = Field(default_factory=PaperConfig)
    finance: FinanceConfig = Field(default_factory=FinanceConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    sources: dict[str, SourceConfig] = Field(default_factory=lambda: dict(DEFAULT_SOURCES))
    outputs: dict[str, OutputConfig] = Field(default_factory=lambda: dict(DEFAULT_OUTPUTS))
