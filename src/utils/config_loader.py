from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.models.task_models import TaskConfig
from src.utils.exceptions import ConfigError


def load_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 原始内容。"""
    if not path.exists():
        raise ConfigError(f"配置文件不存在：{path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ConfigError(f"配置文件格式不正确：{path}")
    return data


def load_task_config(path: Path) -> TaskConfig:
    """加载并解析任务配置。"""
    return TaskConfig.from_dict(load_yaml(path))
