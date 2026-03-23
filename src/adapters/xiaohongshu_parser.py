from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from src.core.ui_xml import Bounds, collect_node_texts, normalize_ui_text, parse_bounds


COUNT_TEXT_RE = re.compile(r"(?P<number>\d+(?:\.\d+)?)(?P<unit>万)?\+?$")
ACTION_COUNT_RE = re.compile(r"^(点赞|收藏|评论)\s*(?P<count>\d+(?:\.\d+)?万?\+?)$")
COMMENT_TOTAL_RE = re.compile(r"共\s*(\d+)\s*条评论")
TOPIC_RE = re.compile(r"#([^#\n]+?)(?:\[话题\])?#")
COMMENT_META_PATTERNS = (
    re.compile(r"^(昨天\s+\d{2}:\d{2})\s+(.+)$"),
    re.compile(r"^(今天\s+\d{2}:\d{2})\s+(.+)$"),
    re.compile(r"^(\d{4}-\d{2}-\d{2})\s*(.+)$"),
    re.compile(r"^(\d{2}-\d{2})\s*(.+)$"),
    re.compile(r"^(\d+天前)\s+(.+)$"),
    re.compile(r"^(\d+小时前)\s+(.+)$"),
    re.compile(r"^(\d+分钟前)\s+(.+)$"),
    re.compile(r"^(\d+小时前)(.+)$"),
    re.compile(r"^(\d+分钟前)(.+)$"),
)
COMMENT_REPLY_BUTTON_RE = re.compile(r"^展开\s+\d+\s+条回复$")
IMAGE_COUNT_TEXT_RE = re.compile(r"^共\s*\d+\s*张$")

CARD_NOISE_TEXTS = {
    "广告",
    "综合",
    "可购买",
    "最新",
    "全部",
    "用户",
    "商品",
    "图片",
    "问一问",
    "返回",
}

DETAIL_NOISE_TEXTS = {
    "关注",
    "评论框",
    "说点什么...",
    "留下你的想法吧",
    "让大家听到你的声音",
    "不喜欢",
    "地点",
    "猜你想搜",
    "作者",
    "搜索",
    "分享",
    "暂停",
    "返回",
}


@dataclass(slots=True)
class XiaohongshuSearchCandidate:
    signature: str
    bounds: Bounds
    title_hint: str
    author_name: str
    liked_count_text: str

    def tap_point(self) -> tuple[int, int]:
        return self.bounds.upper_tap_point()


@dataclass(slots=True)
class XiaohongshuComment:
    author_name: str
    content_text: str
    published_text: str
    ip_location: str
    like_count: int | None
    like_count_text: str
    is_author: bool

    @property
    def signature(self) -> str:
        return "|".join([self.author_name, self.content_text, self.published_text, self.ip_location])

    def to_dict(self) -> dict[str, object]:
        return {
            "author_name": self.author_name,
            "content_text": self.content_text,
            "published_text": self.published_text,
            "ip_location": self.ip_location,
            "like_count": self.like_count,
            "like_count_text": self.like_count_text,
            "is_author": self.is_author,
        }


