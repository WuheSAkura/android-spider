"""Adapter 注册表。"""

from src.adapters.settings_demo_adapter import SettingsDemoAdapter
from src.adapters.target_app_template_adapter import TargetAppTemplateAdapter
from src.adapters.xiaohongshu_adapter import XiaohongshuAdapter
from src.adapters.xianyu_adapter import XianyuAdapter

ADAPTER_REGISTRY = {
    SettingsDemoAdapter.name: SettingsDemoAdapter,
    TargetAppTemplateAdapter.name: TargetAppTemplateAdapter,
    XiaohongshuAdapter.name: XiaohongshuAdapter,
    XianyuAdapter.name: XianyuAdapter,
}
