from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class CollectedRecord:
    """统一的结构化采集记录。"""

    platform: str
    record_type: str
    keyword: str = ""
    title: str = ""
    content_text: str = ""
    author_name: str = ""
    author_id: str = ""
    location_text: str = ""
    ip_location: str = ""
    published_text: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    raw_visible_texts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
