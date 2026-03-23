from __future__ import annotations

from src.adapters.base_adapter import BaseAdapter
from src.models.task_models import TaskConfig
from src.utils.exceptions import ConfigError


class SettingsDemoAdapter(BaseAdapter):
    """用于验证系统 Settings 应用流程可用。"""

    name = "settings_demo"

    def validate_config(self, task_config: TaskConfig) -> None:
        if task_config.package_name != "com.android.settings":
            raise ConfigError("settings_demo 适配器要求 package_name 为 com.android.settings。")

