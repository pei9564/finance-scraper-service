"""機密設定 — 由環境變數載入。"""
from __future__ import annotations

import os

from pydantic import BaseModel


class Secrets(BaseModel):
    github_token: str

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            github_token=os.environ["GITHUB_TOKEN"],
        )
