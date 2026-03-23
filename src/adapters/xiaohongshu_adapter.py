from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from src.adapters.base_adapter import AdapterPartialResult, AdapterRunResult, BaseAdapter
from src.adapters.search_adapter_support import (
    click_optional,
    ensure_not_cancelled,
    resolve_runtime_selectors,
    sleep_seconds,
    title_matches_keyword,
)
from src.adapters.xiaohongshu_parser import (
    XiaohongshuComment,
    XiaohongshuNoteDetail,
    XiaohongshuSearchCandidate,
    find_action_button_bounds,
    has_comment_recycler,
    parse_comment_entries,
    parse_image_detail_snapshot,
    parse_search_result_candidates,
    parse_total_comment_count,
    parse_video_comment_panel_snapshot,
    parse_video_detail_snapshot,
)
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


@dataclass(slots=True)
class XiaohongshuRunState:
    keyword: str = ""
    note_items: list[dict[str, Any]] = field(default_factory=list)
    comment_items: list[dict[str, Any]] = field(default_factory=list)
    collected_records: list[CollectedRecord] = field(default_factory=list)


XIAOHONGSHU_NOTE_CSV_FIELDNAMES = (
    "keyword",
    "note_type",
    "title",
    "content_text",
    "author_name",
    "author_id",
    "location_text",
    "ip_location",
    "published_text",
    "like_count",
    "favorite_count",
    "comment_count",
    "comments_captured",
    "topics",
)

XIAOHONGSHU_COMMENT_CSV_FIELDNAMES = (
    "keyword",
    "parent_title",
    "parent_author_name",
    "parent_note_type",
    "author_name",
    "content_text",
    "published_text",
    "ip_location",
    "like_count",
    "is_author",
)


