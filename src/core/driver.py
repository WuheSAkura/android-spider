from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from src.core.selectors import Selector
from src.core.ui_xml import extract_visible_texts_from_xml
from src.utils.exceptions import DependencyError, DriverError

try:
    import uiautomator2 as u2  # type: ignore[import-untyped]
    from uiautomator2 import exceptions as u2_exceptions  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - 依赖检查由 doctor 命令负责
    u2 = None
    u2_exceptions = None


ELEMENT_ACTION_ATTEMPTS = 3
ELEMENT_RETRY_SLEEP_SECONDS = 0.3


class AndroidDriver:
    """对 uiautomator2 的最小封装，便于未来替换为其他 driver。"""

    def __init__(self, serial: str, logger: logging.Logger | None = None) -> None:
        self.serial = serial
        self.logger = logger or logging.getLogger(__name__)
        self.device: Any | None = None

    def connect(self) -> "AndroidDriver":
        if u2 is None:
            raise DependencyError("缺少 uiautomator2 依赖，请先安装 requirements.txt。")
        self.device = u2.connect(self.serial)
        self.logger.info("已连接设备：%s", self.serial)
        return self

    def is_alive(self) -> bool:
        if self.device is None:
            return False
        try:
            _ = self.device.info
            return True
        except Exception:
            return False

    def start_app(self, package_name: str, activity: str | None = None) -> None:
        device = self._require_device()
        device.app_start(package_name, activity=activity, wait=True)
        self.logger.info("已启动应用：%s", package_name)

    def stop_app(self, package_name: str) -> None:
        device = self._require_device()
        device.app_stop(package_name)
        self.logger.info("已停止应用：%s", package_name)

    def click(self, selector: Selector, timeout: float = 10) -> None:
        strategy = self._execute_element_action(
            selector,
            timeout=timeout,
            action_name="点击",
            action=lambda _strategy, element: element.click(),
        )
        self.logger.info("点击成功，定位方式：%s", strategy)

    def input_text(self, selector: Selector, text: str, timeout: float = 10) -> None:
        def perform_input(strategy: str, element: Any) -> None:
            if strategy == "xpath" and hasattr(element, "set_text"):
                element.set_text(text)
            elif strategy != "xpath" and hasattr(element, "set_text"):
                element.set_text(text)
            else:
                element.click()
                self._require_device().send_keys(text, clear=True)

        strategy = self._execute_element_action(
            selector,
            timeout=timeout,
            action_name="输入文本",
            action=perform_input,
        )
        self.logger.info("输入文本成功，定位方式：%s", strategy)

    def send_keys(self, text: str, clear: bool = True) -> None:
        """向当前焦点控件输入文本。"""
        self._require_device().send_keys(text, clear=clear)
        self.logger.info("已向当前焦点输入文本。")

    def press_key(self, key: str) -> None:
        """发送系统按键，例如 enter、search、back。"""
        self._require_device().press(key)
        self.logger.info("已发送按键：%s", key)

    def click_point(self, x: int, y: int) -> None:
        """按坐标点击，适合列表项 bounds 点击。"""
        self._require_device().click(x, y)
        self.logger.info("已按坐标点击：(%s, %s)", x, y)

    def swipe_up(self) -> None:
        device = self._require_device()
        # 对外语义为“页面向上滚动”，因此实际手势向下滑。
        device.swipe_ext("down", scale=0.8)
        self.logger.info("已执行上滑。")

    def swipe_down(self) -> None:
        device = self._require_device()
        # 对外语义为“页面向下滚动”，因此实际手势向上滑。
        device.swipe_ext("up", scale=0.8)
        self.logger.info("已执行下滑。")

    def back(self) -> None:
        device = self._require_device()
        device.press("back")
        self.logger.info("已执行返回。")

    def wait_for(self, selector: Selector, timeout: float = 10) -> bool:
        try:
            self._execute_element_action(
                selector,
                timeout=timeout,
                action_name="等待元素",
                action=lambda _strategy, _element: None,
            )
        except DriverError:
            return False
        return True

    def screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._require_device().screenshot(str(path))
        return path

    def get_hierarchy_xml(self) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return str(self._require_device().dump_hierarchy(pretty=True))
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    self.logger.warning("获取页面层级失败，准备重试：%s", exc)
                    time.sleep(0.4)
                    continue
                if attempt == 1:
                    self.logger.warning("获取页面层级再次失败，尝试重置 uiautomator：%s", exc)
                    self._reset_uiautomator()
                    time.sleep(0.8)
                    continue
                break
        raise DriverError(f"获取页面层级失败：{last_error}") from last_error

    def dump_hierarchy(self, path: Path) -> Path:
        xml_content = self.get_hierarchy_xml()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xml_content, encoding="utf-8")
        return path

    def get_visible_texts(self, hierarchy_xml: str | None = None) -> list[str]:
        xml_content = hierarchy_xml or self.get_hierarchy_xml()
        return extract_visible_texts_from_xml(xml_content)

    def _execute_element_action(
        self,
        selector: Selector,
        *,
        timeout: float,
        action_name: str,
        action: Callable[[str, Any], None],
    ) -> str:
        deadline = time.time() + max(timeout, 0.1)
        last_error: Exception | None = None

        for attempt in range(ELEMENT_ACTION_ATTEMPTS):
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            attempts_left = max(ELEMENT_ACTION_ATTEMPTS - attempt, 1)
            lookup_timeout = max(remaining / attempts_left, 0.1)

            try:
                strategy, element = self._find_element(selector, lookup_timeout)
                action(strategy, element)
                return strategy
            except DriverError as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
                if not self._is_retryable_element_error(exc):
                    raise DriverError(f"{action_name}失败：{exc}") from exc
                if attempt < ELEMENT_ACTION_ATTEMPTS - 1 and deadline - time.time() > 0:
                    self._prepare_retryable_element_error(action_name, exc, attempt)

            if attempt >= ELEMENT_ACTION_ATTEMPTS - 1:
                break

            sleep_seconds = min(ELEMENT_RETRY_SLEEP_SECONDS, max(deadline - time.time(), 0))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if isinstance(last_error, DriverError):
            raise last_error
        if last_error is not None:
            raise DriverError(f"{action_name}失败：{last_error}") from last_error
        raise DriverError(f"{action_name}失败：未找到匹配元素")

    def _find_element(self, selector: Selector, timeout: float) -> tuple[str, Any]:
        self._ensure_device()
        deadline = time.time() + max(timeout, 0.1)
        last_error: str | None = None

        for strategy, value in selector.strategies():
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            element = self._get_element(strategy, value)
            try:
                exists = element.wait(timeout=remaining)
            except Exception as exc:
                last_error = str(exc)
                continue
            if exists:
                return strategy, element

        details = last_error or "未找到匹配元素"
        raise DriverError(f"元素查找失败：{details}")

    def _get_element(self, strategy: str, value: str) -> Any:
        device = self._require_device()
        if strategy == "xpath":
            return device.xpath(value)
        if strategy == "text":
            return device(text=value)
        if strategy == "resource_id":
            return device(resourceId=value)
        if strategy == "description":
            return device(description=value)
        raise DriverError(f"不支持的定位方式：{strategy}")

    def _ensure_device(self) -> None:
        if self.device is None:
            raise DriverError("设备尚未连接，请先调用 connect()。")

    def _require_device(self) -> Any:
        self._ensure_device()
        return self.device

    def _is_retryable_element_error(self, exc: Exception) -> bool:
        if u2_exceptions is None:
            return False

        if isinstance(
            exc,
            (
                u2_exceptions.UiObjectNotFoundError,
                u2_exceptions.HTTPError,
                u2_exceptions.ConnectError,
                u2_exceptions.UiAutomationError,
                u2_exceptions.SessionBrokenError,
            ),
        ):
            return True

        return isinstance(exc, u2_exceptions.RPCUnknownError) and any(
            token in str(exc)
            for token in (
                "StaleObjectException",
                "UiObjectNotFoundException",
            )
        )

    def _prepare_retryable_element_error(self, action_name: str, exc: Exception, attempt: int) -> None:
        if self._should_reset_uiautomator(exc):
            self.logger.warning(
                "%s遇到 uiautomator 瞬时异常，第 %s 次重试前重置服务：%s",
                action_name,
                attempt + 1,
                exc,
            )
            self._reset_uiautomator()
            return

        self.logger.warning(
            "%s遇到瞬时节点异常，准备重试（第 %s 次）：%s",
            action_name,
            attempt + 1,
            exc,
        )

    def _should_reset_uiautomator(self, exc: Exception) -> bool:
        if u2_exceptions is None:
            return False

        return isinstance(
            exc,
            (
                u2_exceptions.HTTPError,
                u2_exceptions.ConnectError,
                u2_exceptions.UiAutomationError,
                u2_exceptions.SessionBrokenError,
            ),
        )

    def _reset_uiautomator(self) -> None:
        device = self._require_device()
        try:
            if hasattr(device, "reset_uiautomator"):
                device.reset_uiautomator()
            if u2 is not None:
                self.device = u2.connect(self.serial)
            self.logger.info("已重置 uiautomator 服务并重新连接设备。")
        except Exception as exc:
            raise DriverError(f"重置 uiautomator 失败：{exc}") from exc
