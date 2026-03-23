from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.utils.config_loader import load_yaml


@dataclass(slots=True)
class TemplateFieldDefinition:
    key: str
    label: str
    field_type: str
    required: bool = True
    min_value: int | float | None = None
    max_value: int | float | None = None
    step: int | float | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "field_type": self.field_type,
            "required": self.required,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step": self.step,
            "description": self.description,
        }


@dataclass(slots=True)
class TaskTemplateDefinition:
    template_id: str
    display_name: str
    description: str
    config_path: Path
    adapter: str
    package_name: str
    platform: str
    default_options: dict[str, Any]
    light_smoke_overrides: dict[str, Any]
    fields: list[TemplateFieldDefinition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "display_name": self.display_name,
            "description": self.description,
            "adapter": self.adapter,
            "package_name": self.package_name,
            "platform": self.platform,
            "default_options": self.default_options,
            "light_smoke_overrides": self.light_smoke_overrides,
            "fields": [field_item.to_dict() for field_item in self.fields],
        }


class TaskTemplateService:
    """从现有 YAML 模板提炼出前端可用的任务定义。"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._template_map = self._build_templates()

    def list_templates(self) -> list[TaskTemplateDefinition]:
        return list(self._template_map.values())

    def get_template(self, template_id: str) -> TaskTemplateDefinition:
        template = self._template_map.get(template_id)
        if template is None:
            raise KeyError(f"未知模板：{template_id}")
        return template

    def load_template_config(self, template_id: str) -> dict[str, Any]:
        template = self.get_template(template_id)
        return load_yaml(template.config_path)

    def _build_templates(self) -> dict[str, TaskTemplateDefinition]:
        xianyu_path = self.project_root / "configs" / "xianyu_search_demo.yaml"
        xianyu_raw = load_yaml(xianyu_path)
        xiaohongshu_path = self.project_root / "configs" / "xiaohongshu_search_demo.yaml"
        xiaohongshu_raw = load_yaml(xiaohongshu_path)

        return {
            "xianyu_search": TaskTemplateDefinition(
                template_id="xianyu_search",
                display_name="闲鱼采集",
                description="搜索关键词并采集商品详情字段。",
                config_path=xianyu_path,
                adapter=str(xianyu_raw.get("adapter", "xianyu_search")),
                package_name=str(xianyu_raw.get("package_name", "com.taobao.idlefish")),
                platform="xianyu",
                default_options=dict(xianyu_raw.get("adapter_options", {}) or {}),
                light_smoke_overrides={
                    "max_items": 3,
                    "max_scrolls": 3,
                    "max_idle_rounds": 2,
                    "search_timeout": 15,
                    "settle_seconds": 1.0,
                },
                fields=[
                    TemplateFieldDefinition(
                        key="search_keyword",
                        label="搜索关键词",
                        field_type="text",
                        description="要在闲鱼中搜索的关键词。",
                    ),
                    TemplateFieldDefinition(
                        key="max_items",
                        label="采集条数",
                        field_type="number",
                        min_value=1,
                        max_value=200,
                        step=1,
                        description="目标采集商品数量。",
                    ),
                    TemplateFieldDefinition(
                        key="max_scrolls",
                        label="最大翻页次数",
                        field_type="number",
                        min_value=1,
                        max_value=100,
                        step=1,
                        description="搜索结果页最多向下滚动多少轮。",
                    ),
                    TemplateFieldDefinition(
                        key="max_idle_rounds",
                        label="空转轮数",
                        field_type="number",
                        min_value=1,
                        max_value=20,
                        step=1,
                        description="连续多少轮没有新数据就提前结束。",
                    ),
                    TemplateFieldDefinition(
                        key="settle_seconds",
                        label="页面稳定等待",
                        field_type="number",
                        min_value=0.5,
                        max_value=10,
                        step=0.25,
                        description="点击或翻页后的等待秒数。",
                    ),
                    TemplateFieldDefinition(
                        key="search_timeout",
                        label="页面等待超时",
                        field_type="number",
                        min_value=5,
                        max_value=60,
                        step=1,
                        description="等待页面切换的超时时间。",
                    ),
                ],
            ),
            "xiaohongshu_search": TaskTemplateDefinition(
                template_id="xiaohongshu_search",
                display_name="小红书采集",
                description="搜索帖子并采集详情与评论。",
                config_path=xiaohongshu_path,
                adapter=str(xiaohongshu_raw.get("adapter", "xiaohongshu_search")),
                package_name=str(xiaohongshu_raw.get("package_name", "com.xingin.xhs")),
                platform="xiaohongshu",
                default_options=dict(xiaohongshu_raw.get("adapter_options", {}) or {}),
                light_smoke_overrides={
                    "max_items": 3,
                    "max_scrolls": 3,
                    "max_idle_rounds": 2,
                    "max_comments_per_note": 3,
                    "detail_scroll_limit": 3,
                    "comment_scroll_limit": 3,
                    "search_timeout": 15,
                    "settle_seconds": 0.6,
                },
                fields=[
                    TemplateFieldDefinition(
                        key="search_keyword",
                        label="搜索关键词",
                        field_type="text",
                        description="要在小红书中搜索的关键词。",
                    ),
                    TemplateFieldDefinition(
                        key="max_items",
                        label="采集帖子数",
                        field_type="number",
                        min_value=1,
                        max_value=100,
                        step=1,
                        description="目标采集帖子数量。",
                    ),
                    TemplateFieldDefinition(
                        key="max_comments_per_note",
                        label="单帖评论数",
                        field_type="number",
                        min_value=0,
                        max_value=100,
                        step=1,
                        description="每篇帖子最多采多少条一级评论。",
                    ),
                    TemplateFieldDefinition(
                        key="max_scrolls",
                        label="结果翻页次数",
                        field_type="number",
                        min_value=1,
                        max_value=100,
                        step=1,
                        description="搜索结果页最多向下滚动多少轮。",
                    ),
                    TemplateFieldDefinition(
                        key="detail_scroll_limit",
                        label="图文详情滚动",
                        field_type="number",
                        min_value=1,
                        max_value=30,
                        step=1,
                        description="图文详情页最多滚动多少轮寻找评论。",
                    ),
                    TemplateFieldDefinition(
                        key="comment_scroll_limit",
                        label="视频评论滚动",
                        field_type="number",
                        min_value=1,
                        max_value=30,
                        step=1,
                        description="视频评论浮层最多滚动多少轮。",
                    ),
                    TemplateFieldDefinition(
                        key="settle_seconds",
                        label="页面稳定等待",
                        field_type="number",
                        min_value=0.25,
                        max_value=10,
                        step=0.05,
                        description="点击或翻页后的等待秒数。",
                    ),
                    TemplateFieldDefinition(
                        key="search_timeout",
                        label="页面等待超时",
                        field_type="number",
                        min_value=5,
                        max_value=60,
                        step=1,
                        description="等待页面切换的超时时间。",
                    ),
                ],
            ),
        }
