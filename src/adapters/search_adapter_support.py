from __future__ import annotations

import re
import time
from typing import Callable

from src.core.driver import AndroidDriver
from src.core.selectors import Selector, resolve_selector
from src.models.task_models import TaskConfig
from src.utils.exceptions import DriverError


CancelCheck = Callable[[], None] | None


def resolve_runtime_selectors(task_config: TaskConfig) -> dict[str, Selector]:
    selectors: dict[str, Selector] = {}
    for name in task_config.selectors:
        selectors[name] = resolve_selector(name, task_config.selectors)
    return selectors


def click_optional(
    driver: AndroidDriver,
    selector: Selector | None,
    *,
    settle_seconds: float,
    check_cancelled: CancelCheck = None,
) -> bool:
    ensure_not_cancelled(check_cancelled)
    if selector is None:
        return False
    try:
        driver.click(selector, timeout=2)
    except DriverError:
        return False
    sleep_seconds(settle_seconds, check_cancelled=check_cancelled)
    return True


def sleep_seconds(seconds: float, *, check_cancelled: CancelCheck = None) -> None:
    ensure_not_cancelled(check_cancelled)
    time.sleep(max(seconds, 0))
    ensure_not_cancelled(check_cancelled)


def title_matches_keyword(title_hint: str, keyword: str) -> bool:
    normalized_title = re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "", title_hint.lower())
    normalized_keyword = re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "", keyword.lower())
    if not normalized_keyword:
        return True
    return normalized_keyword in normalized_title


def ensure_not_cancelled(check_cancelled: CancelCheck) -> None:
    if check_cancelled is not None:
        check_cancelled()