@dataclass(slots=True)
class XiaohongshuNoteDetail:
    note_type: str
    title: str = ""
    title_source_score: int = 0
    content_text: str = ""
    content_source_score: int = 0
    author_name: str = ""
    author_id: str = ""
    location_text: str = ""
    location_query: str = ""
    published_text: str = ""
    ip_location: str = ""
    like_count: int | None = None
    like_count_text: str = ""
    favorite_count: int | None = None
    favorite_count_text: str = ""
    comment_count: int | None = None
    comment_count_text: str = ""
    comment_total_count: int | None = None
    note_notice: str = ""
    topics: list[str] = field(default_factory=list)

    def merge(self, other: "XiaohongshuNoteDetail") -> None:
        if _should_replace_note_title(
            current_title=self.title,
            current_score=self.title_source_score,
            incoming_title=other.title,
            incoming_score=other.title_source_score,
        ):
            self.title = other.title
            self.title_source_score = other.title_source_score
        if _should_replace_note_content(
            current_text=self.content_text,
            current_score=self.content_source_score,
            incoming_text=other.content_text,
            incoming_score=other.content_source_score,
        ):
            self.content_text = other.content_text
            self.content_source_score = other.content_source_score
            self.topics = list(other.topics)
        if other.author_name and not self.author_name:
            self.author_name = other.author_name
        if other.author_id and not self.author_id:
            self.author_id = other.author_id
        if other.location_text and not self.location_text:
            self.location_text = other.location_text
        if other.location_query and not self.location_query:
            self.location_query = other.location_query
        if other.published_text and not self.published_text:
            self.published_text = other.published_text
        if other.ip_location and not self.ip_location:
            self.ip_location = other.ip_location
        if other.like_count is not None and self.like_count is None:
            self.like_count = other.like_count
        if other.like_count_text and not self.like_count_text:
            self.like_count_text = other.like_count_text
        if other.favorite_count is not None and self.favorite_count is None:
            self.favorite_count = other.favorite_count
        if other.favorite_count_text and not self.favorite_count_text:
            self.favorite_count_text = other.favorite_count_text
        if other.comment_count is not None and self.comment_count is None:
            self.comment_count = other.comment_count
        if other.comment_count_text and not self.comment_count_text:
            self.comment_count_text = other.comment_count_text
        if other.comment_total_count is not None and self.comment_total_count is None:
            self.comment_total_count = other.comment_total_count
        if other.note_notice and not self.note_notice:
            self.note_notice = other.note_notice
        for topic in other.topics:
            if topic not in self.topics:
                self.topics.append(topic)
        self.finalize_text_fields()

    def finalize_text_fields(self) -> None:
        if self.content_text and not self.topics:
            self.topics = _extract_topics(self.content_text)
        if not self.title and self.content_text:
            self.title = _pick_title_from_content(self.content_text)
            self.title_source_score = max(self.title_source_score, 1)


def parse_search_result_candidates(hierarchy_xml: str) -> list[XiaohongshuSearchCandidate]:
    root = ET.fromstring(hierarchy_xml)
    recycler = _find_search_results_recycler(root)
    if recycler is None:
        return []

    candidates: list[XiaohongshuSearchCandidate] = []
    seen_signatures: set[str] = set()
    for child in recycler.findall("node"):
        bounds = parse_bounds(child.attrib.get("bounds", ""))
        if bounds is None or bounds.top < 500 or bounds.width < 450 or bounds.height < 250:
            continue

        texts = collect_node_texts(child)
        if not texts or "广告" in texts:
            continue

        title_hint = _pick_card_title(texts)
        if not title_hint:
            continue
        author_name = _pick_card_author(texts)
        liked_count_text = _pick_card_like_count(texts)
        clickable_bounds = _find_primary_clickable_bounds(child) or bounds
        signature = "|".join([title_hint, author_name, liked_count_text])
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        candidates.append(
            XiaohongshuSearchCandidate(
                signature=signature,
                bounds=clickable_bounds,
                title_hint=title_hint,
                author_name=author_name,
                liked_count_text=liked_count_text,
            )
        )
    return candidates


