from __future__ import annotations

import os
from pathlib import Path

from src.utils.exceptions import DependencyError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

_ENV_LOADED = False


def load_project_env() -> Path | None:
    """加载项目根目录 .env，重复调用时保持幂等。"""

    global _ENV_LOADED
    if _ENV_LOADED:
        return ENV_PATH if ENV_PATH.exists() else None

    if not ENV_PATH.exists():
        _ENV_LOADED = True
        return None

    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise DependencyError("缺少 python-dotenv 依赖，请先安装 requirements.txt。") from exc

    load_dotenv(ENV_PATH, override=False)
    _ENV_LOADED = True
    return ENV_PATH


def get_env(name: str, default: str | None = None) -> str | None:
    load_project_env()
    return os.getenv(name, default)


def get_env_int(name: str, default: int) -> int:
    value = get_env(name)
    if value in (None, ""):
        return default
    try:
        return int(str(value))
    except ValueError:
        return default


def get_env_bool(name: str, default: bool) -> bool:
    value = get_env(name)
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
