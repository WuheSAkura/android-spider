from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
PRICE_LINE_RE = re.compile(r"(\d+(?:\.\d+)?)")
WANT_RE = re.compile(r"(\d+)\s*人想要")
VIEW_RE = re.compile(r"(\d+)\s*(?:看过|浏览)")
REGION_RE = re.compile(r"([\u4e00-\u9fa5]{2,8})发货")

LIST_NOISE_KEYWORDS = (
    "马上抢",
    "抢限量优惠券",
    "立即购买",
    "综合",
    "价格",
    "降价",
    "新发",
    "区域",
    "筛选",
    "验货宝",
    "存储容量",
    "成色",
    "拆修和功能",
    "版本",
    "品牌",
    "运行内存",
)

DETAIL_NOISE_TEXTS = {
    "返回",
    "搜索栏",
    "分享",
    "更多",
    "用户区域关注",
    "买前了解退货规则，保障你的交易权益",
    "宝贝图片1",
    "留言按钮",
    "收藏",
    "我想要按钮",
    "按钮",
}


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
    def area(self) -> int:
        return max(0, self.right - self.left) * max(0, self.bottom - self.top)


@dataclass(slots=True)
class XianyuListCandidate:
    signature: str
    bounds: Bounds
    title_hint: str

    def tap_point(self) -> tuple[int, int]:
        return self.bounds.upper_tap_point()


@dataclass(slots=True)
class XianyuDetailData:
    title: str
    price: str
    seller_name: str
    seller_region: str
    want_count: int | None
    view_count: int | None
    message_text: str
    detail_text: str
    detail_visible_texts: list[str]


def parse_bounds(bounds_text: str) -> Bounds | None:
    match = BOUNDS_RE.fullmatch(bounds_text.strip())
    if not match:
        return None
    left, top, right, bottom = (int(value) for value in match.groups())
    return Bounds(left, top, right, bottom)


def parse_search_result_candidates(hierarchy_xml: str) -> list[XianyuListCandidate]:
    root = ET.fromstring(hierarchy_xml)
    recycler = _find_first_node(root, "resource-id", "com.taobao.idlefish:id/nested_recycler_view")
    if recycler is None:
        return []

    candidates: list[XianyuListCandidate] = []
    seen_signatures: set[str] = set()
    for child in recycler.findall("node"):
        child_bounds = parse_bounds(child.attrib.get("bounds", ""))
        if child_bounds is None or child_bounds.area < 60_000:
            continue

        texts = _collect_texts(child)
        if not _looks_like_product_card(texts):
            continue

        title_hint = _pick_list_title_hint(texts)
        price = _pick_list_price(texts)
        if not title_hint or not price:
            continue

        region = _pick_list_region(texts)
        clickable_bounds = _find_clickable_bounds(child) or child_bounds
        signature = "|".join([title_hint, price, region or ""])
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        candidates.append(
            XianyuListCandidate(
                signature=signature,
                bounds=clickable_bounds,
                title_hint=title_hint,
            )
        )
    return candidates


def parse_detail_data(visible_texts: list[str]) -> XianyuDetailData:
    clean_texts = [item for item in (_normalize_text(text) for text in visible_texts) if item and not _is_system_noise(item)]

    stats_block = next((text for text in clean_texts if "人想要" in text and ("看过" in text or "浏览" in text)), "")
    seller_block = next((text for text in clean_texts if _looks_like_seller_block(text)), "")
    shipping_block = next((text for text in clean_texts if "发货" in text and "包邮" in text), "")
    review_block = next((text for text in clean_texts if "买过的人的评价" in text), "")

    seller_name, seller_region = _parse_seller_block(seller_block)
    if not seller_region:
        seller_region = _parse_region_from_shipping(shipping_block)

    title = _pick_detail_title(clean_texts, stats_block, seller_block)
    price = _parse_price(stats_block) or _pick_price_from_texts(clean_texts) or ""
    want_count = _parse_int_from_texts(clean_texts, WANT_RE)
    view_count = _parse_int_from_texts(clean_texts, VIEW_RE)
    message_text = _pick_message_text(clean_texts)
    detail_text = _pick_detail_text(clean_texts, stats_block, seller_block, shipping_block, review_block, title)

    return XianyuDetailData(
        title=title,
        price=price,
        seller_name=seller_name,
        seller_region=seller_region,
        want_count=want_count,
        view_count=view_count,
        message_text=message_text,
        detail_text=detail_text,
        detail_visible_texts=clean_texts,
    )


