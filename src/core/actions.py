from __future__ import annotations

import logging
import time
from typing import Any

from src.core.artifacts import ArtifactManager, PageCapture
from src.core.driver import AndroidDriver
from src.core.selectors import resolve_selector
from src.models.task_models import StepConfig, TaskConfig
from src.utils.exceptions import ConfigError, StepExecutionError


class ActionExecutor:
    """负责执行 YAML 中定义的步骤。"""

    def __init__(
        self,
        driver: AndroidDriver,
        task_config: TaskConfig,
        artifacts: ArtifactManager,
        logger: logging.Logger,
    ) -> None:
        self.driver = driver
        self.task_config = task_config
        self.artifacts = artifacts
        self.logger = logger

    def execute(self, step: StepConfig) -> dict[str, Any] | None:
        action = step.action.lower()
        self.logger.info("开始执行步骤：%s %s", action, step.description or "")

        if action == "wait":
            selector = resolve_selector(step.selector, self.task_config.selectors)
            if not self.driver.wait_for(selector, timeout=step.timeout):
                raise StepExecutionError("等待目标元素超时。")
            return None

        if action == "click":
            selector = resolve_selector(step.selector, self.task_config.selectors)
            self.driver.click(selector, timeout=step.timeout)
            return None

        if action == "input":
            if step.text is None:
                raise ConfigError("input 步骤必须提供 text。")
            selector = resolve_selector(step.selector, self.task_config.selectors)
            self.driver.input_text(selector, step.text, timeout=step.timeout)
            return None

        if action in {"swipe", "swipe_up", "swipe_down"}:
            self._execute_swipe(action, step)
            return None

        if action == "back":
            self.driver.back()
            return None

        if action == "sleep":
            time.sleep(step.seconds)
            return None

        if action == "capture":
            capture = self._capture(step.page_name)
            return {
                "page_name": step.page_name,
                "capture": capture.to_dict(),
            }

        raise ConfigError(f"不支持的步骤动作：{step.action}")

    def _execute_swipe(self, action: str, step: StepConfig) -> None:
        count = max(step.count, 1)
        if action == "swipe":
            direction = step.direction
        else:
            direction = "up" if action == "swipe_up" else "down"

        for _ in range(count):
            if direction == "up":
                self.driver.swipe_up()
            elif direction == "down":
                self.driver.swipe_down()
            else:
                raise ConfigError(f"不支持的 swipe direction：{direction}")
            time.sleep(1)

    def _capture(self, page_name: str) -> PageCapture:
        return self.artifacts.capture_page(
            self.driver,
            save_screenshot=self.task_config.save_screenshot,
            save_hierarchy=self.task_config.save_hierarchy,
            save_visible_texts=self.task_config.save_visible_texts,
            prefix=page_name,
        )

