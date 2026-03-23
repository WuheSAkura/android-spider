from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

from src.utils.exceptions import DriverError


IGNORED_NODE_PACKAGES = {
    "com.android.systemui",
    "com.github.uiautomator",
    "gesture",
}

HIDDEN_TEXT_TOKENS = ("\u200b", "\ufeff", "\u2060", "\u00a0", "\u200c", "\u200d", "\ufffc")
BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True, slots=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def upper_tap_point(self) -> tuple[int, int]:
        width = max(1, self.right - self.left)
        height = max(1, self.bottom - self.top)
        x = self.left + width // 2
        y = self.top + min(max(height // 3, 80), 220)
        return x, min(y, self.bottom - 12)

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height


def parse_bounds(bounds_text: str) -> Bounds | None:
    match = BOUNDS_RE.fullmatch(bounds_text.strip())
    if not match:
        return None
    left, top, right, bottom = (int(value) for value in match.groups())
    return Bounds(left, top, right, bottom)


def normalize_ui_text(text: str) -> str:
    value = text.replace("&#10;", "\n").strip()
    for token in HIDDEN_TEXT_TOKENS:
        value = value.replace(token, "")
    return value.strip()


def is_ignored_package(package_name: str) -> bool:
    return package_name in IGNORED_NODE_PACKAGES


def iter_visible_nodes(root: ET.Element | ET.ElementTree) -> Iterable[ET.Element]:
    iterator = root.iter("node") if isinstance(root, ET.Element) else root.iter("node")
    for node in iterator:
        if is_ignored_package(node.attrib.get("package", "")):
            continue
        yield node


def collect_node_texts(node: ET.Element) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for sub in iter_visible_nodes(node):
        for key in ("text", "content-desc"):
            text = normalize_ui_text(sub.attrib.get(key, ""))
            if not text or text in seen:
                continue
            seen.add(text)
            texts.append(text)
    return texts


def extract_visible_texts_from_xml(hierarchy_xml: str) -> list[str]:
    try:
        root = ET.fromstring(hierarchy_xml)
    except ET.ParseError as exc:
        raise DriverError("页面层级 XML 解析失败，无法提取可见文本。") from exc

    texts: list[str] = []
    seen: set[str] = set()
    for node in iter_visible_nodes(root):
        for key in ("text", "content-desc"):
            value = normalize_ui_text(node.attrib.get(key, ""))
            if not value or value in seen:
                continue
            seen.add(value)
            texts.append(value)
    return texts
