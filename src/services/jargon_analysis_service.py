from __future__ import annotations

import math
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

from src.services.ai_text_service import ai_text_service
from src.services.settings_service import SettingsService
from src.services.shared_store_factory import SharedStoreFactory
from src.storage.mysql_analysis_store import MySQLAnalysisStore
from src.utils.time_utils import format_datetime


SOURCE_TYPE_TO_PLATFORM = {
    "xianyu": "xianyu",
    "xhs": "xiaohongshu",
}

SOURCE_TYPE_TO_RECORD_TYPE = {
    "xianyu": "listing",
    "xhs": "note",
}

PLATFORM_TO_SOURCE_TYPE = {value: key for key, value in SOURCE_TYPE_TO_PLATFORM.items()}

ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="jargon_analysis")
ANALYSIS_FUTURES: dict[int, Future[None]] = {}


class JargonAnalysisService:
    """共享黑话研判任务服务。"""

    def __init__(self, sqlite_path: Path) -> None:
        self.settings_service = SettingsService(sqlite_path)
        self.store_factory = SharedStoreFactory(self.settings_service)
        self.batch_size = 10

    def list_source_datasets(self) -> list[dict[str, Any]]:
        store = self._open_store()
        try:
            rows = store.list_analysis_sources()
        finally:
            store.close()

        datasets: list[dict[str, Any]] = []
        for row in rows:
            platform = str(row["platform"])
            source_type = PLATFORM_TO_SOURCE_TYPE.get(platform)
            if source_type is None:
                continue
            source_task_name = self._build_source_task_name(row)
            datasets.append(
                {
                    "source_type": source_type,
                    "source_task_id": int(row["id"]),
                    "source_task_name": source_task_name,
                    "label": f"{self._get_source_type_text(source_type)} | {source_task_name}",
                    "record_count": int(row["record_count"]),
                    "created_at": str(row["created_at"]),
                }
            )
        return datasets

    def create_task(self, *, source_type: str, source_task_id: int, keyword_id: int) -> dict[str, Any]:
        if source_type not in SOURCE_TYPE_TO_PLATFORM:
            raise ValueError("不支持的数据源类型")

        ai_text_service.validate_configuration()

        store = self._open_store()
        try:
            source_snapshot = store.get_analysis_source_snapshot(source_type=source_type, source_task_id=source_task_id)
            if source_snapshot is None:
                raise ValueError("未找到可分析的数据源")

            keyword = store.get_keyword(keyword_id)
            if keyword is None:
                raise ValueError("未找到黑话词条")

            task = store.create_jargon_analysis_task(
                source_type=source_type,
                source_task_id=source_task_id,
                source_task_name=str(source_snapshot["source_task_name"]),
                keyword_id=keyword_id,
                keyword_name_snapshot=str(keyword["keyword"]),
                keyword_meaning_snapshot=str(keyword["meaning"]),
                category_name_snapshot=str(keyword["category_name"]),
                subcategory_name_snapshot=str(keyword["subcategory_name"]),
                total_records=int(source_snapshot["record_count"]),
            )
        finally:
            store.close()

        self._submit_task(int(task["id"]))
        return task

    def list_tasks(self, *, page: int, page_size: int) -> dict[str, Any]:
        store = self._open_store()
        try:
            total = store.count_jargon_analysis_tasks()
            items = store.list_jargon_analysis_tasks(limit=page_size, offset=(page - 1) * page_size)
        finally:
            store.close()
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if page_size else 0,
        }

    def get_task_detail(self, task_id: int) -> dict[str, Any] | None:
        store = self._open_store()
        try:
            return store.get_jargon_analysis_task(task_id)
        finally:
            store.close()

    def get_task_results(self, task_id: int) -> list[dict[str, Any]]:
        store = self._open_store()
        try:
            task = store.get_jargon_analysis_task(task_id)
            if task is None:
                return []
            results = store.get_jargon_analysis_results(task_id)
            records = store.get_collected_records_by_ids([int(item["source_record_id"]) for item in results])
            records_by_id = {int(item["id"]): item for item in records}
        finally:
            store.close()

        items: list[dict[str, Any]] = []
        for result in results:
            record = records_by_id.get(int(result["source_record_id"]), {})
            matched_keywords = (
                [
                    {
                        "task_id": int(task["id"]),
                        "keyword_id": int(task["keyword_id"]),
                        "keyword": str(task["keyword_name"]),
                        "meaning": str(task["keyword_meaning"]),
                        "confidence": float(result["confidence"] or 0),
                    }
                ]
                if bool(result["is_match"])
                else []
            )
            items.append(
                {
                    "id": int(result["id"]),
                    "source_record_id": int(result["source_record_id"]),
                    "is_match": bool(result["is_match"]),
                    "confidence": float(result["confidence"] or 0),
                    "reason": str(result["reason"] or ""),
                    "record": self._serialize_record(record, matched_keywords, {int(result["source_record_id"])}),
                }
            )
        return items

    def list_source_records(
        self,
        *,
        source_type: str,
        page: int,
        page_size: int,
        task_id: int | None,
        search: str | None,
        matched_only: bool,
    ) -> dict[str, Any]:
        if source_type not in SOURCE_TYPE_TO_PLATFORM:
            raise ValueError("不支持的数据源类型")

        store = self._open_store()
        try:
            total = store.count_source_records(
                source_type=source_type,
                task_id=task_id,
                search=search,
                matched_only=matched_only,
            )
            rows = store.list_source_records(
                source_type=source_type,
                task_id=task_id,
                search=search,
                matched_only=matched_only,
                limit=page_size,
                offset=(page - 1) * page_size,
            )
            record_ids = [int(row["id"]) for row in rows]
            matched_map, analyzed_ids = store.get_record_match_map(source_type=source_type, record_ids=record_ids)
        finally:
            store.close()

        return {
            "items": [self._serialize_record(row, matched_map.get(int(row["id"]), []), analyzed_ids) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if page_size else 0,
        }

    def list_matched_records(
        self,
        *,
        source_type: str,
        page: int,
        page_size: int,
        task_id: int | None,
        search: str | None,
        keyword_id: int | None,
        category_id: int | None,
        subcategory_id: int | None,
        min_confidence: float | None,
    ) -> dict[str, Any]:
        if source_type not in SOURCE_TYPE_TO_PLATFORM:
            raise ValueError("不支持的数据源类型")

        store = self._open_store()
        try:
            total = store.count_matched_source_records(
                source_type=source_type,
                task_id=task_id,
                search=search,
                keyword_id=keyword_id,
                category_id=category_id,
                subcategory_id=subcategory_id,
                min_confidence=min_confidence,
            )
            rows = store.list_matched_source_records(
                source_type=source_type,
                task_id=task_id,
                search=search,
                keyword_id=keyword_id,
                category_id=category_id,
                subcategory_id=subcategory_id,
                min_confidence=min_confidence,
                limit=page_size,
                offset=(page - 1) * page_size,
            )
            record_ids = [int(row["id"]) for row in rows]
            matched_map, _ = store.get_record_match_details(source_type=source_type, record_ids=record_ids)
        finally:
            store.close()

        return {
            "items": [self._serialize_matched_record_summary(row, matched_map.get(int(row["id"]), [])) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if page_size else 0,
        }

    def get_matched_record_detail(self, record_id: int) -> dict[str, Any] | None:
        store = self._open_store()
        try:
            record = store.get_collected_record(record_id)
            if record is None:
                return None

            platform = str(record.get("platform") or "")
            source_type = PLATFORM_TO_SOURCE_TYPE.get(platform)
            if source_type is None:
                return None

            matched_map, _ = store.get_record_match_details(source_type=source_type, record_ids=[record_id])
        finally:
            store.close()

        matches = matched_map.get(record_id, [])
        if not matches:
            return None
        return self._serialize_matched_record_detail(record, matches)

    def process_task(self, task_id: int) -> None:
        store: MySQLAnalysisStore | None = None
        try:
            store = self._open_store()
            task = store.get_jargon_analysis_task(task_id)
            if task is None:
                return
            if str(task["status"]) == "completed":
                return

            store.update_jargon_analysis_task(
                task_id,
                {
                    "status": "running",
                    "started_at": format_datetime(None),
                    "completed_at": None,
                    "error_message": "",
                },
            )

            records = store.get_source_records_for_analysis(
                source_type=str(task["source_type"]),
                source_task_id=int(task["source_task_id"]),
            )
            total_records = len(records)
            store.update_jargon_analysis_task(task_id, {"total_records": total_records})

            if not records:
                store.update_jargon_analysis_task(
                    task_id,
                    {
                        "status": "completed",
                        "completed_at": format_datetime(None),
                        "processed_records": 0,
                        "matched_records": 0,
                    },
                )
                return

            processed = 0
            matched = 0

            for batch in self._chunks(records, self.batch_size):
                result = ai_text_service.analyze_jargon_records(
                    records=batch,
                    jargon_name=str(task["keyword_name"]),
                    jargon_meaning=str(task["keyword_meaning"]),
                    source_type=str(task["source_type"]),
                    category_name=str(task["category_name"] or ""),
                    subcategory_name=str(task["subcategory_name"] or ""),
                )
                if not result.get("success"):
                    raise RuntimeError(str(result.get("error") or "AI 研判失败"))

                rows: list[dict[str, Any]] = []
                for item in result.get("results", []):
                    is_match = bool(item.get("is_match"))
                    if is_match:
                        matched += 1
                    processed += 1
                    rows.append(
                        {
                            "source_record_id": int(item["record_id"]),
                            "is_match": is_match,
                            "confidence": float(item.get("confidence") or 0),
                            "reason": str(item.get("reason") or ""),
                            "raw_response": item,
                        }
                    )

                if rows:
                    store.insert_jargon_analysis_results(
                        task_id=task_id,
                        source_type=str(task["source_type"]),
                        results=rows,
                    )

                store.update_jargon_analysis_task(
                    task_id,
                    {
                        "processed_records": processed,
                        "matched_records": matched,
                    },
                )

            store.update_jargon_analysis_task(
                task_id,
                {
                    "status": "completed",
                    "completed_at": format_datetime(None),
                    "processed_records": processed,
                    "matched_records": matched,
                },
            )
        except Exception as exc:
            if store is not None:
                store.update_jargon_analysis_task(
                    task_id,
                    {
                        "status": "failed",
                        "error_message": str(exc),
                        "completed_at": format_datetime(None),
                    },
                )
        finally:
            if store is not None:
                store.close()

    def _submit_task(self, task_id: int) -> None:
        active_future = ANALYSIS_FUTURES.get(task_id)
        if active_future is not None and not active_future.done():
            return

        future = ANALYSIS_EXECUTOR.submit(self.process_task, task_id)
        ANALYSIS_FUTURES[task_id] = future

        def _cleanup(done_future: Future[None], *, analysis_task_id: int) -> None:
            current = ANALYSIS_FUTURES.get(analysis_task_id)
            if current is done_future:
                ANALYSIS_FUTURES.pop(analysis_task_id, None)

        def _on_done(done_future: Future[None]) -> None:
            _cleanup(done_future, analysis_task_id=task_id)

        future.add_done_callback(_on_done)

    def _open_store(self) -> MySQLAnalysisStore:
        return self.store_factory.create_analysis_store(logger_name="jargon_analysis_service")

    @staticmethod
    def _chunks(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
        for index in range(0, len(items), size):
            yield items[index : index + size]

    def _serialize_record(
        self,
        record: dict[str, Any],
        matched_keywords: list[dict[str, Any]],
        analyzed_ids: set[int],
    ) -> dict[str, Any]:
        if not record:
            return {}

        metrics = record.get("metrics") or {}
        extra = record.get("extra") or {}
        record_id = int(record["id"])
        platform = str(record["platform"])
        source_type = PLATFORM_TO_SOURCE_TYPE.get(platform, platform)
        analysis_status = "matched" if matched_keywords else ("analyzed" if record_id in analyzed_ids else "unanalyzed")

        if source_type == "xianyu":
            price_value = str(metrics.get("price") or "").strip()
            price_label = f"¥{price_value}" if price_value else ""
            return {
                "id": record_id,
                "platform": source_type,
                "source_task_id": int(record["local_run_id"]),
                "source_label": str(record.get("keyword") or ""),
                "title": str(record.get("title") or ""),
                "content": str(record.get("content_text") or ""),
                "image_url": str(extra.get("image_url") or ""),
                "price": price_value,
                "price_label": price_label,
                "link": str(extra.get("link") or ""),
                "created_at": str(record.get("created_at") or ""),
                "matched_keywords": matched_keywords,
                "analysis_status": analysis_status,
                "want_count": metrics.get("want_count"),
                "view_count": metrics.get("view_count"),
                "seller_name": str(record.get("author_name") or ""),
                "seller_region": str(record.get("location_text") or ""),
            }

        return {
            "id": record_id,
            "platform": source_type,
            "source_task_id": int(record["local_run_id"]),
            "source_label": str(record.get("keyword") or ""),
            "title": str(record.get("title") or ""),
            "content": str(record.get("content_text") or ""),
            "image_url": str(extra.get("image_url") or ""),
            "author": str(record.get("author_name") or ""),
            "publish_time": str(record.get("published_text") or ""),
            "likes": metrics.get("like_count") or 0,
            "collects": metrics.get("favorite_count") or 0,
            "comment_count": metrics.get("comment_count") or 0,
            "link": str(extra.get("link") or ""),
            "created_at": str(record.get("created_at") or ""),
            "matched_keywords": matched_keywords,
            "analysis_status": analysis_status,
            "topics": extra.get("topics") or [],
            "ip_location": str(record.get("ip_location") or ""),
        }

    def _serialize_matched_record_summary(
        self,
        record: dict[str, Any],
        matches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        record_id = int(record["id"])
        basic_matches = [
            {
                "task_id": int(item["task_id"]),
                "keyword_id": int(item["keyword_id"] or 0),
                "keyword": str(item["keyword"] or ""),
                "meaning": str(item["meaning"] or ""),
                "confidence": float(item["confidence"] or 0),
            }
            for item in matches
        ]
        summary = self._serialize_record(record, basic_matches, {record_id})
        summary.update(
            {
                "local_run_id": int(record.get("local_run_id") or 0),
                "item_index": int(record.get("item_index") or 0),
                "record_type": str(record.get("record_type") or ""),
                "match_count": len(matches),
                "top_confidence": max((float(item["confidence"] or 0) for item in matches), default=0),
                "matches": matches,
            }
        )
        return summary

    def _serialize_matched_record_detail(
        self,
        record: dict[str, Any],
        matches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        detail = self._serialize_matched_record_summary(record, matches)
        detail.update(
            {
                "author_name": str(record.get("author_name") or ""),
                "author_id": str(record.get("author_id") or ""),
                "location_text": str(record.get("location_text") or ""),
                "published_text": str(record.get("published_text") or ""),
                "metrics": record.get("metrics") if isinstance(record.get("metrics"), dict) else {},
                "extra": record.get("extra") if isinstance(record.get("extra"), dict) else {},
                "raw_visible_texts": record.get("raw_visible_texts")
                if isinstance(record.get("raw_visible_texts"), list)
                else [],
            }
        )
        return detail

    @staticmethod
    def _build_source_task_name(row: dict[str, Any]) -> str:
        config = row.get("config") if isinstance(row.get("config"), dict) else {}
        adapter_options = config.get("adapter_options") if isinstance(config, dict) else {}
        if isinstance(adapter_options, dict):
            keyword = str(adapter_options.get("search_keyword") or "").strip()
            if keyword:
                return keyword
        return str(row.get("task_name") or f"运行 #{row.get('id')}")

    @staticmethod
    def _get_source_type_text(source_type: str) -> str:
        return "小红书" if source_type == "xhs" else "闲鱼"