def parse_image_detail_snapshot(hierarchy_xml: str, visible_texts: list[str]) -> XiaohongshuNoteDetail:
    root = ET.fromstring(hierarchy_xml)
    clean_texts = _clean_visible_texts(visible_texts)
    title, title_source_score, content_text, content_source_score = _pick_image_title_and_content(root, clean_texts)
    published_text, ip_location, note_notice = _split_note_meta(_pick_image_meta_text(root, clean_texts))
    like_count, like_count_text = _parse_action_count(root, clean_texts, "点赞")
    favorite_count, favorite_count_text = _parse_action_count(root, clean_texts, "收藏")
    comment_count, comment_count_text = _parse_action_count(root, clean_texts, "评论")
    return XiaohongshuNoteDetail(
        note_type="image",
        title=title or _pick_title_from_content(content_text),
        title_source_score=title_source_score or (1 if content_text else 0),
        content_text=content_text,
        content_source_score=content_source_score,
        author_name=_find_text_by_resource_id(root, "com.xingin.xhs:id/nickNameTV"),
        author_id=_find_text_by_resource_id(root, "com.xingin.xhs:id/nickNameTV"),
        location_text=_pick_value_after_marker(clean_texts, "地点"),
        location_query=_pick_value_after_marker(clean_texts, "猜你想搜"),
        published_text=published_text,
        ip_location=ip_location,
        like_count=like_count,
        like_count_text=like_count_text,
        favorite_count=favorite_count,
        favorite_count_text=favorite_count_text,
        comment_count=comment_count,
        comment_count_text=comment_count_text,
        comment_total_count=parse_total_comment_count(clean_texts),
        note_notice=note_notice,
        topics=_extract_topics(content_text),
    )


def parse_video_detail_snapshot(hierarchy_xml: str, visible_texts: list[str]) -> XiaohongshuNoteDetail:
    root = ET.fromstring(hierarchy_xml)
    clean_texts = _clean_visible_texts(visible_texts)
    content_text, content_source_score = _pick_video_content(root, clean_texts)
    title = _pick_title_from_content(content_text)
    like_count_text = _pick_video_like_count_text(clean_texts)
    return XiaohongshuNoteDetail(
        note_type="video",
        title=title,
        title_source_score=2 if title else 0,
        content_text=content_text,
        content_source_score=content_source_score,
        author_name=_find_text_by_resource_id(root, "com.xingin.xhs:id/matrixNickNameView"),
        author_id=_find_text_by_resource_id(root, "com.xingin.xhs:id/matrixNickNameView"),
        like_count=parse_count_text(like_count_text),
        like_count_text=like_count_text,
        favorite_count=_parse_action_count(root, clean_texts, "收藏")[0],
        favorite_count_text=_parse_action_count(root, clean_texts, "收藏")[1],
        comment_count=_parse_action_count(root, clean_texts, "评论")[0],
        comment_count_text=_parse_action_count(root, clean_texts, "评论")[1],
        topics=_extract_topics(content_text),
    )


def parse_video_comment_panel_snapshot(hierarchy_xml: str, visible_texts: list[str]) -> XiaohongshuNoteDetail:
    root = ET.fromstring(hierarchy_xml)
    clean_texts = _clean_visible_texts(visible_texts)
    content_text, author_name, meta_text, content_source_score = _pick_video_panel_intro(clean_texts)
    published_text, ip_location, note_notice = _split_note_meta(meta_text)
    title = _pick_title_from_content(content_text)
    return XiaohongshuNoteDetail(
        note_type="video",
        title=title,
        title_source_score=2 if title else 0,
        content_text=content_text,
        content_source_score=content_source_score,
        author_name=author_name or _find_text_by_resource_id(root, "com.xingin.xhs:id/matrixNickNameView"),
        author_id=author_name or _find_text_by_resource_id(root, "com.xingin.xhs:id/matrixNickNameView"),
        published_text=published_text,
        ip_location=ip_location,
        comment_total_count=parse_total_comment_count(clean_texts),
        note_notice=note_notice,
        topics=_extract_topics(content_text),
    )