def _find_first_node(root: ET.Element, key: str, value: str) -> ET.Element | None:
    for node in root.iter("node"):
        if node.attrib.get(key) == value:
            return node
    return None


def _collect_texts(node: ET.Element) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for sub in node.iter("node"):
        for key in ("text", "content-desc"):
            text = _normalize_text(sub.attrib.get(key, ""))
            if text and text not in seen:
                seen.add(text)
                texts.append(text)
    return texts


def _looks_like_product_card(texts: list[str]) -> bool:
    if not texts or any(text in LIST_NOISE_KEYWORDS for text in texts):
        return False
    if _pick_list_price(texts) is None:
        return False
    return any(_looks_like_title_line(text) for text in texts)


def _looks_like_title_line(text: str) -> bool:
    compact = text.replace(" ", "")
    if len(compact) < 8:
        return False
    if "|" in text:
        return False
    if text.startswith("七天无理由") or text.startswith("描述不符") or text.startswith("48小时发货"):
        return False
    if "想要" in text or "已售" in text or "已降" in text:
        return False
    if PRICE_LINE_RE.fullmatch(compact):
        return False
    return True


def _pick_list_title_hint(texts: list[str]) -> str:
    for text in texts:
        if not _looks_like_title_line(text):
            continue
        return re.sub(r"^pic", "", text, flags=re.IGNORECASE).strip()
    return ""


def _pick_list_price(texts: list[str]) -> str | None:
    for text in texts:
        compact = text.replace("¥", "").replace(",", "").strip()
        if compact and PRICE_LINE_RE.fullmatch(compact):
            return compact
    return None


def _pick_list_region(texts: list[str]) -> str | None:
    for text in texts:
        if re.fullmatch(r"[\u4e00-\u9fa5]{2,8}", text):
            if text not in {"回复超快", "综合", "价格", "区域", "筛选"}:
                return text
    return None


def _find_clickable_bounds(node: ET.Element) -> Bounds | None:
    best: Bounds | None = None
    for sub in node.iter("node"):
        if sub.attrib.get("clickable") != "true":
            continue
        bounds = parse_bounds(sub.attrib.get("bounds", ""))
        if bounds is None:
            continue
        if best is None or bounds.area > best.area:
            best = bounds
    return best


def _normalize_text(text: str) -> str:
    value = text.replace("&#10;", "\n").strip()
    for token in ("\u200b", "\ufeff", "\u2060", "\u00a0", "\u200c", "\u200d", "\ufffc"):
        value = value.replace(token, "")
    return value.strip()


def _is_system_noise(text: str) -> bool:
    if text in DETAIL_NOISE_TEXTS:
        return True
    if text.startswith("Android 系统通知："):
        return True
    if text in {"WLAN 信号满格。", "手机信号满格。", "正在充电，已完成 100%。"}:
        return True
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        return True
    if text.startswith("上午") or text.startswith("下午"):
        return True
    return False


def _looks_like_seller_block(text: str) -> bool:
    if any(token in text for token in ("人想要", "看过", "已售", "¥", "品牌 ", "型号 ", "存储容量", "买过的人的评价")):
        return False
    if ":" in text or "：" in text or "共" in text:
        return False
    if "来过" in text or "芝麻" in text or "信用" in text:
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return len(lines) >= 2 and len(lines[0]) <= 20 and len(lines[-1]) <= 12 and "发货" not in text


