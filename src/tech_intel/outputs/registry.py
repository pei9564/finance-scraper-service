"""輸出 registry — 把 config 的名稱對應到啟用的 OutputWriter。

新增輸出 = 一個 OUTPUT_FACTORIES 條目 + repos.yaml 的一筆 outputs 設定。
enabled 旗標在此解析，orchestrator 只看得到啟用的 writer。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tech_intel.domain import AppConfig, Secrets
from tech_intel.interfaces import OutputWriter

from .web import WebOutput

logger = logging.getLogger(__name__)


@dataclass
class OutputDeps:
    config: AppConfig
    secrets: Secrets
    output_dir: Path


OUTPUT_FACTORIES: dict[str, Callable[[OutputDeps], OutputWriter]] = {
    "web": lambda d: WebOutput(d.output_dir),
}


def build_output_writers(
    config: AppConfig,
    secrets: Secrets,
    output_dir: Path,
) -> list[OutputWriter]:
    deps = OutputDeps(config=config, secrets=secrets, output_dir=output_dir)
    writers: list[OutputWriter] = []

    for name, output_config in config.outputs.items():
        if not output_config.enabled:
            logger.info(f"輸出 '{name}' 已停用，略過")
            continue
        factory = OUTPUT_FACTORIES.get(name)
        if factory is None:
            logger.warning(f"未知輸出 '{name}'，略過")
            continue
        writers.append(factory(deps))
        logger.info(f"輸出 '{name}' 已啟用")

    return writers