def parse_comment_entries(hierarchy_xml: str) -> list[XiaohongshuComment]:
    root = ET.fromstring(hierarchy_xml)
    recycler = _find_comment_recycler(root)
    if recycler is None:
        return []

    comments: list[XiaohongshuComment] = []
    seen_signatures: set[str] = set()
    candidate_blocks: list[tuple[int, int, int, list[str]]] = []
    for node in recycler.iter("node"):
        if node is recycler:
            continue
        bounds = parse_bounds(node.attrib.get("bounds", ""))
        if bounds is None or bounds.width < 360 or bounds.height < 120 or bounds.height > 720:
            continue
        texts = collect_node_texts(node)
        if not _looks_like_comment_block(texts):
            continue
        candidate_blocks.append((bounds.top, bounds.left, bounds.area, texts))

    for _, _, _, texts in sorted(candidate_blocks, key=lambda item: (item[0], item[1], item[2])):
        comment = _parse_comment_texts(texts)
        if comment is None or comment.signature in seen_signatures:
            continue
        seen_signatures.add(comment.signature)
        comments.append(comment)
    return comments


def has_comment_recycler(hierarchy_xml: str) -> bool:
    root = ET.fromstring(hierarchy_xml)
    return _find_comment_recycler(root) is not None


def parse_total_comment_count(visible_texts: list[str]) -> int | None:
    for text in visible_texts:
        match = COMMENT_TOTAL_RE.search(text)
        if match:
            return int(match.group(1))
    return None


def find_action_button_bounds(hierarchy_xml: str, label: str) -> Bounds | None:
    root = ET.fromstring(hierarchy_xml)
    for node in root.iter("node"):
        content_desc = normalize_ui_text(node.attrib.get("content-desc", ""))
        if not content_desc.startswith(label):
            continue
        bounds = parse_bounds(node.attrib.get("bounds", ""))
        if bounds is not None:
            return bounds
    return None


def parse_count_text(text: str) -> int | None:
    value = normalize_ui_text(text)
    if not value:
        return None
    match = COUNT_TEXT_RE.fullmatch(value)
    if not match:
        return None
    number = float(match.group("number"))
    if match.group("unit") == "万":
        number *= 10_000
    return int(number)


def _find_search_results_recycler(root: ET.Element) -> ET.Element | None:
    best_node: ET.Element | None = None
    best_score = -1
    for node in root.iter("node"):
        if node.attrib.get("class") != "androidx.recyclerview.widget.RecyclerView":
            continue
        bounds = parse_bounds(node.attrib.get("bounds", ""))
        if bounds is None or bounds.height < 1200:
            continue
        score = 0
        for child in node.findall("node"):
            child_bounds = parse_bounds(child.attrib.get("bounds", ""))
            if child_bounds is None or child_bounds.top < 500:
                continue
            if child_bounds.width >= 450 and child_bounds.height >= 250:
                score += 1
        if score > best_score:
            best_score = score
            best_node = node
    return best_node


def _find_comment_recycler(root: ET.Element) -> ET.Element | None:
    best_node: ET.Element | None = None
    best_score = 0
    for node in root.iter("node"):
        if node.attrib.get("class") != "androidx.recyclerview.widget.RecyclerView":
            continue
        bounds = parse_bounds(node.attrib.get("bounds", ""))
        if bounds is None or bounds.height < 320:
            continue
        texts = collect_node_texts(node)
        comment_meta_count = sum(1 for text in texts if _looks_like_comment_meta(text))
        author_count = sum(1 for text in texts if _looks_like_comment_author_name(text))
        reply_button_count = sum(1 for text in texts if COMMENT_REPLY_BUTTON_RE.fullmatch(text))
        score = comment_meta_count * 8
        score += min(author_count, max(1, comment_meta_count)) * 3
        score += reply_button_count
        if node.attrib.get("scrollable") == "true":
            score += 2
        if bounds.top >= 850:
            score += 1
        if any(COMMENT_TOTAL_RE.search(text) for text in texts):
            score += 4
        if score > best_score:
            best_score = score
            best_node = node
    if best_score < 8:
        return None
    return best_node


def _find_primary_clickable_bounds(node: ET.Element) -> Bounds | None:
    best: Bounds | None = None
    for sub in node.iter("node"):
        if sub.attrib.get("clickable") != "true":
            continue
        bounds = parse_bounds(sub.attrib.get("bounds", ""))
        if bounds is None or bounds.width < 300 or bounds.height < 250:
            continue
        if best is None or bounds.area > best.area:
            best = bounds
    return best


