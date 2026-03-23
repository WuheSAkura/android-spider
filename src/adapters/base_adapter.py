from __future__ import annotations

import logging
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.core.artifacts import ArtifactManager
from src.core.driver import AndroidDriver
from src.models.collected_record import CollectedRecord
from src.models.task_models import TaskConfig
from src.storage.result_store import MySQLResultStore


@dataclass(slots=True)
class AdapterRunResult:
    result: dict[str, Any]
    page_name: str
    visible_texts: list[str]
    collected_records: list[CollectedRecord] = field(default_factory=list)


@dataclass(slots=True)
class AdapterPartialResult:
    result: dict[str, Any] = field(default_factory=dict)
    collected_records: list[CollectedRecord] = field(default_factory=list)


class BaseAdapter(ABC):
    """通用 Adapter 接口，屏蔽不同 App 的页面逻辑差异。"""

    name = "base"

    def validate_config(self, task_config: TaskConfig) -> None:
        """按需校验任务配置。"""

    def before_run(self, task_config: TaskConfig, logger: logging.Logger) -> None:
        """任务开始前的扩展点。"""

    def after_run(self, task_config: TaskConfig, logger: logging.Logger) -> None:
        """任务结束后的扩展点。"""

    def execute_task(
        self,
        *,
        driver: AndroidDriver,
        task_config: TaskConfig,
        artifacts: ArtifactManager,
        logger: logging.Logger,
        mysql_store: MySQLResultStore,
        run_id: int | None,
        check_cancelled: Callable[[], None] | None = None,
    ) -> AdapterRunResult | None:
        """复杂页面流程可由 Adapter 接管；返回 None 表示走默认 YAML 任务流。"""
        del check_cancelled
        return None

    def export_partial_result(
        self,
        *,
        task_config: TaskConfig,
        artifacts: ArtifactManager,
        logger: logging.Logger,
    ) -> AdapterPartialResult | None:
        """任务异常中断时导出已采集的部分结果；默认无输出。"""
        del task_config, artifacts, logger
        return None

    def build_result(
        self,
        *,
        task_config: TaskConfig,
        device_serial: str,
        artifact_dir: Path,
        page_name: str,
        visible_texts: list[str],
    ) -> dict[str, Any]:
        return {
            "task_name": task_config.task_name,
            "adapter": self.name,
            "device_serial": device_serial,
            "package_name": task_config.package_name,
            "page_name": page_name,
            "visible_text_count": len(visible_texts),
            "visible_texts": visible_texts,
            "artifact_dir": str(artifact_dir),
            "status": "success",
        }
