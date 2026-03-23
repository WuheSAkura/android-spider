from __future__ import annotations

from src.adapters.base_adapter import BaseAdapter


class TargetAppTemplateAdapter(BaseAdapter):
    """后续替换具体 App 逻辑时使用的占位模板。"""

    name = "target_app_template"