def _pick_card_title(texts: list[str]) -> str:
    for text in texts:
        if text in CARD_NOISE_TEXTS or _looks_like_card_date(text):
            continue
        if _looks_like_count_text(text):
            continue
        if len(text.replace(" ", "")) < 8:
            continue
        return text
    return ""


def _pick_card_author(texts: list[str]) -> str:
    for text in texts:
        compact = text.strip()
        if not compact or compact in CARD_NOISE_TEXTS or _looks_like_card_date(compact):
            continue
        if _looks_like_count_text(compact):
            continue
        if len(compact) <= 20 and not _looks_like_title_like_text(compact):
            return compact
    return ""


def _pick_card_like_count(texts: list[str]) -> str:
    for text in reversed(texts):
        if _looks_like_count_text(text):
            return text
    return ""


def _pick_image_title_and_content(root: ET.Element, clean_texts: list[str]) -> tuple[str, int, str, int]:
    layout = _find_first_node_by_resource_id(root, "com.xingin.xhs:id/noteContentLayout")
    if layout is not None:
        layout_texts = [text for text in collect_node_texts(layout) if normalize_ui_text(text)]
        title, content_text = _pick_title_and_content_from_texts(layout_texts)
        if title or content_text:
            return title, (3 if title else 0), content_text, (3 if content_text else 0)

    note_candidates = _pick_note_candidate_texts(clean_texts)
    title, content_text = _pick_title_and_content_from_texts(note_candidates)
    return title, (1 if title else 0), content_text, (1 if content_text else 0)


def _pick_image_content(root: ET.Element, clean_texts: list[str]) -> tuple[str, int]:
    layout = _find_first_node_by_resource_id(root, "com.xingin.xhs:id/noteContentLayout")
    if layout is not None:
        for text in collect_node_texts(layout):
            if _looks_like_note_content(text):
                return text, 3

    for text in _pick_note_candidate_texts(clean_texts):
        if _looks_like_note_content(text):
            return text, 1
    return "", 0


def _pick_video_content(root: ET.Element, clean_texts: list[str]) -> tuple[str, int]:
    for node in root.iter("node"):
        if node.attrib.get("resource-id") != "com.xingin.xhs:id/noteContentText":
            continue
        content_desc = normalize_ui_text(node.attrib.get("content-desc", ""))
        text = normalize_ui_text(node.attrib.get("text", ""))
        if content_desc:
            return content_desc, 3
        if text:
            return text, 3

    for text in _pick_note_candidate_texts(clean_texts):
        if _looks_like_note_content(text):
            return text, 1
    return "", 0


def _pick_image_meta_text(root: ET.Element, clean_texts: list[str]) -> str:
    for node in root.iter("node"):
        content_desc = normalize_ui_text(node.attrib.get("content-desc", ""))
        if _looks_like_note_meta(content_desc):
            return content_desc
    for text in clean_texts:
        if _looks_like_note_meta(text):
            return text
    return ""


def _parse_action_count(root: ET.Element, clean_texts: list[str], action_label: str) -> tuple[int | None, str]:
    for node in root.iter("node"):
        content_desc = normalize_ui_text(node.attrib.get("content-desc", ""))
        match = ACTION_COUNT_RE.fullmatch(content_desc)
        if match is None or content_desc[:2] != action_label:
            continue
        count_text = match.group("count")
        return parse_count_text(count_text), count_text

    for text in clean_texts:
        match = ACTION_COUNT_RE.fullmatch(text)
        if match is None or text[:2] != action_label:
            continue
        count_text = match.group("count")
        return parse_count_text(count_text), count_text
    return None, ""


def _pick_video_like_count_text(clean_texts: list[str]) -> str:
    for index, text in enumerate(clean_texts):
        if not _looks_like_count_text(text):
            continue
        next_text = clean_texts[index + 1] if index + 1 < len(clean_texts) else ""
        if next_text.startswith("收藏"):
            return text
    return ""


