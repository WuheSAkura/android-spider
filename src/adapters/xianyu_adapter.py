from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from src.adapters.base_adapter import AdapterRunResult, BaseAdapter
from src.adapters.search_adapter_support import (
    click_optional,
    ensure_not_cancelled,
    resolve_runtime_selectors,
    sleep_seconds,
    title_matches_keyword,
)
from src.adapters.xianyu_parser import parse_detail_data, parse_search_result_candidates
from src.core.artifacts import ArtifactManager
from src.core.driver import AndroidDriver
from src.core.selectors import Selector
from src.models.collected_record import CollectedRecord
from src.models.task_models import TaskConfig
from src.storage.result_store import MySQLResultStore
from src.utils.exceptions import ConfigError, StepExecutionError


@dataclass(slots=True)
class PageSnapshot:
    hierarchy_xml: str
    visible_texts: list[str]
    page_kind: str


XIANYU_CSV_FIELDNAMES = (
    "keyword",
    "title",
    "price",
    "seller_name",
    "seller_region",
    "want_count",
    "view_count",
    "message_text",
    "detail_visible_texts",
    "detail_text",
)


class XianyuAdapter(BaseAdapter):
    """闲鱼搜索采集 MVP。"""

    name = "xianyu_search"

    def __init__(self) -> None:
        self._cancel_check = None

    def validate_config(self, task_config: TaskConfig) -> None:
        if task_config.package_name != "com.taobao.idlefish":
            raise ConfigError("xianyu_search 适配器要求 package_name 为 com.taobao.idlefish。")

        required_selectors = {
            "home_search_bar",
            "login_close",
            "search_results_list",
            "detail_back",
        }
        missing = [name for name in required_selectors if name not in task_config.selectors]
        if missing:
            raise ConfigError(f"xianyu_search 缺少必要 selectors：{', '.join(missing)}")

    def execute_task(
        self,
        *,
        driver: AndroidDriver,
        task_config: TaskConfig,
        artifacts: ArtifactManager,
        logger,
        mysql_store: MySQLResultStore,
        run_id: int | None,
        check_cancelled=None,
    ) -> AdapterRunResult:
        del mysql_store, run_id
        self._cancel_check = check_cancelled

        keyword = str(task_config.adapter_options.get("search_keyword", "iPhone15")).strip() or "iPhone15"
        max_items = int(task_config.adapter_options.get("max_items", 20))
        max_scrolls = int(task_config.adapter_options.get("max_scrolls", 20))
        max_idle_rounds = int(task_config.adapter_options.get("max_idle_rounds", 5))
        settle_seconds = max(1.0, float(task_config.adapter_options.get("settle_seconds", 1.5)))
        search_timeout = float(task_config.adapter_options.get("search_timeout", 20))
        poll_seconds = min(max(settle_seconds / 2, 0.5), 1.0)
        selectors = self._resolve_selectors(task_config)

        ready_snapshot = self._prepare_search_entry(driver, selectors, keyword, search_timeout, settle_seconds, poll_seconds, logger)
        if ready_snapshot.page_kind == "home":
            self._click_required(driver, selectors["home_search_bar"], "首页搜索栏", settle_seconds)

        search_input_snapshot = self._wait_for_page(
            driver,
            selectors,
            timeout=search_timeout,
            poll_seconds=poll_seconds,
            expected={"search_input"},
            logger=logger,
            allow_dismiss_login=True,
            settle_seconds=settle_seconds,
        )
        if search_input_snapshot is None:
            raise StepExecutionError("未能进入闲鱼搜索输入页。")

        search_input_selector = selectors.get("search_input_field")
        if search_input_selector is not None:
            self._click_optional(driver, search_input_selector, "搜索输入框", settle_seconds)
        driver.send_keys(keyword, clear=True)
        self._sleep(settle_seconds)

        if not self._trigger_search(
            driver,
            selectors=selectors,
            logger=logger,
            timeout=search_timeout,
            poll_seconds=poll_seconds,
            settle_seconds=settle_seconds,
        ):
            raise StepExecutionError("未能进入闲鱼搜索结果页，请检查搜索页结构是否变化。")

        collected_products: list[dict[str, Any]] = []
        seen_list_signatures: set[str] = set()
        seen_detail_signatures: set[str] = set()
        stagnant_rounds = 0
        scroll_count = 0

        while len(collected_products) < max_items and scroll_count <= max_scrolls:
            ensure_not_cancelled(self._cancel_check)
            results_snapshot = self._wait_for_page(
                driver,
                selectors,
                timeout=search_timeout,
                poll_seconds=poll_seconds,
                expected={"search_results"},
                logger=logger,
                allow_dismiss_login=True,
                settle_seconds=settle_seconds,
            )
            if results_snapshot is None:
                raise StepExecutionError("未能停留在闲鱼搜索结果页。")

            candidates = parse_search_result_candidates(results_snapshot.hierarchy_xml)
            new_products_this_round = 0

            for candidate in candidates:
                ensure_not_cancelled(self._cancel_check)
                if candidate.signature in seen_list_signatures:
                    continue
                if not title_matches_keyword(candidate.title_hint, keyword):
                    continue
                seen_list_signatures.add(candidate.signature)

                detail_snapshot = self._open_detail_from_candidate(
                    driver,
                    candidate=candidate,
                    selectors=selectors,
                    logger=logger,
                    timeout=min(search_timeout, 8),
                    poll_seconds=poll_seconds,
                    settle_seconds=settle_seconds,
                )
                if detail_snapshot is None:
                    logger.warning("点击列表项后未进入详情页，已尝试返回继续。标题提示：%s", candidate.title_hint)
                    if not self._return_to_results(
                        driver,
                        selectors,
                        logger=logger,
                        timeout=search_timeout,
                        poll_seconds=poll_seconds,
                        settle_seconds=settle_seconds,
                    ):
                        logger.warning("当前页面未能稳定回到搜索结果页，本条商品跳过。")
                    continue

                detail_data = parse_detail_data(detail_snapshot.visible_texts)
                detail_signature = "|".join(
                    [
                        detail_data.title,
                        detail_data.price,
                        detail_data.seller_name,
                        detail_data.seller_region,
                    ]
                )

                if detail_signature and detail_signature not in seen_detail_signatures and detail_data.title:
                    seen_detail_signatures.add(detail_signature)
                    collected_products.append(
                        {
                            "keyword": keyword,
                            "title": detail_data.title,
                            "price": detail_data.price,
                            "seller_name": detail_data.seller_name,
                            "seller_region": detail_data.seller_region,
                            "want_count": detail_data.want_count,
                            "view_count": detail_data.view_count,
                            "message_text": detail_data.message_text,
                            "detail_visible_texts": detail_data.detail_visible_texts,
                            "detail_text": detail_data.detail_text,
                        }
                    )
                    new_products_this_round += 1
                    logger.info("已采集商品 %s/%s：%s", len(collected_products), max_items, detail_data.title)

                if not self._return_to_results(
                    driver,
                    selectors,
                    logger=logger,
                    timeout=search_timeout,
                    poll_seconds=poll_seconds,
                    settle_seconds=settle_seconds,
                ):
                    raise StepExecutionError("从详情页返回后未能回到搜索结果页。")

                if len(collected_products) >= max_items:
                    break

            if len(collected_products) >= max_items:
                break

            if new_products_this_round == 0:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= max_idle_rounds:
                logger.info("连续 %s 轮没有采到新商品，提前结束采集。", max_idle_rounds)
                break

            driver.swipe_down()
            scroll_count += 1
            self._sleep(settle_seconds)

        items_path = artifacts.write_json("xianyu_items.json", collected_products)
        csv_path = artifacts.write_csv(
            task_config.storage.csv_dir,
            filename_prefix=keyword,
            fieldnames=XIANYU_CSV_FIELDNAMES,
            rows=collected_products,
        )
        final_capture = artifacts.capture_page(
            driver,
            save_screenshot=task_config.save_screenshot,
            save_hierarchy=task_config.save_hierarchy,
            save_visible_texts=task_config.save_visible_texts,
            prefix="xianyu_final",
        )

        result = {
            "task_name": task_config.task_name,
            "adapter": self.name,
            "status": "success",
            "package_name": task_config.package_name,
            "keyword": keyword,
            "item_count": len(collected_products),
            "max_items": max_items,
            "artifact_dir": str(artifacts.run_dir),
            "items_path": str(items_path),
            "csv_path": str(csv_path),
            "items": collected_products,
        }
        return AdapterRunResult(
            result=result,
            page_name="xianyu_search_results",
            visible_texts=final_capture.visible_texts or [],
            collected_records=self._build_records(keyword, collected_products),
        )

    def _build_records(self, keyword: str, products: list[dict[str, Any]]) -> list[CollectedRecord]:
        records: list[CollectedRecord] = []
        for product in products:
            records.append(
                CollectedRecord(
                    platform="xianyu",
                    record_type="listing",
                    keyword=keyword,
                    title=str(product.get("title", "")),
                    content_text=str(product.get("detail_text", "")),
                    author_name=str(product.get("seller_name", "")),
                    author_id=str(product.get("seller_name", "")),
                    location_text=str(product.get("seller_region", "")),
                    metrics={
                        "price": str(product.get("price", "")),
                        "want_count": product.get("want_count"),
                        "view_count": product.get("view_count"),
                    },
                    extra={
                        "message_text": str(product.get("message_text", "")),
                    },
                    raw_visible_texts=list(product.get("detail_visible_texts", []) or []),
                )
            )
        return records

    def _resolve_selectors(self, task_config: TaskConfig) -> dict[str, Selector]:
        return resolve_runtime_selectors(task_config)

    def _prepare_search_entry(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        keyword: str,
        timeout: float,
        settle_seconds: float,
        poll_seconds: float,
        logger,
    ) -> PageSnapshot:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ensure_not_cancelled(self._cancel_check)
            snapshot = self._capture_snapshot(driver, selectors)
            if snapshot.page_kind == "login_modal":
                self._dismiss_login_modal(driver, selectors, logger, settle_seconds)
                continue
            if self._is_search_entry_page(snapshot.page_kind):
                return snapshot
            if snapshot.page_kind == "search_results":
                logger.info("检测到已停留在搜索结果页，先尝试返回到可重新搜索的入口页。")
                entry_snapshot = self._return_from_results_to_search_entry(driver, selectors, logger, settle_seconds)
                if entry_snapshot is None:
                    raise StepExecutionError(f"无法从已有结果页返回到搜索入口页，无法重新搜索关键词：{keyword}")
                if entry_snapshot.page_kind == "home":
                    logger.info("结果页返回后已回到首页，将从首页重新进入搜索输入页。")
                else:
                    logger.info("结果页返回后已回到搜索输入页。")
                return entry_snapshot
            if snapshot.page_kind == "detail":
                logger.info("检测到应用仍停留在详情页，先尝试返回。")
                if not self._return_to_results(
                    driver,
                    selectors,
                    logger=logger,
                    timeout=timeout,
                    poll_seconds=poll_seconds,
                    settle_seconds=settle_seconds,
                ):
                    self._click_detail_back_or_system_back(driver, selectors, settle_seconds)
                continue
            self._sleep(poll_seconds)
        raise StepExecutionError("闲鱼启动后未进入可识别页面。")

    def _trigger_search(
        self,
        driver: AndroidDriver,
        *,
        selectors: dict[str, Selector],
        logger,
        timeout: float,
        poll_seconds: float,
        settle_seconds: float,
    ) -> bool:
        driver.press_key("enter")
        self._sleep(settle_seconds)
        return (
            self._wait_for_page(
                driver,
                selectors,
                timeout=timeout,
                poll_seconds=poll_seconds,
                expected={"search_results"},
                logger=logger,
                allow_dismiss_login=True,
                settle_seconds=settle_seconds,
            )
            is not None
        )

    def _open_detail_from_candidate(
        self,
        driver: AndroidDriver,
        *,
        candidate,
        selectors: dict[str, Selector],
        logger,
        timeout: float,
        poll_seconds: float,
        settle_seconds: float,
    ) -> PageSnapshot | None:
        tap_points = [candidate.tap_point(), candidate.bounds.center()]
        for x, y in tap_points:
            ensure_not_cancelled(self._cancel_check)
            if y >= 1720:
                y = max(220, y - 180)
            driver.click_point(x, y)
            self._sleep(settle_seconds)
            snapshot = self._wait_for_page(
                driver,
                selectors,
                timeout=timeout,
                poll_seconds=poll_seconds,
                expected={"detail"},
                logger=logger,
                allow_dismiss_login=True,
                settle_seconds=settle_seconds,
            )
            if snapshot is not None:
                return snapshot
        return None

    def _return_to_results(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        *,
        logger,
        timeout: float,
        poll_seconds: float,
        settle_seconds: float,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ensure_not_cancelled(self._cancel_check)
            snapshot = self._capture_snapshot(driver, selectors)
            if snapshot.page_kind == "search_results":
                return True
            if snapshot.page_kind == "login_modal":
                self._dismiss_login_modal(driver, selectors, logger, settle_seconds)
                continue
            if snapshot.page_kind == "detail":
                self._click_detail_back_or_system_back(driver, selectors, settle_seconds)
                continue
            if snapshot.page_kind == "search_input":
                if self._click_optional(driver, selectors.get("search_input_back"), "搜索输入页返回按钮", settle_seconds):
                    continue
                driver.back()
                self._sleep(settle_seconds)
                continue
            if snapshot.page_kind == "home":
                return False
            driver.back()
            self._sleep(settle_seconds)
            self._sleep(poll_seconds)
        return False

    def _return_from_results_to_search_entry(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        logger,
        settle_seconds: float,
    ) -> PageSnapshot | None:
        if self._click_optional(driver, selectors.get("results_back"), "结果页返回按钮", settle_seconds):
            snapshot = self._capture_snapshot_after_navigation(driver, selectors, logger, settle_seconds)
            if self._is_search_entry_page(snapshot.page_kind):
                return snapshot
        driver.back()
        self._sleep(settle_seconds)
        snapshot = self._capture_snapshot_after_navigation(driver, selectors, logger, settle_seconds)
        if self._is_search_entry_page(snapshot.page_kind):
            return snapshot
        return None

    def _wait_for_page(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        *,
        timeout: float,
        poll_seconds: float,
        expected: set[str],
        logger,
        allow_dismiss_login: bool,
        settle_seconds: float,
    ) -> PageSnapshot | None:
        deadline = time.time() + timeout
        last_snapshot: PageSnapshot | None = None
        while time.time() < deadline:
            ensure_not_cancelled(self._cancel_check)
            snapshot = self._capture_snapshot(driver, selectors)
            last_snapshot = snapshot
            if snapshot.page_kind in expected:
                return snapshot
            if allow_dismiss_login and snapshot.page_kind == "login_modal":
                self._dismiss_login_modal(driver, selectors, logger, settle_seconds)
                continue
            self._sleep(poll_seconds)
        expected_pages = ", ".join(sorted(expected))
        if last_snapshot is None:
            logger.warning("等待页面超时，目标页面：%s；未获取到任何页面快照。", expected_pages)
        else:
            logger.warning(
                "等待页面超时，目标页面：%s；最后识别页面：%s；关键文本：%s",
                expected_pages,
                last_snapshot.page_kind,
                self._summarize_visible_texts(last_snapshot.visible_texts),
            )
        return None

    def _capture_snapshot(self, driver: AndroidDriver, selectors: dict[str, Selector]) -> PageSnapshot:
        hierarchy_xml = driver.get_hierarchy_xml()
        visible_texts = [_normalize_ui_text(text) for text in driver.get_visible_texts(hierarchy_xml)]
        visible_texts = [text for text in visible_texts if text]
        page_kind = self._classify_page(hierarchy_xml, visible_texts, selectors)
        return PageSnapshot(hierarchy_xml=hierarchy_xml, visible_texts=visible_texts, page_kind=page_kind)

    def _capture_snapshot_after_navigation(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        logger,
        settle_seconds: float,
    ) -> PageSnapshot:
        snapshot = self._capture_snapshot(driver, selectors)
        if snapshot.page_kind != "login_modal":
            return snapshot

        self._dismiss_login_modal(driver, selectors, logger, settle_seconds)
        return self._capture_snapshot(driver, selectors)

    def _classify_page(self, hierarchy_xml: str, visible_texts: list[str], selectors: dict[str, Selector]) -> str:
        joined_text = "\n".join(visible_texts)
        if self._is_login_modal(hierarchy_xml, joined_text):
            return "login_modal"
        if self._is_detail_page(visible_texts, joined_text):
            return "detail"
        if self._is_search_results_page(hierarchy_xml, visible_texts, selectors):
            return "search_results"
        if self._is_search_input_page(hierarchy_xml, visible_texts, selectors):
            return "search_input"
        if self._is_home_page(hierarchy_xml, visible_texts, selectors):
            return "home"
        return "unknown"

    def _is_login_modal(self, hierarchy_xml: str, joined_text: str) -> bool:
        return "com.taobao.idlefish:id/login_root_view" in hierarchy_xml or "欢迎使用快捷登录" in joined_text

    def _is_detail_page(self, visible_texts: list[str], joined_text: str) -> bool:
        return (
            "人想要" in joined_text
            and self._visible_texts_contain_any_fragment(visible_texts, ("看过", "浏览", "已售"))
            and self._visible_texts_contain_any_fragment(visible_texts, ("返回",))
            and self._visible_texts_contain_any_fragment(visible_texts, ("收藏", "按钮", "我想要按钮"))
        )

    def _is_search_results_page(
        self,
        hierarchy_xml: str,
        visible_texts: list[str],
        selectors: dict[str, Selector],
    ) -> bool:
        return self._snapshot_matches_selector(selectors.get("search_results_list"), hierarchy_xml, visible_texts) and (
            self._visible_texts_contain_any_fragment(visible_texts, ("综合", "价格", "筛选", "个人闲置", "全部"))
        )

    def _is_search_input_page(
        self,
        hierarchy_xml: str,
        visible_texts: list[str],
        selectors: dict[str, Selector],
    ) -> bool:
        legacy_search_input = "android.widget.EditText" in hierarchy_xml and self._visible_texts_contain_any_fragment(
            visible_texts, ("搜索",)
        )
        if legacy_search_input:
            return True

        has_back_button = self._snapshot_matches_selector(selectors.get("search_input_back"), hierarchy_xml, visible_texts)
        has_search_suggestions = self._visible_texts_contain_any_fragment(
            visible_texts,
            (
                "猜你可能在找",
                "历史搜索",
                "更精准",
            ),
        )
        return has_back_button and has_search_suggestions

    def _is_home_page(
        self,
        hierarchy_xml: str,
        visible_texts: list[str],
        selectors: dict[str, Selector],
    ) -> bool:
        return self._snapshot_matches_selector(selectors.get("home_search_bar"), hierarchy_xml, visible_texts)

    def _is_search_entry_page(self, page_kind: str) -> bool:
        return page_kind in {"home", "search_input"}

    def _snapshot_matches_selector(
        self,
        selector: Selector | None,
        hierarchy_xml: str,
        visible_texts: list[str],
    ) -> bool:
        if selector is None:
            return False

        for strategy, value in selector.strategies():
            if strategy == "resource_id" and value in hierarchy_xml:
                return True
            if strategy in {"text", "description"} and self._visible_texts_contain_any_fragment(
                visible_texts,
                tuple(self._split_selector_terms(value)),
            ):
                return True
            if strategy == "xpath" and self._xpath_snapshot_matches(hierarchy_xml, value):
                return True
        return False

    def _xpath_snapshot_matches(self, hierarchy_xml: str, xpath: str) -> bool:
        normalized_xpath = xpath.strip()
        if not normalized_xpath.startswith("//"):
            return False
        node_name = normalized_xpath[2:]
        if not node_name or any(token in node_name for token in ("[", "@", "*", "(", ")", "|")):
            return False
        return node_name in hierarchy_xml

    def _split_selector_terms(self, raw_value: str) -> list[str]:
        terms: list[str] = []
        for item in re.split(r"[,，]", raw_value):
            term = item.strip()
            if term and term not in terms:
                terms.append(term)
        if raw_value.strip() and raw_value.strip() not in terms:
            terms.insert(0, raw_value.strip())
        return terms

    def _visible_texts_contain_any_fragment(self, visible_texts: list[str], fragments: tuple[str, ...]) -> bool:
        for fragment in fragments:
            normalized_fragment = _normalize_ui_text(fragment)
            if not normalized_fragment:
                continue
            for text in visible_texts:
                if normalized_fragment in text:
                    return True
        return False

    def _summarize_visible_texts(self, visible_texts: list[str], limit: int = 6) -> str:
        if not visible_texts:
            return "无可见文本"

        summary_items: list[str] = []
        for text in visible_texts[:limit]:
            compact = text.replace("\n", " / ")
            if len(compact) > 36:
                compact = f"{compact[:33]}..."
            summary_items.append(compact)
        return " | ".join(summary_items)

    def _dismiss_login_modal(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        logger,
        settle_seconds: float,
    ) -> None:
        if self._click_optional(driver, selectors.get("login_close"), "快捷登录关闭按钮", settle_seconds):
            logger.info("已关闭闲鱼登录弹窗。")
            return
        driver.back()
        logger.info("未找到登录弹窗关闭按钮，已回退关闭。")
        self._sleep(settle_seconds)

    def _click_required(self, driver: AndroidDriver, selector: Selector, label: str, settle_seconds: float) -> None:
        del label
        ensure_not_cancelled(self._cancel_check)
        driver.click(selector, timeout=5)
        self._sleep(settle_seconds)

    def _click_optional(
        self,
        driver: AndroidDriver,
        selector: Selector | None,
        label: str,
        settle_seconds: float,
    ) -> bool:
        del label
        return click_optional(
            driver,
            selector,
            settle_seconds=settle_seconds,
            check_cancelled=self._cancel_check,
        )

    def _click_detail_back_or_system_back(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        settle_seconds: float,
    ) -> None:
        if self._click_optional(driver, selectors.get("detail_back"), "详情页返回按钮", settle_seconds):
            return
        driver.back()
        self._sleep(settle_seconds)

    def _sleep(self, seconds: float) -> None:
        sleep_seconds(seconds, check_cancelled=self._cancel_check)


def _normalize_ui_text(text: str) -> str:
    value = text.strip()
    for token in ("\u200b", "\ufeff", "\u2060", "\u00a0", "\u200c", "\u200d", "\ufffc"):
        value = value.replace(token, "")
    return value.strip()
