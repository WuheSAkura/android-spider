from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.utils.exceptions import ConfigError


SUPPORTED_SELECTOR_KEYS = ("resource_id", "text", "description", "xpath")


@dataclass(frozen=True, slots=True)
class Selector:
    text: str | None = None
    resource_id: str | None = None
    description: str | None = None
    xpath: str | None = None

    def strategies(self) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        if self.resource_id:
            candidates.append(("resource_id", self.resource_id))
        if self.text:
            candidates.append(("text", self.text))
        if self.description:
            candidates.append(("description", self.description))
        if self.xpath:
            candidates.append(("xpath", self.xpath))
        return candidates


def selector_from_mapping(data: dict[str, Any]) -> Selector:
    selector = Selector(
        text=data.get("text"),
        resource_id=data.get("resource_id"),
        description=data.get("description"),
        xpath=data.get("xpath"),
    )
    if not selector.strategies():
        raise ConfigError("selector 未配置有效定位字段，至少需要 text/resource_id/description/xpath 之一。")
    return selector


def resolve_selector(selector_ref: str | dict[str, Any] | None, selector_map: dict[str, dict[str, Any]]) -> Selector:
    if selector_ref is None:
        raise ConfigError("当前步骤缺少 selector 配置。")

    if isinstance(selector_ref, str):
        if selector_ref in selector_map:
            return selector_from_mapping(selector_map[selector_ref])
        return Selector(text=selector_ref)

    if isinstance(selector_ref, dict):
        if "name" in selector_ref:
            selector_name = str(selector_ref["name"])
            if selector_name not in selector_map:
                raise ConfigError(f"引用了不存在的 selector：{selector_name}")
            return selector_from_mapping(selector_map[selector_name])

        allowed_values = {key: value for key, value in selector_ref.items() if key in SUPPORTED_SELECTOR_KEYS}
        if not allowed_values:
            raise ConfigError("selector 字典中没有可识别的定位字段。")
        return selector_from_mapping(allowed_values)

    raise ConfigError("selector 配置格式不正确，只支持字符串或对象。")