def _pick_video_panel_intro(clean_texts: list[str]) -> tuple[str, str, str, int]:
    intro_texts: list[str] = []
    note_meta_text = ""
    for text in clean_texts:
        if COMMENT_TOTAL_RE.search(text):
            continue
        if text.startswith("猜你想搜"):
            continue
        if text in {"让大家听到你的声音", "留下你的想法吧", "不喜欢"}:
            continue
        intro_texts.append(text)
        if _looks_like_note_meta(text):
            note_meta_text = text
            break
        if _looks_like_comment_meta(text):
            break
    if not note_meta_text:
        return "", "", "", 0

    author_name = ""
    for index, text in enumerate(intro_texts):
        if text != "作者":
            continue
        for candidate in reversed(intro_texts[:index]):
            if _looks_like_author_name(candidate):
                author_name = candidate
                break
        if author_name:
            break
    if not author_name:
        author_name = next((text for text in intro_texts if _looks_like_author_name(text)), "")

    content_text = ""
    for text in intro_texts:
        if text in {"作者", author_name}:
            continue
        if text == note_meta_text or _looks_like_note_meta(text):
            break
        if _looks_like_note_content(text):
            content_text = text
            break
    if not content_text:
        return "", author_name, note_meta_text, 0
    return content_text, author_name, note_meta_text, 2


def _parse_comment_texts(texts: list[str]) -> XiaohongshuComment | None:
    clean_texts = [normalize_ui_text(text) for text in texts if normalize_ui_text(text)]
    if not clean_texts:
        return None

    metadata = next((text for text in clean_texts if _looks_like_comment_meta(text)), "")
    if not metadata:
        return None

    metadata_index = clean_texts.index(metadata)
    prefix_texts = [text for text in clean_texts[:metadata_index] if text != "作者"]
    author_index = -1
    author_name = ""
    for index, text in enumerate(prefix_texts):
        if _looks_like_comment_author_name(text):
            author_name = text
            author_index = index
            break
    if author_index < 0:
        return None

    body_parts: list[str] = []
    for text in prefix_texts[author_index + 1 :]:
        if _looks_like_comment_body(text, author_name=author_name):
            body_parts.append(text)
    content_text = "\n".join(body_parts).strip()
    if not author_name or not content_text:
        return None

    published_text, ip_location = _split_comment_meta(metadata)
    like_count_text = ""
    for text in clean_texts[metadata_index + 1 :]:
        if _looks_like_count_text(text):
            like_count_text = text
            break

    return XiaohongshuComment(
        author_name=author_name,
        content_text=content_text,
        published_text=published_text,
        ip_location=ip_location,
        like_count=parse_count_text(like_count_text),
        like_count_text=like_count_text,
        is_author="作者" in clean_texts,
    )