class XiaohongshuAdapter(BaseAdapter):
    """小红书搜索与帖子采集。"""

    name = "xiaohongshu_search"

    def __init__(self) -> None:
        self._run_state = XiaohongshuRunState()
        self._cancel_check = None

    def validate_config(self, task_config: TaskConfig) -> None:
        if task_config.package_name != "com.xingin.xhs":
            raise ConfigError("xiaohongshu_search 适配器要求 package_name 为 com.xingin.xhs。")

        required_selectors = {
            "home_search_entry",
            "search_input_field",
            "search_submit",
            "back_button",
        }
        missing = [name for name in required_selectors if name not in task_config.selectors]
        if missing:
            raise ConfigError(f"xiaohongshu_search 缺少必要 selectors：{', '.join(missing)}")

    def export_partial_result(
        self,
        *,
        task_config: TaskConfig,
        artifacts: ArtifactManager,
        logger,
    ) -> AdapterPartialResult | None:
        if not self._run_state.note_items and not self._run_state.comment_items:
            return None

        output_paths = self._write_output_files(
            task_config=task_config,
            artifacts=artifacts,
            partial=True,
        )
        logger.info(
            "已导出中途中断的部分结果：帖子 %s 条，评论 %s 条。",
            len(self._run_state.note_items),
            len(self._run_state.comment_items),
        )
        return AdapterPartialResult(
            result={
                "partial_keyword": self._run_state.keyword,
                "partial_item_count": len(self._run_state.note_items),
                "partial_comment_count": len(self._run_state.comment_items),
                "partial_notes_path": str(output_paths["notes_path"]),
                "partial_comments_path": str(output_paths["comments_path"]),
                "partial_notes_csv_path": str(output_paths["notes_csv_path"]),
                "partial_comments_csv_path": str(output_paths["comments_csv_path"]),
            },
            collected_records=list(self._run_state.collected_records),
        )

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

        keyword = str(task_config.adapter_options.get("search_keyword", "穿搭")).strip() or "穿搭"
        self._run_state = XiaohongshuRunState(keyword=keyword)
        max_items = int(task_config.adapter_options.get("max_items", 20))
        max_scrolls = int(task_config.adapter_options.get("max_scrolls", 20))
        max_idle_rounds = int(task_config.adapter_options.get("max_idle_rounds", 5))
        max_comments_per_note = int(task_config.adapter_options.get("max_comments_per_note", 20))
        detail_scroll_limit = int(task_config.adapter_options.get("detail_scroll_limit", 8))
        comment_scroll_limit = int(task_config.adapter_options.get("comment_scroll_limit", 10))
        settle_seconds = max(0.4, float(task_config.adapter_options.get("settle_seconds", 0.75)))
        search_timeout = float(task_config.adapter_options.get("search_timeout", 20))
        poll_seconds = min(max(settle_seconds / 2, 0.25), 0.6)
        selectors = self._resolve_selectors(task_config)

        ready_snapshot = self._prepare_search_entry(driver, selectors, search_timeout, settle_seconds, poll_seconds, logger)
        if ready_snapshot.page_kind == "home":
            self._click_required(driver, selectors["home_search_entry"], "首页搜索入口", settle_seconds)

        search_input_snapshot = self._wait_for_page(
            driver,
            selectors,
            timeout=search_timeout,
            poll_seconds=poll_seconds,
            expected={"search_input"},
            logger=logger,
        )
        if search_input_snapshot is None:
            raise StepExecutionError("未能进入小红书搜索输入页。")

        self._click_optional(driver, selectors.get("search_input_field"), settle_seconds)
        driver.send_keys(keyword, clear=True)
        self._sleep(settle_seconds)
        self._trigger_search(driver, selectors, settle_seconds)

        results_snapshot = self._wait_for_page(
            driver,
            selectors,
            timeout=search_timeout,
            poll_seconds=poll_seconds,
            expected={"search_results"},
            logger=logger,
        )
        if results_snapshot is None:
            raise StepExecutionError("未能进入小红书搜索结果页。")

        collected_note_items = self._run_state.note_items
        collected_comment_items = self._run_state.comment_items
        collected_records = self._run_state.collected_records
        seen_list_signatures: set[str] = set()
        seen_note_signatures: set[str] = set()
        stagnant_rounds = 0
        scroll_count = 0

        while len(collected_note_items) < max_items and scroll_count <= max_scrolls:
            ensure_not_cancelled(self._cancel_check)
            results_snapshot = self._wait_for_page(
                driver,
                selectors,
                timeout=search_timeout,
                poll_seconds=poll_seconds,
                expected={"search_results"},
                logger=logger,
            )
            if results_snapshot is None:
                raise StepExecutionError("未能稳定停留在小红书搜索结果页。")

            candidates = parse_search_result_candidates(results_snapshot.hierarchy_xml)
            new_notes_this_round = 0

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
                    timeout=min(search_timeout, 10),
                    poll_seconds=poll_seconds,
                    settle_seconds=settle_seconds,
                )
                if detail_snapshot is None:
                    logger.warning("点击结果卡片后未进入详情页，标题提示：%s", candidate.title_hint)
                    self._return_to_results(
                        driver,
                        selectors,
                        logger=logger,
                        timeout=search_timeout,
                        poll_seconds=poll_seconds,
                        settle_seconds=settle_seconds,
                    )
                    continue

                if detail_snapshot.page_kind == "image_detail":
                    note_item, comment_items, note_records, comment_records = self._collect_image_note(
                        driver=driver,
                        detail_snapshot=detail_snapshot,
                        keyword=keyword,
                        fallback_title=candidate.title_hint,
                        max_comments_per_note=max_comments_per_note,
                        max_scrolls=detail_scroll_limit,
                        selectors=selectors,
                        settle_seconds=settle_seconds,
                        logger=logger,
                    )
                elif detail_snapshot.page_kind == "video_detail":
                    note_item, comment_items, note_records, comment_records = self._collect_video_note(
                        driver=driver,
                        detail_snapshot=detail_snapshot,
                        keyword=keyword,
                        fallback_title=candidate.title_hint,
                        max_comments_per_note=max_comments_per_note,
                        max_scrolls=comment_scroll_limit,
                        selectors=selectors,
                        search_timeout=search_timeout,
                        poll_seconds=poll_seconds,
                        settle_seconds=settle_seconds,
                        logger=logger,
                    )
                else:
                    logger.warning("进入了未识别页面，页面类型：%s", detail_snapshot.page_kind)
                    self._return_to_results(
                        driver,
                        selectors,
                        logger=logger,
                        timeout=search_timeout,
                        poll_seconds=poll_seconds,
                        settle_seconds=settle_seconds,
                    )
                    continue

                note_signature = "|".join(
                    [
                        str(note_item.get("note_type", "")),
                        str(note_item.get("author_name", "")),
                        str(note_item.get("title", "")),
                    ]
                )
                if note_signature and note_signature not in seen_note_signatures:
                    seen_note_signatures.add(note_signature)
                    collected_note_items.append(note_item)
                    collected_comment_items.extend(comment_items)
                    collected_records.extend(note_records)
                    collected_records.extend(comment_records)
                    new_notes_this_round += 1
                    logger.info("已采集帖子 %s/%s：%s", len(collected_note_items), max_items, note_item.get("title", ""))

                if not self._return_to_results(
                    driver,
                    selectors,
                    logger=logger,
                    timeout=search_timeout,
                    poll_seconds=poll_seconds,
                    settle_seconds=settle_seconds,
                ):
                    raise StepExecutionError("从详情页返回后未能回到小红书搜索结果页。")

                if len(collected_note_items) >= max_items:
                    break

            if len(collected_note_items) >= max_items:
                break

            if new_notes_this_round == 0:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= max_idle_rounds:
                logger.info("连续 %s 轮没有采到新帖子，提前结束。", max_idle_rounds)
                break

            driver.swipe_down()
            scroll_count += 1
            self._sleep(settle_seconds)

        output_paths = self._write_output_files(
            task_config=task_config,
            artifacts=artifacts,
            partial=False,
        )
        final_capture = artifacts.capture_page(
            driver,
            save_screenshot=task_config.save_screenshot,
            save_hierarchy=task_config.save_hierarchy,
            save_visible_texts=task_config.save_visible_texts,
            prefix="xiaohongshu_final",
        )

        result = {
            "task_name": task_config.task_name,
            "adapter": self.name,
            "status": "success",
            "package_name": task_config.package_name,
            "keyword": keyword,
            "item_count": len(collected_note_items),
            "comment_count": len(collected_comment_items),
            "max_items": max_items,
            "max_comments_per_note": max_comments_per_note,
            "artifact_dir": str(artifacts.run_dir),
            "notes_path": str(output_paths["notes_path"]),
            "comments_path": str(output_paths["comments_path"]),
            "notes_csv_path": str(output_paths["notes_csv_path"]),
            "comments_csv_path": str(output_paths["comments_csv_path"]),
            "items": collected_note_items,
        }
        return AdapterRunResult(
            result=result,
            page_name="xiaohongshu_search_results",
            visible_texts=final_capture.visible_texts or [],
            collected_records=collected_records,
        )

    def _collect_image_note(
        self,
        *,
        driver: AndroidDriver,
        detail_snapshot: PageSnapshot,
        keyword: str,
        fallback_title: str,
        max_comments_per_note: int,
        max_scrolls: int,
        selectors: dict[str, Selector],
        settle_seconds: float,
        logger,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[CollectedRecord], list[CollectedRecord]]:
        detail = parse_image_detail_snapshot(detail_snapshot.hierarchy_xml, detail_snapshot.visible_texts)
        raw_visible_texts = list(detail_snapshot.visible_texts)
        comments: list[XiaohongshuComment] = []
        seen_comment_signatures: set[str] = set()
        stagnant_rounds = 0
        snapshot = detail_snapshot
        seek_scroll_rounds = 0
        comment_scroll_rounds = 0
        comment_section_seen = False

        while True:
            ensure_not_cancelled(self._cancel_check)
            detail.merge(parse_image_detail_snapshot(snapshot.hierarchy_xml, snapshot.visible_texts))
            total_comment_count = parse_total_comment_count(snapshot.visible_texts)
            if total_comment_count is not None and detail.comment_total_count is None:
                detail.comment_total_count = total_comment_count

            new_comments = 0
            parsed_comments = parse_comment_entries(snapshot.hierarchy_xml)
            if total_comment_count is not None or parsed_comments:
                comment_section_seen = True

            for comment in parsed_comments:
                if comment.signature in seen_comment_signatures:
                    continue
                seen_comment_signatures.add(comment.signature)
                comments.append(comment)
                new_comments += 1
                if len(comments) >= max_comments_per_note:
                    break

            raw_visible_texts = _merge_texts(raw_visible_texts, snapshot.visible_texts)
            if len(comments) >= max_comments_per_note:
                break

            if comment_section_seen:
                if new_comments == 0:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0
                if stagnant_rounds >= 2 or comment_scroll_rounds >= max_scrolls:
                    break
            else:
                if seek_scroll_rounds >= max_scrolls:
                    break

            driver.swipe_down()
            self._sleep(settle_seconds)
            snapshot = self._capture_snapshot(driver, selectors)
            if snapshot.page_kind != "image_detail":
                logger.info("图文详情页继续下滑后已离开详情主内容区域，停止评论采集。")
                break
            if comment_section_seen:
                comment_scroll_rounds += 1
            else:
                seek_scroll_rounds += 1

        self._apply_title_hint(detail, fallback_title)
        detail.finalize_text_fields()

        note_item = self._build_note_item(keyword, detail, comments[:max_comments_per_note])
        comment_items = [
            self._build_comment_item(keyword, note_item, comment)
            for comment in comments[:max_comments_per_note]
        ]
        note_record = self._build_note_record(keyword, detail, raw_visible_texts, len(comment_items))
        comment_records = [
            self._build_comment_record(keyword, detail, comment, str(note_item.get("title", "")))
            for comment in comments[:max_comments_per_note]
        ]
        return note_item, comment_items, [note_record], comment_records

    def _collect_video_note(
        self,
        *,
        driver: AndroidDriver,
        detail_snapshot: PageSnapshot,
        keyword: str,
        fallback_title: str,
        max_comments_per_note: int,
        max_scrolls: int,
        selectors: dict[str, Selector],
        search_timeout: float,
        poll_seconds: float,
        settle_seconds: float,
        logger,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[CollectedRecord], list[CollectedRecord]]:
        detail = parse_video_detail_snapshot(detail_snapshot.hierarchy_xml, detail_snapshot.visible_texts)
        raw_visible_texts = list(detail_snapshot.visible_texts)
        comments: list[XiaohongshuComment] = []
        seen_comment_signatures: set[str] = set()

        panel_snapshot: PageSnapshot | None = None
        comment_button_bounds = find_action_button_bounds(detail_snapshot.hierarchy_xml, "评论")
        if comment_button_bounds is not None:
            x, y = comment_button_bounds.center()
            driver.click_point(x, y)
            self._sleep(settle_seconds)
            panel_snapshot = self._wait_for_page(
                driver,
                selectors,
                timeout=search_timeout,
                poll_seconds=poll_seconds,
                expected={"video_comment_panel"},
                logger=logger,
            )
            if panel_snapshot is None:
                fallback_snapshot = self._capture_snapshot(driver, selectors)
                if self._is_video_comment_panel(fallback_snapshot.hierarchy_xml, fallback_snapshot.visible_texts):
                    panel_snapshot = fallback_snapshot
        else:
            logger.warning("未找到视频评论按钮，将只采集视频详情页可见字段。")

        if panel_snapshot is not None:
            detail.merge(parse_video_comment_panel_snapshot(panel_snapshot.hierarchy_xml, panel_snapshot.visible_texts))
            raw_visible_texts = _merge_texts(raw_visible_texts, panel_snapshot.visible_texts)
            stagnant_rounds = 0
            snapshot = panel_snapshot

            for _ in range(max_scrolls):
                ensure_not_cancelled(self._cancel_check)
                detail.merge(parse_video_comment_panel_snapshot(snapshot.hierarchy_xml, snapshot.visible_texts))
                total_comment_count = parse_total_comment_count(snapshot.visible_texts)
                if total_comment_count is not None and detail.comment_total_count is None:
                    detail.comment_total_count = total_comment_count

                new_comments = 0
                for comment in parse_comment_entries(snapshot.hierarchy_xml):
                    if comment.signature in seen_comment_signatures:
                        continue
                    seen_comment_signatures.add(comment.signature)
                    comments.append(comment)
                    new_comments += 1
                    if len(comments) >= max_comments_per_note:
                        break

                raw_visible_texts = _merge_texts(raw_visible_texts, snapshot.visible_texts)
                if len(comments) >= max_comments_per_note:
                    break

                if new_comments == 0:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0
                if stagnant_rounds >= 2:
                    break

                driver.swipe_down()
                self._sleep(settle_seconds)
                snapshot = self._capture_snapshot(driver, selectors)
                if snapshot.page_kind != "video_comment_panel":
                    logger.info("视频评论浮层已关闭或切换页面，停止评论采集。")
                    break
        self._apply_title_hint(detail, fallback_title)
        detail.finalize_text_fields()

        note_item = self._build_note_item(keyword, detail, comments[:max_comments_per_note])
        comment_items = [
            self._build_comment_item(keyword, note_item, comment)
            for comment in comments[:max_comments_per_note]
        ]
        note_record = self._build_note_record(keyword, detail, raw_visible_texts, len(comment_items))
        comment_records = [
            self._build_comment_record(keyword, detail, comment, str(note_item.get("title", "")))
            for comment in comments[:max_comments_per_note]
        ]
        return note_item, comment_items, [note_record], comment_records

    def _build_note_item(
        self,
        keyword: str,
        detail: XiaohongshuNoteDetail,
        comments: list[XiaohongshuComment],
    ) -> dict[str, Any]:
        return {
            "keyword": keyword,
            "note_type": detail.note_type,
            "title": detail.title,
            "content_text": detail.content_text,
            "author_name": detail.author_name,
            "author_id": detail.author_id or detail.author_name,
            "location_text": detail.location_text,
            "location_query": detail.location_query,
            "ip_location": detail.ip_location,
            "published_text": detail.published_text,
            "like_count": detail.like_count,
            "like_count_text": detail.like_count_text,
            "favorite_count": detail.favorite_count,
            "favorite_count_text": detail.favorite_count_text,
            "comment_count": detail.comment_count,
            "comment_count_text": detail.comment_count_text,
            "comment_total_count": detail.comment_total_count,
            "comments_captured": len(comments),
            "topics": detail.topics,
            "note_notice": detail.note_notice,
            "comments": [comment.to_dict() for comment in comments],
        }

    def _build_comment_item(
        self,
        keyword: str,
        note_item: dict[str, Any],
        comment: XiaohongshuComment,
    ) -> dict[str, Any]:
        return {
            "keyword": keyword,
            "parent_title": str(note_item.get("title", "")),
            "parent_author_name": str(note_item.get("author_name", "")),
            "parent_note_type": str(note_item.get("note_type", "")),
            "author_name": comment.author_name,
            "content_text": comment.content_text,
            "published_text": comment.published_text,
            "ip_location": comment.ip_location,
            "like_count": comment.like_count,
            "is_author": comment.is_author,
        }

    def _build_note_record(
        self,
        keyword: str,
        detail: XiaohongshuNoteDetail,
        raw_visible_texts: list[str],
        comment_count_captured: int,
    ) -> CollectedRecord:
        return CollectedRecord(
            platform="xiaohongshu",
            record_type="note",
            keyword=keyword,
            title=detail.title,
            content_text=detail.content_text,
            author_name=detail.author_name,
            author_id=detail.author_id or detail.author_name,
            location_text=detail.location_text,
            ip_location=detail.ip_location,
            published_text=detail.published_text,
            metrics={
                "like_count": detail.like_count,
                "favorite_count": detail.favorite_count,
                "comment_count": detail.comment_count,
                "comment_total_count": detail.comment_total_count,
                "comments_captured": comment_count_captured,
            },
            extra={
                "note_type": detail.note_type,
                "location_query": detail.location_query,
                "topics": detail.topics,
                "note_notice": detail.note_notice,
                "like_count_text": detail.like_count_text,
                "favorite_count_text": detail.favorite_count_text,
                "comment_count_text": detail.comment_count_text,
            },
            raw_visible_texts=raw_visible_texts,
        )

    def _build_comment_record(
        self,
        keyword: str,
        detail: XiaohongshuNoteDetail,
        comment: XiaohongshuComment,
        parent_title: str,
    ) -> CollectedRecord:
        return CollectedRecord(
            platform="xiaohongshu",
            record_type="comment",
            keyword=keyword,
            title=parent_title,
            content_text=comment.content_text,
            author_name=comment.author_name,
            author_id=comment.author_name,
            ip_location=comment.ip_location,
            published_text=comment.published_text,
            metrics={"like_count": comment.like_count},
            extra={
                "parent_note_type": detail.note_type,
                "parent_author_name": detail.author_name,
                "is_author": comment.is_author,
                "like_count_text": comment.like_count_text,
            },
        )

    def _write_output_files(
        self,
        *,
        task_config: TaskConfig,
        artifacts: ArtifactManager,
        partial: bool,
    ) -> dict[str, Any]:
        keyword = self._run_state.keyword or str(task_config.adapter_options.get("search_keyword", "xiaohongshu")).strip()
        suffix = "_partial" if partial else ""
        notes_path = artifacts.write_json(f"xiaohongshu_notes{suffix}.json", self._run_state.note_items)
        comments_path = artifacts.write_json(f"xiaohongshu_comments{suffix}.json", self._run_state.comment_items)
        notes_csv_path = artifacts.write_csv(
            task_config.storage.csv_dir,
            filename_prefix=f"{keyword}_xiaohongshu_notes{suffix}",
            fieldnames=XIAOHONGSHU_NOTE_CSV_FIELDNAMES,
            rows=self._run_state.note_items,
        )
        comments_csv_path = artifacts.write_csv(
            task_config.storage.csv_dir,
            filename_prefix=f"{keyword}_xiaohongshu_comments{suffix}",
            fieldnames=XIAOHONGSHU_COMMENT_CSV_FIELDNAMES,
            rows=self._run_state.comment_items,
        )
        return {
            "notes_path": notes_path,
            "comments_path": comments_path,
            "notes_csv_path": notes_csv_path,
            "comments_csv_path": comments_csv_path,
        }

    def _apply_title_hint(self, detail: XiaohongshuNoteDetail, title_hint: str) -> None:
        normalized_hint = title_hint.strip()
        if not normalized_hint:
            return
        if not detail.title:
            detail.title = normalized_hint
            detail.title_source_score = 1
            return
        if detail.title_source_score > 1:
            return
        if _title_hint_should_override(normalized_hint, detail.title):
            detail.title = normalized_hint
            detail.title_source_score = 1

    def _resolve_selectors(self, task_config: TaskConfig) -> dict[str, Selector]:
        return resolve_runtime_selectors(task_config)

    def _prepare_search_entry(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        timeout: float,
        settle_seconds: float,
        poll_seconds: float,
        logger,
    ) -> PageSnapshot:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ensure_not_cancelled(self._cancel_check)
            snapshot = self._capture_snapshot(driver, selectors)
            if snapshot.page_kind in {"home", "search_input"}:
                return snapshot
            if snapshot.page_kind in {"search_results", "image_detail", "video_detail", "video_comment_panel"}:
                if not self._click_optional(driver, selectors.get("back_button"), settle_seconds):
                    driver.back()
                    self._sleep(settle_seconds)
                self._sleep(poll_seconds)
                continue
            self._sleep(poll_seconds)
        raise StepExecutionError("小红书启动后未进入可识别页面。")

    def _trigger_search(self, driver: AndroidDriver, selectors: dict[str, Selector], settle_seconds: float) -> None:
        if not self._click_optional(driver, selectors.get("search_submit"), settle_seconds):
            driver.press_key("enter")
            self._sleep(settle_seconds)

    def _open_detail_from_candidate(
        self,
        driver: AndroidDriver,
        *,
        candidate: XiaohongshuSearchCandidate,
        selectors: dict[str, Selector],
        logger,
        timeout: float,
        poll_seconds: float,
        settle_seconds: float,
    ) -> PageSnapshot | None:
        ensure_not_cancelled(self._cancel_check)
        x, y = candidate.tap_point()
        driver.click_point(x, y)
        self._sleep(settle_seconds)
        return self._wait_for_page(
            driver,
            selectors,
            timeout=timeout,
            poll_seconds=poll_seconds,
            expected={"image_detail", "video_detail"},
            logger=logger,
        )

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
            if snapshot.page_kind in {"image_detail", "video_detail", "video_comment_panel", "search_input"}:
                if not self._click_optional(driver, selectors.get("back_button"), settle_seconds):
                    driver.back()
                    self._sleep(settle_seconds)
                self._sleep(poll_seconds)
                continue
            if snapshot.page_kind == "home":
                return False
            driver.back()
            self._sleep(settle_seconds)
        logger.warning("返回搜索结果页超时。")
        return False

    def _wait_for_page(
        self,
        driver: AndroidDriver,
        selectors: dict[str, Selector],
        *,
        timeout: float,
        poll_seconds: float,
        expected: set[str],
        logger,
    ) -> PageSnapshot | None:
        deadline = time.time() + timeout
        last_snapshot: PageSnapshot | None = None
        while time.time() < deadline:
            ensure_not_cancelled(self._cancel_check)
            snapshot = self._capture_snapshot(driver, selectors)
            last_snapshot = snapshot
            if snapshot.page_kind in expected:
                return snapshot
            self._sleep(poll_seconds)

        expected_pages = ", ".join(sorted(expected))
        if last_snapshot is None:
            logger.warning("等待页面超时，目标页面：%s；未获取到页面快照。", expected_pages)
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
        visible_texts = driver.get_visible_texts(hierarchy_xml)
        page_kind = self._classify_page(hierarchy_xml, visible_texts, selectors)
        return PageSnapshot(hierarchy_xml=hierarchy_xml, visible_texts=visible_texts, page_kind=page_kind)

    def _classify_page(self, hierarchy_xml: str, visible_texts: list[str], selectors: dict[str, Selector]) -> str:
        joined_text = "\n".join(visible_texts)
        if self._is_video_comment_panel(hierarchy_xml, visible_texts):
            return "video_comment_panel"
        if self._is_video_detail_page(hierarchy_xml, joined_text):
            return "video_detail"
        if self._is_image_detail_page(hierarchy_xml, joined_text):
            return "image_detail"
        if self._is_search_results_page(visible_texts):
            return "search_results"
        if self._is_search_input_page(hierarchy_xml, visible_texts, selectors):
            return "search_input"
        if self._is_home_page(visible_texts):
            return "home"
        return "unknown"

    def _is_home_page(self, visible_texts: list[str]) -> bool:
        required = {"首页", "市集", "发布", "消息", "我"}
        return required.issubset(set(visible_texts))

    def _is_search_input_page(self, hierarchy_xml: str, visible_texts: list[str], selectors: dict[str, Selector]) -> bool:
        has_edit_text = "android.widget.EditText" in hierarchy_xml
        has_camera = self._visible_texts_contain_any_fragment(visible_texts, ("拍照搜索",))
        has_suggestions = self._visible_texts_contain_any_fragment(visible_texts, ("猜你想搜", "按住提问"))
        has_back = self._snapshot_matches_selector(selectors.get("back_button"), hierarchy_xml, visible_texts)
        return has_edit_text and has_camera and has_suggestions and has_back

    def _is_search_results_page(self, visible_texts: list[str]) -> bool:
        return self._visible_texts_contain_any_fragment(visible_texts, ("综合", "最新", "全部", "用户", "商品"))

    def _is_image_detail_page(self, hierarchy_xml: str, joined_text: str) -> bool:
        return "com.xingin.xhs:id/nickNameTV" in hierarchy_xml or (
            "评论框" in joined_text and "点赞 " in joined_text and "收藏 " in joined_text
        )

    def _is_video_detail_page(self, hierarchy_xml: str, joined_text: str) -> bool:
        return "com.xingin.xhs:id/matrixNickNameView" in hierarchy_xml or (
            "暂停" in joined_text and "评论" in joined_text and "收藏" in joined_text
        )

    def _is_video_comment_panel(self, hierarchy_xml: str, visible_texts: list[str]) -> bool:
        if "com.xingin.xhs:id/nickNameTV" in hierarchy_xml:
            return False
        if parse_total_comment_count(visible_texts) is None:
            return False
        if not has_comment_recycler(hierarchy_xml):
            return False
        joined_text = "\n".join(visible_texts)
        if "让大家听到你的声音" in joined_text or "留下你的想法吧" in joined_text:
            return True
        if "作者" in joined_text or "置顶评论" in joined_text:
            return True
        return "回复" in joined_text

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
            if strategy == "xpath" and value.startswith("//") and "EditText" in value:
                return "android.widget.EditText" in hierarchy_xml
        return False

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
            normalized_fragment = fragment.strip()
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

    def _click_required(self, driver: AndroidDriver, selector: Selector, label: str, settle_seconds: float) -> None:
        del label
        ensure_not_cancelled(self._cancel_check)
        driver.click(selector, timeout=5)
        self._sleep(settle_seconds)

    def _click_optional(self, driver: AndroidDriver, selector: Selector | None, settle_seconds: float) -> bool:
        return click_optional(
            driver,
            selector,
            settle_seconds=settle_seconds,
            check_cancelled=self._cancel_check,
        )

    def _sleep(self, seconds: float) -> None:
        sleep_seconds(seconds, check_cancelled=self._cancel_check)


def _title_hint_should_override(title_hint: str, current_title: str) -> bool:
    normalized_hint = title_hint.strip()
    normalized_current = current_title.strip()
    if not normalized_hint:
        return False
    if not normalized_current:
        return True
    if normalized_current.startswith("#") and normalized_current.count("#") >= 2 and normalized_hint.count("#") < 2:
        return True
    if len(normalized_current.replace(" ", "")) <= 2 and len(normalized_hint.replace(" ", "")) > 2:
        return True
    return False


def _merge_texts(base_texts: list[str], new_texts: list[str]) -> list[str]:
    merged = list(base_texts)
    seen = set(base_texts)
    for text in new_texts:
        if text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return merged
