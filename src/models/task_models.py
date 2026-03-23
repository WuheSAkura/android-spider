from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.utils.exceptions import ConfigError


SelectorValue = str | dict[str, Any]


@dataclass(slots=True)
class MySQLConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = "root"
    database: str = "android_spider"
    charset: str = "utf8mb4"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MySQLConfig":
        if not data:
            return cls()
        return cls(
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 3306)),
            user=str(data.get("user", "root")),
            password=str(data.get("password", "root")),
            database=str(data.get("database", "android_spider")),
            charset=str(data.get("charset", "utf8mb4")),
        )


@dataclass(slots=True)
class StorageConfig:
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    sqlite_path: Path = Path("data/local_runs.sqlite3")
    csv_dir: Path = Path("exports")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StorageConfig":
        if not data:
            return cls()
        return cls(
            mysql=MySQLConfig.from_dict(data.get("mysql")),
            sqlite_path=Path(data.get("sqlite_path", "data/local_runs.sqlite3")),
            csv_dir=Path(data.get("csv_dir", "exports")),
        )


@dataclass(slots=True)
class StepConfig:
    action: str
    selector: SelectorValue | None = None
    text: str | None = None
    timeout: float = 10.0
    direction: str = "down"
    count: int = 1
    page_name: str = "current_page"
    seconds: float = 1.0
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepConfig":
        action = str(data.get("action", "")).strip().lower()
        if not action:
            raise ConfigError("steps 中存在未配置 action 的步骤。")
        return cls(
            action=action,
            selector=data.get("selector"),
            text=data.get("text"),
            timeout=float(data.get("timeout", 10)),
            direction=str(data.get("direction", "down")).strip().lower(),
            count=int(data.get("count", 1)),
            page_name=str(data.get("page_name", "current_page")),
            seconds=float(data.get("seconds", 1)),
            description=str(data.get("description", "")),
        )


@dataclass(slots=True)
class TaskConfig:
    task_name: str
    adapter: str
    package_name: str
    device_serial: str | None
    launch_activity: str | None
    run_mode: str
    startup_wait_seconds: float
    selectors: dict[str, dict[str, Any]]
    steps: list[StepConfig]
    output_dir: Path
    save_screenshot: bool
    save_hierarchy: bool
    save_visible_texts: bool
    adapter_options: dict[str, Any] = field(default_factory=dict)
    storage: StorageConfig = field(default_factory=StorageConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskConfig":
        if not data:
            raise ConfigError("YAML 配置为空，无法执行任务。")

        task_name = str(data.get("task_name", "")).strip()
        if not task_name:
            raise ConfigError("必须配置 task_name。")

        package_name = str(data.get("package_name", "")).strip()
        if not package_name:
            raise ConfigError("必须配置 package_name。")

        raw_steps = data.get("steps", [])
        if raw_steps is None:
            raw_steps = []
        if not isinstance(raw_steps, list):
            raise ConfigError("steps 必须是数组。")

        selectors = data.get("selectors", {})
        if selectors is None:
            selectors = {}
        if not isinstance(selectors, dict):
            raise ConfigError("selectors 必须是对象映射。")

        return cls(
            task_name=task_name,
            adapter=str(data.get("adapter", "target_app_template")).strip() or "target_app_template",
            package_name=package_name,
            device_serial=str(data.get("device_serial")).strip() if data.get("device_serial") else None,
            launch_activity=str(data.get("launch_activity")).strip() if data.get("launch_activity") else None,
            run_mode=str(data.get("run_mode", "normal")).strip() or "normal",
            startup_wait_seconds=float(data.get("startup_wait_seconds", 3)),
            selectors=selectors,
            steps=[StepConfig.from_dict(item) for item in raw_steps],
            output_dir=Path(data.get("output_dir", "artifacts")),
            save_screenshot=bool(data.get("save_screenshot", True)),
            save_hierarchy=bool(data.get("save_hierarchy", True)),
            save_visible_texts=bool(data.get("save_visible_texts", True)),
            adapter_options=dict(data.get("adapter_options", {}) or {}),
            storage=StorageConfig.from_dict(data.get("storage")),
        )