def _pick_title_from_content(content_text: str) -> str:
    lines = [line.strip() for line in content_text.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


def _extract_topics(content_text: str) -> list[str]:
    topics: list[str] = []
    for match in TOPIC_RE.finditer(content_text):
        topic = normalize_ui_text(match.group(1))
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def _pick_value_after_marker(texts: list[str], marker: str) -> str:
    for index, text in enumerate(texts):
        if text != marker:
            continue
        if index + 1 < len(texts):
            return texts[index + 1]
    return ""


def _split_note_meta(text: str) -> tuple[str, str, str]:
    value = normalize_ui_text(text)
    if not value:
        return "", "", ""
    for pattern in COMMENT_META_PATTERNS:
        match = pattern.fullmatch(value)
        if match is None:
            continue
        published_text = match.group(1).strip()
        region_with_notice = match.group(2).strip()
        ip_location, note_notice = _split_region_and_notice(region_with_notice)
        return published_text, ip_location, note_notice
    return value, "", ""


def _split_comment_meta(text: str) -> tuple[str, str]:
    value = normalize_ui_text(text).replace(" 回复", "").strip()
    if not value:
        return "", ""
    for pattern in COMMENT_META_PATTERNS:
        match = pattern.fullmatch(value)
        if match is None:
            continue
        return match.group(1).strip(), match.group(2).strip()
    return value, ""


def _split_region_and_notice(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _find_text_by_resource_id(root: ET.Element, resource_id: str) -> str:
    for node in root.iter("node"):
        if node.attrib.get("resource-id") != resource_id:
            continue
        text = normalize_ui_text(node.attrib.get("text", ""))
        if text:
            return text
        content_desc = normalize_ui_text(node.attrib.get("content-desc", ""))
        if content_desc:
            return content_desc
    return ""


def _find_first_node_by_resource_id(root: ET.Element, resource_id: str) -> ET.Element | None:
    for node in root.iter("node"):
        if node.attrib.get("resource-id") == resource_id:
            return node
    return None


def _clean_visible_texts(visible_texts: list[str]) -> list[str]:
    result: list[str] = []
    for text in visible_texts:
        value = normalize_ui_text(text)
        if not value or value in DETAIL_NOISE_TEXTS:
            continue
        if _looks_like_status_time(value):
            continue
        if value.startswith("共 ") and value.endswith(" 条评论"):
            result.append(value)
            continue
        if value.startswith("点赞 ") or value.startswith("收藏 ") or value.startswith("评论 "):
            result.append(value)
            continue
        if value.startswith("电量剩余"):
            continue
        if value in {"Android 系统通知：", "天气通知：", "蓝牙开启。", "振铃器静音。", "WLAN 信号强度满格。", "无 SIM 卡。"}:
            continue
        result.append(value)
    return result


def _looks_like_note_content(text: str) -> bool:
    if not text or text in DETAIL_NOISE_TEXTS:
        return False
    if text.startswith("图片,") or text.startswith("长按边缘") or text.startswith("已播放到"):
        return False
    if IMAGE_COUNT_TEXT_RE.fullmatch(text):
        return False
    if COMMENT_REPLY_BUTTON_RE.fullmatch(text):
        return False
    if COMMENT_TOTAL_RE.search(text):
        return False
    if _looks_like_comment_meta(text):
        return False
    if _looks_like_note_meta(text):
        return False
    return ("#" in text) or ("\n" in text) or len(text.replace(" ", "")) >= 16


def _looks_like_note_title(text: str) -> bool:
    value = normalize_ui_text(text)
    if not value or value in DETAIL_NOISE_TEXTS:
        return False
    if value.startswith("图片,") or value.startswith("猜你想搜"):
        return False
    if IMAGE_COUNT_TEXT_RE.fullmatch(value) or COMMENT_REPLY_BUTTON_RE.fullmatch(value):
        return False
    if _looks_like_count_text(value) or _looks_like_note_meta(value) or _looks_like_comment_meta(value):
        return False
    compact = value.replace(" ", "")
    if len(compact) < 2 or len(compact) > 48:
        return False
    if "\n" in value:
        return False
    if value.startswith("#") and value.count("#") >= 2:
        return False
    return True


def _looks_like_note_meta(text: str) -> bool:
    value = normalize_ui_text(text)
    if not value or "回复" in value:
        return False
    return any(pattern.fullmatch(value) for pattern in COMMENT_META_PATTERNS)


def _looks_like_comment_author_name(text: str) -> bool:
    value = normalize_ui_text(text)
    if not value or value in DETAIL_NOISE_TEXTS:
        return False
    if _looks_like_status_time(value):
        return False
    if _looks_like_comment_meta(value) or _looks_like_count_text(value) or _looks_like_note_meta(value):
        return False
    if IMAGE_COUNT_TEXT_RE.fullmatch(value) or COMMENT_REPLY_BUTTON_RE.fullmatch(value):
        return False
    if len(value) > 24:
        return False
    return True


def _looks_like_author_name(text: str) -> bool:
    value = normalize_ui_text(text)
    return _looks_like_comment_author_name(value) and not _looks_like_note_content(value)


def _looks_like_count_text(text: str) -> bool:
    return bool(COUNT_TEXT_RE.fullmatch(normalize_ui_text(text)))


def _looks_like_card_date(text: str) -> bool:
    value = normalize_ui_text(text)
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or re.fullmatch(r"\d+天前", value))


def _looks_like_title_like_text(text: str) -> bool:
    compact = text.replace(" ", "")
    return len(compact) >= 8 and not _looks_like_count_text(text)


def _should_replace_note_content(
    *,
    current_text: str,
    current_score: int,
    incoming_text: str,
    incoming_score: int,
) -> bool:
    if not incoming_text:
        return False
    if not current_text:
        return True
    if incoming_score > current_score:
        return True
    if incoming_score != current_score:
        return False
    return bool(current_text and incoming_text.startswith(current_text) and len(incoming_text) > len(current_text))


def _should_replace_note_title(
    *,
    current_title: str,
    current_score: int,
    incoming_title: str,
    incoming_score: int,
) -> bool:
    if not incoming_title:
        return False
    if not current_title:
        return True
    if incoming_score > current_score:
        return True
    if incoming_score != current_score:
        return False
    return len(incoming_title) > len(current_title)


def _pick_note_candidate_texts(clean_texts: list[str]) -> list[str]:
    candidates: list[str] = []
    for text in clean_texts:
        if COMMENT_TOTAL_RE.search(text) or _looks_like_comment_meta(text):
            break
        if text.startswith("点赞 ") or text.startswith("收藏 ") or text.startswith("评论 "):
            continue
        if _looks_like_count_text(text) or text in {"地点", "猜你想搜", "不喜欢"}:
            continue
        candidates.append(text)
    return candidates


def _pick_title_and_content_from_texts(texts: list[str]) -> tuple[str, str]:
    clean_texts = [normalize_ui_text(text) for text in texts if normalize_ui_text(text)]
    if not clean_texts:
        return "", ""

    content_index = -1
    content_text = ""
    for index, text in enumerate(clean_texts):
        if _looks_like_note_content(text):
            content_index = index
            content_text = text
            break

    title = ""
    if content_index > 0:
        for candidate in reversed(clean_texts[:content_index]):
            if _looks_like_note_title(candidate):
                title = candidate
                break

    if not title:
        for text in clean_texts:
            if text == content_text:
                continue
            if _looks_like_note_title(text):
                title = text
                break

    return title, content_text


def _looks_like_comment_block(texts: list[str]) -> bool:
    if not texts:
        return False
    if not any(_looks_like_comment_meta(text) for text in texts):
        return False
    return any(_looks_like_comment_author_name(text) for text in texts)


def _looks_like_comment_meta(text: str) -> bool:
    value = normalize_ui_text(text)
    if not value:
        return False
    if COMMENT_REPLY_BUTTON_RE.fullmatch(value):
        return False
    if "笔记含" in value or "作者自主声明" in value:
        return False
    candidate = value.replace(" 回复", "").strip()
    return any(pattern.fullmatch(candidate) for pattern in COMMENT_META_PATTERNS)


def _looks_like_comment_body(text: str, *, author_name: str) -> bool:
    value = normalize_ui_text(text)
    if not value or value == author_name or value == "作者":
        return False
    if _looks_like_count_text(value) or _looks_like_comment_meta(value) or _looks_like_note_meta(value):
        return False
    if COMMENT_REPLY_BUTTON_RE.fullmatch(value) or IMAGE_COUNT_TEXT_RE.fullmatch(value):
        return False
    if value in {"置顶评论", "不喜欢"}:
        return False
    if value.startswith("图片,") or value.startswith("猜你想搜"):
        return False
    return True


def _looks_like_status_time(text: str) -> bool:
    value = normalize_ui_text(text)
    return bool(re.fullmatch(r"\d{1,2}:\d{2}", value))