def _parse_seller_block(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "", ""
    seller_name = lines[0]
    seller_region = ""
    for line in reversed(lines[1:]):
        if re.search(r"[\u4e00-\u9fa5]{2,8}", line):
            seller_region = line
            break
    return seller_name, seller_region


def _parse_region_from_shipping(text: str) -> str:
    if not text:
        return ""
    matches = REGION_RE.findall(text)
    for candidate in reversed(matches):
        if candidate.endswith("小时"):
            continue
        return candidate
    return ""


def _parse_price(text: str) -> str | None:
    if not text:
        return None
    for line in text.splitlines():
        current_price_match = re.search(r"现价\s*([0-9]+(?:\.\d+)?)", line)
        if current_price_match:
            return current_price_match.group(1)
        if "¥" not in line:
            continue
        compact = re.sub(r"[^\d.]", "", line)
        if compact and PRICE_LINE_RE.fullmatch(compact):
            return compact
    for line in text.splitlines():
        if any(token in line for token in ("/", "人想要", "看过", "已售")):
            continue
        compact = re.sub(r"[^\d.]", "", line)
        if compact and len(compact) <= 8 and PRICE_LINE_RE.fullmatch(compact):
            return compact
    return None


def _pick_price_from_texts(texts: list[str]) -> str | None:
    for text in texts:
        price = _parse_price(text)
        if price:
            return price
    return None


def _parse_int_from_texts(texts: list[str], pattern: re.Pattern[str]) -> int | None:
    for text in texts:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None


def _pick_detail_title(texts: list[str], stats_block: str, seller_block: str) -> str:
    if stats_block:
        lines = [line.strip() for line in stats_block.splitlines() if line.strip()]
        for line in lines:
            if re.fullmatch(r".*\d+/\d+.*", line):
                continue
            if line.startswith("现价") or line.startswith("原价"):
                continue
            if line.startswith("¥"):
                break
            if "人想要" in line or "看过" in line or "已售" in line:
                continue
            if _is_price_only_line(line):
                continue
            if _looks_like_detail_title(line):
                return line

    for text in texts:
        if text in {stats_block, seller_block}:
            continue
        if _has_strong_product_identity(text) and _looks_like_detail_title(text):
            return text

    for text in texts:
        if text in {stats_block, seller_block}:
            continue
        if not _looks_like_detail_title(text):
            continue
        return text
    return ""


def _pick_detail_text(
    texts: list[str],
    stats_block: str,
    seller_block: str,
    shipping_block: str,
    review_block: str,
    title: str,
) -> str:
    blocks: list[str] = []
    for text in texts:
        if text in {stats_block, seller_block, review_block, title}:
            continue
        if text in DETAIL_NOISE_TEXTS:
            continue
        if "人想要" in text and "看过" in text:
            continue
        if "留言" in text or "评论" in text or "评价" in text:
            continue
        if len(text) >= 12:
            blocks.append(text)

    if shipping_block and shipping_block not in blocks:
        blocks.insert(0, shipping_block)
    if not blocks:
        return ""
    return "\n\n".join(dict.fromkeys(blocks))


def _pick_message_text(texts: list[str]) -> str:
    messages = []
    for text in texts:
        if "留言" in text or "评论" in text or "评价" in text:
            messages.append(text)
    return "\n\n".join(dict.fromkeys(messages))


def _looks_like_detail_title(text: str) -> bool:
    if any(token in text for token in ("优惠", "小刀", "按钮", "评价", "发货", "退货规则", "来过")):
        return False
    if "品牌" in text or "型号" in text or "存储容量" in text or "版本" in text:
        return False
    lower_text = text.lower()
    if any(token in lower_text for token in ("iphone", "苹果", "国行", "pro", "max")):
        return True
    if re.search(r"\d+\s*gb", lower_text):
        return True
    return _looks_like_title_line(text)


def _is_price_only_line(text: str) -> bool:
    compact = text.replace("¥", "").replace(",", "").strip()
    if not compact:
        return False
    if not re.fullmatch(r"[¥\d\s,\.]+", text):
        return False
    return bool(PRICE_LINE_RE.fullmatch(compact))


def _has_strong_product_identity(text: str) -> bool:
    lower_text = text.lower()
    return any(token in lower_text for token in ("iphone", "苹果", "国行", "pro", "max", "plus"))
