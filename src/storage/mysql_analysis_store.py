from __future__ import annotations

import json
import logging
from typing import Any, cast

from src.models.task_models import MySQLConfig, SSHTunnelConfig
from src.storage.result_store import MySQLResultStore
from src.utils.time_utils import format_datetime


SOURCE_TYPE_TO_PLATFORM = {
    "xianyu": "xianyu",
    "xhs": "xiaohongshu",
}

SOURCE_TYPE_TO_RECORD_TYPE = {
    "xianyu": "listing",
    "xhs": "note",
}


class MySQLAnalysisStore:
    """共享 MySQL 黑话字典与研判存储层。"""

    def __init__(
        self,
        mysql_config: MySQLConfig,
        logger: logging.Logger,
        *,
        ssh_config: SSHTunnelConfig | None = None,
    ) -> None:
        self.run_store = MySQLResultStore(mysql_config, logger, ssh_config=ssh_config)
        self.connection = None

    def connect(self) -> None:
        self.run_store.connect()
        self.connection = self.run_store.connection
        self._ensure_tables()

    def close(self) -> None:
        self.run_store.close()
        self.connection = None

    def list_keyword_categories(self) -> list[dict[str, Any]]:
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM keyword_categories
            ORDER BY sort_order ASC, id ASC
            """
        )
        category_rows = cursor.fetchall()
        categories = {
            int(row["id"]): {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "description": str(row["description"] or ""),
                "sort_order": int(row["sort_order"] or 0),
                "subcategories": [],
                "keywords": [],
                "created_at": str(row["created_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
            for row in category_rows
        }

        cursor.execute(
            """
            SELECT *
            FROM keyword_subcategories
            ORDER BY sort_order ASC, id ASC
            """
        )
        subcategory_rows = cursor.fetchall()
        subcategories: dict[int, dict[str, Any]] = {}
        for row in subcategory_rows:
            item_id = int(row["id"])
            category_id = int(row["category_id"])
            item = {
                "id": item_id,
                "name": str(row["name"]),
                "description": str(row["description"] or ""),
                "category_id": category_id,
                "sort_order": int(row["sort_order"] or 0),
                "keywords": [],
                "created_at": str(row["created_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
            subcategories[item_id] = item
            category = categories.get(category_id)
            if category is not None:
                cast(list[dict[str, Any]], category["subcategories"]).append(item)

        cursor.execute(
            """
            SELECT
                keywords.*,
                keyword_categories.name AS category_name,
                keyword_subcategories.name AS subcategory_name
            FROM keywords
            LEFT JOIN keyword_categories ON keyword_categories.id = keywords.category_id
            LEFT JOIN keyword_subcategories ON keyword_subcategories.id = keywords.subcategory_id
            ORDER BY keywords.sort_order ASC, keywords.id ASC
            """
        )
        keyword_rows = cursor.fetchall()
        cursor.close()

        for row in keyword_rows:
            keyword = self._row_to_keyword(row)
            category = categories.get(keyword["category_id"])
            if category is not None:
                cast(list[dict[str, Any]], category["keywords"]).append(keyword)
            subcategory = subcategories.get(keyword["subcategory_id"])
            if subcategory is not None:
                cast(list[dict[str, Any]], subcategory["keywords"]).append(keyword)

        return list(categories.values())

    def create_keyword_category(self, *, name: str, description: str, sort_order: int) -> dict[str, Any]:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("分类名称不能为空")

        cursor = self._cursor(dictionary=True)
        cursor.execute("SELECT id FROM keyword_categories WHERE name = %s", (normalized_name,))
        if cursor.fetchone() is not None:
            cursor.close()
            raise ValueError(f"分类名称 '{normalized_name}' 已存在")

        timestamp = format_datetime(None)
        cursor.execute(
            """
            INSERT INTO keyword_categories (name, description, sort_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (normalized_name, str(description or "").strip(), int(sort_order), timestamp, timestamp),
        )
        category_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO keyword_subcategories (category_id, name, description, sort_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (category_id, "未分类", "系统自动创建的默认二级分类", 0, timestamp, timestamp),
        )
        cursor.close()
        return self._require_category(category_id)

    def update_keyword_category(self, category_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._require_category(category_id)
        updates: dict[str, Any] = {}
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("分类名称不能为空")
            if name != current["name"]:
                cursor = self._cursor(dictionary=True)
                cursor.execute("SELECT id FROM keyword_categories WHERE name = %s AND id != %s", (name, category_id))
                if cursor.fetchone() is not None:
                    cursor.close()
                    raise ValueError(f"分类名称 '{name}' 已存在")
                cursor.close()
            updates["name"] = name
        if "description" in payload:
            updates["description"] = str(payload.get("description") or "").strip()
        if "sort_order" in payload:
            updates["sort_order"] = int(payload.get("sort_order") or 0)
        if not updates:
            return current
        updates["updated_at"] = format_datetime(None)
        self._update_row("keyword_categories", category_id, updates)
        return self._require_category(category_id)

    def delete_keyword_category(self, category_id: int) -> None:
        self._require_category(category_id)
        cursor = self._cursor()
        cursor.execute("DELETE FROM keyword_categories WHERE id = %s", (category_id,))
        cursor.close()

    def create_keyword_subcategory(
        self,
        *,
        category_id: int,
        name: str,
        description: str,
        sort_order: int,
    ) -> dict[str, Any]:
        self._require_category(category_id)
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("二级分类名称不能为空")

        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id
            FROM keyword_subcategories
            WHERE category_id = %s AND name = %s
            """,
            (category_id, normalized_name),
        )
        if cursor.fetchone() is not None:
            cursor.close()
            raise ValueError(f"二级分类 '{normalized_name}' 已存在")

        timestamp = format_datetime(None)
        cursor.execute(
            """
            INSERT INTO keyword_subcategories (category_id, name, description, sort_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                category_id,
                normalized_name,
                str(description or "").strip(),
                int(sort_order),
                timestamp,
                timestamp,
            ),
        )
        subcategory_id = int(cursor.lastrowid)
        cursor.close()
        return self._require_subcategory(subcategory_id)

    def update_keyword_subcategory(self, subcategory_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._require_subcategory(subcategory_id)
        updates: dict[str, Any] = {}
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("二级分类名称不能为空")
            if name != current["name"]:
                cursor = self._cursor(dictionary=True)
                cursor.execute(
                    """
                    SELECT id
                    FROM keyword_subcategories
                    WHERE category_id = %s AND name = %s AND id != %s
                    """,
                    (current["category_id"], name, subcategory_id),
                )
                if cursor.fetchone() is not None:
                    cursor.close()
                    raise ValueError(f"二级分类 '{name}' 已存在")
                cursor.close()
            updates["name"] = name
        if "description" in payload:
            updates["description"] = str(payload.get("description") or "").strip()
        if "sort_order" in payload:
            updates["sort_order"] = int(payload.get("sort_order") or 0)
        if not updates:
            return current
        updates["updated_at"] = format_datetime(None)
        self._update_row("keyword_subcategories", subcategory_id, updates)
        return self._require_subcategory(subcategory_id)

    def delete_keyword_subcategory(self, subcategory_id: int) -> None:
        self._require_subcategory(subcategory_id)
        cursor = self._cursor()
        cursor.execute("DELETE FROM keyword_subcategories WHERE id = %s", (subcategory_id,))
        cursor.close()

    def create_keyword(
        self,
        *,
        category_id: int,
        subcategory_id: int,
        keyword: str,
        meaning: str,
        sort_order: int,
    ) -> dict[str, Any]:
        self._require_category(category_id)
        subcategory = self._require_subcategory(subcategory_id)
        if int(subcategory["category_id"]) != category_id:
            raise ValueError("二级分类不属于当前一级分类")

        normalized_keyword = str(keyword or "").strip()
        if not normalized_keyword:
            raise ValueError("黑话词条不能为空")
        normalized_meaning = str(meaning or "").strip() or normalized_keyword

        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id
            FROM keywords
            WHERE subcategory_id = %s AND keyword = %s
            """,
            (subcategory_id, normalized_keyword),
        )
        if cursor.fetchone() is not None:
            cursor.close()
            raise ValueError(f"黑话词条 '{normalized_keyword}' 已存在")

        timestamp = format_datetime(None)
        cursor.execute(
            """
            INSERT INTO keywords (
                category_id, subcategory_id, keyword, meaning, sort_order, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                category_id,
                subcategory_id,
                normalized_keyword,
                normalized_meaning,
                int(sort_order),
                timestamp,
                timestamp,
            ),
        )
        keyword_id = int(cursor.lastrowid)
        cursor.close()
        return self._require_keyword(keyword_id)

    def update_keyword(self, keyword_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._require_keyword(keyword_id)
        target_subcategory_id = int(payload.get("subcategory_id") or current["subcategory_id"])
        subcategory = self._require_subcategory(target_subcategory_id)
        target_category_id = int(subcategory["category_id"])

        requested_category_id = payload.get("category_id")
        if requested_category_id is not None and int(requested_category_id) != target_category_id:
            raise ValueError("目标二级分类不属于指定一级分类")

        normalized_keyword = str(payload.get("keyword") or current["keyword"]).strip()
        if not normalized_keyword:
            raise ValueError("黑话词条不能为空")
        normalized_meaning = str(payload.get("meaning") if "meaning" in payload else current["meaning"]).strip()
        if not normalized_meaning:
            normalized_meaning = normalized_keyword

        if normalized_keyword != current["keyword"] or target_subcategory_id != current["subcategory_id"]:
            cursor = self._cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id
                FROM keywords
                WHERE subcategory_id = %s AND keyword = %s AND id != %s
                """,
                (target_subcategory_id, normalized_keyword, keyword_id),
            )
            if cursor.fetchone() is not None:
                cursor.close()
                raise ValueError(f"黑话词条 '{normalized_keyword}' 已存在")
            cursor.close()

        updates: dict[str, Any] = {
            "category_id": target_category_id,
            "subcategory_id": target_subcategory_id,
            "keyword": normalized_keyword,
            "meaning": normalized_meaning,
            "updated_at": format_datetime(None),
        }
        if "sort_order" in payload:
            updates["sort_order"] = int(payload.get("sort_order") or 0)
        self._update_row("keywords", keyword_id, updates)
        return self._require_keyword(keyword_id)

    def delete_keyword(self, keyword_id: int) -> None:
        self._require_keyword(keyword_id)
        cursor = self._cursor()
        cursor.execute("DELETE FROM keywords WHERE id = %s", (keyword_id,))
        cursor.close()

    def get_keyword(self, keyword_id: int) -> dict[str, Any] | None:
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                keywords.*,
                keyword_categories.name AS category_name,
                keyword_subcategories.name AS subcategory_name
            FROM keywords
            LEFT JOIN keyword_categories ON keyword_categories.id = keywords.category_id
            LEFT JOIN keyword_subcategories ON keyword_subcategories.id = keywords.subcategory_id
            WHERE keywords.id = %s
            """,
            (keyword_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return self._row_to_keyword(row) if row is not None else None

    def recover_interrupted_jargon_tasks(self) -> int:
        return 0

    def create_jargon_analysis_task(
        self,
        *,
        source_type: str,
        source_task_id: int,
        source_task_name: str,
        keyword_id: int,
        keyword_name_snapshot: str,
        keyword_meaning_snapshot: str,
        category_name_snapshot: str,
        subcategory_name_snapshot: str,
        total_records: int,
    ) -> dict[str, Any]:
        timestamp = format_datetime(None)
        cursor = self._cursor()
        cursor.execute(
            """
            INSERT INTO jargon_analysis_tasks (
                source_type,
                source_task_id,
                source_task_name,
                keyword_id,
                keyword_name_snapshot,
                keyword_meaning_snapshot,
                category_name_snapshot,
                subcategory_name_snapshot,
                status,
                total_records,
                processed_records,
                matched_records,
                error_message,
                created_at,
                started_at,
                completed_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_type,
                source_task_id,
                source_task_name,
                keyword_id,
                keyword_name_snapshot,
                keyword_meaning_snapshot,
                category_name_snapshot,
                subcategory_name_snapshot,
                "pending",
                total_records,
                0,
                0,
                "",
                timestamp,
                None,
                None,
                timestamp,
            ),
        )
        task_id = int(cursor.lastrowid)
        cursor.close()
        return self.get_jargon_analysis_task(task_id) or {}

    def count_jargon_analysis_tasks(self) -> int:
        cursor = self._cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM jargon_analysis_tasks")
        row = cursor.fetchone()
        cursor.close()
        return int(row["total"] or 0) if row is not None else 0

    def list_jargon_analysis_tasks(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM jargon_analysis_tasks
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_jargon_task(row) for row in rows]

    def get_jargon_analysis_task(self, task_id: int) -> dict[str, Any] | None:
        cursor = self._cursor(dictionary=True)
        cursor.execute("SELECT * FROM jargon_analysis_tasks WHERE id = %s", (task_id,))
        row = cursor.fetchone()
        cursor.close()
        return self._row_to_jargon_task(row) if row is not None else None

    def update_jargon_analysis_task(self, task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if self.get_jargon_analysis_task(task_id) is None:
            raise KeyError(f"黑话研判任务不存在：{task_id}")
        updates = dict(payload)
        updates["updated_at"] = format_datetime(None)
        self._update_row("jargon_analysis_tasks", task_id, updates)
        return self.get_jargon_analysis_task(task_id) or {}

    def insert_jargon_analysis_results(
        self,
        *,
        task_id: int,
        source_type: str,
        results: list[dict[str, Any]],
    ) -> None:
        if not results:
            return

        timestamp = format_datetime(None)
        rows = [
            (
                task_id,
                source_type,
                int(item["source_record_id"]),
                1 if bool(item.get("is_match")) else 0,
                float(item.get("confidence") or 0),
                str(item.get("reason") or ""),
                json.dumps(item.get("raw_response"), ensure_ascii=False) if item.get("raw_response") is not None else None,
                timestamp,
                timestamp,
            )
            for item in results
        ]
        cursor = self._cursor()
        cursor.executemany(
            """
            INSERT INTO jargon_analysis_results (
                task_id, source_type, source_record_id, is_match, confidence, reason,
                raw_response_json, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                source_type = VALUES(source_type),
                is_match = VALUES(is_match),
                confidence = VALUES(confidence),
                reason = VALUES(reason),
                raw_response_json = VALUES(raw_response_json),
                updated_at = VALUES(updated_at)
            """,
            rows,
        )
        cursor.close()

    def get_jargon_analysis_results(self, task_id: int) -> list[dict[str, Any]]:
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM jargon_analysis_results
            WHERE task_id = %s
            ORDER BY is_match DESC, confidence DESC, id ASC
            """,
            (task_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_jargon_result(row) for row in rows]

    def get_record_match_details(
        self,
        *,
        source_type: str,
        record_ids: list[int],
    ) -> tuple[dict[int, list[dict[str, Any]]], set[int]]:
        if not record_ids:
            return {}, set()

        placeholders = ", ".join(["%s" for _ in record_ids])
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            f"""
            SELECT
                jargon_analysis_results.source_record_id,
                jargon_analysis_results.is_match,
                jargon_analysis_results.confidence,
                jargon_analysis_results.reason,
                jargon_analysis_tasks.id AS task_id,
                jargon_analysis_tasks.keyword_id,
                jargon_analysis_tasks.keyword_name_snapshot,
                jargon_analysis_tasks.keyword_meaning_snapshot,
                jargon_analysis_tasks.category_name_snapshot,
                jargon_analysis_tasks.subcategory_name_snapshot,
                jargon_analysis_tasks.created_at AS task_created_at,
                jargon_analysis_tasks.completed_at AS task_completed_at
            FROM jargon_analysis_results
            JOIN jargon_analysis_tasks
                ON jargon_analysis_tasks.id = jargon_analysis_results.task_id
            WHERE jargon_analysis_results.source_type = %s
              AND jargon_analysis_results.source_record_id IN ({placeholders})
              AND jargon_analysis_tasks.status = 'completed'
            ORDER BY jargon_analysis_results.source_record_id ASC,
                     jargon_analysis_results.confidence DESC,
                     jargon_analysis_results.id DESC
            """,
            (source_type, *record_ids),
        )
        rows = cursor.fetchall()
        cursor.close()

        matched_map: dict[int, list[dict[str, Any]]] = {}
        analyzed_ids: set[int] = set()
        for row in rows:
            record_id = int(row["source_record_id"])
            analyzed_ids.add(record_id)
            if not bool(row["is_match"]):
                continue
            matched_map.setdefault(record_id, [])
            matched_map[record_id].append(
                {
                    "task_id": int(row["task_id"]),
                    "keyword_id": int(row["keyword_id"] or 0),
                    "keyword": str(row["keyword_name_snapshot"] or ""),
                    "meaning": str(row["keyword_meaning_snapshot"] or ""),
                    "confidence": float(row["confidence"] or 0),
                    "reason": str(row["reason"] or ""),
                    "category_name": str(row["category_name_snapshot"] or ""),
                    "subcategory_name": str(row["subcategory_name_snapshot"] or ""),
                    "task_created_at": str(row["task_created_at"] or ""),
                    "task_completed_at": str(row["task_completed_at"] or ""),
                }
            )

        for record_id, items in matched_map.items():
            deduplicated: dict[int, dict[str, Any]] = {}
            for item in items:
                identity = int(item["keyword_id"] or item["task_id"])
                previous = deduplicated.get(identity)
                if previous is None or float(item["confidence"]) > float(previous["confidence"]):
                    deduplicated[identity] = item
            matched_map[record_id] = sorted(deduplicated.values(), key=lambda item: float(item["confidence"]), reverse=True)

        return matched_map, analyzed_ids

    def get_record_match_map(
        self,
        *,
        source_type: str,
        record_ids: list[int],
    ) -> tuple[dict[int, list[dict[str, Any]]], set[int]]:
        detailed_map, analyzed_ids = self.get_record_match_details(source_type=source_type, record_ids=record_ids)
        matched_map = {
            record_id: [
                {
                    "task_id": int(item["task_id"]),
                    "keyword_id": int(item["keyword_id"] or 0),
                    "keyword": str(item["keyword"] or ""),
                    "meaning": str(item["meaning"] or ""),
                    "confidence": float(item["confidence"] or 0),
                }
                for item in items
            ]
            for record_id, items in detailed_map.items()
        }
        return matched_map, analyzed_ids

    def count_matched_source_records(
        self,
        *,
        source_type: str,
        task_id: int | None,
        search: str | None,
        keyword_id: int | None,
        category_id: int | None,
        subcategory_id: int | None,
        min_confidence: float | None,
    ) -> int:
        where_sql, params = self._build_matched_record_where(
            source_type=source_type,
            task_id=task_id,
            search=search,
            keyword_id=keyword_id,
            category_id=category_id,
            subcategory_id=subcategory_id,
            min_confidence=min_confidence,
        )
        cursor = self._cursor(dictionary=True)
        cursor.execute(f"SELECT COUNT(*) AS total FROM collected_records {where_sql}", params)
        row = cursor.fetchone()
        cursor.close()
        return int(row["total"] or 0) if row is not None else 0

    def list_matched_source_records(
        self,
        *,
        source_type: str,
        task_id: int | None,
        search: str | None,
        keyword_id: int | None,
        category_id: int | None,
        subcategory_id: int | None,
        min_confidence: float | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        where_sql, params = self._build_matched_record_where(
            source_type=source_type,
            task_id=task_id,
            search=search,
            keyword_id=keyword_id,
            category_id=category_id,
            subcategory_id=subcategory_id,
            min_confidence=min_confidence,
        )
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            f"""
            SELECT *
            FROM collected_records
            {where_sql}
            ORDER BY local_run_id DESC, item_index ASC, id ASC
            LIMIT %s OFFSET %s
            """,
            (*params, limit, offset),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [MySQLResultStore._row_to_collected_record(row) for row in rows]

    def list_analysis_sources(self) -> list[dict[str, Any]]:
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                task_runs.*,
                collected_records.platform AS collected_platform,
                COUNT(collected_records.id) AS record_count
            FROM task_runs
            JOIN collected_records ON collected_records.local_run_id = task_runs.id
            WHERE (
                (collected_records.platform = 'xianyu' AND collected_records.record_type = 'listing')
                OR
                (collected_records.platform = 'xiaohongshu' AND collected_records.record_type = 'note')
            )
            GROUP BY task_runs.id, collected_records.platform
            HAVING COUNT(collected_records.id) > 0
            ORDER BY task_runs.id DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()

        items: list[dict[str, Any]] = []
        for row in rows:
            run = MySQLResultStore._row_to_run_summary(row)
            run["platform"] = str(row["collected_platform"] or run["platform"])
            run["record_count"] = int(row["record_count"] or 0)
            items.append(run)
        return items

    def get_analysis_source_snapshot(self, *, source_type: str, source_task_id: int) -> dict[str, Any] | None:
        platform, record_type = self._resolve_source_filters(source_type)
        run = self.get_run(source_task_id)
        if run is None:
            return None

        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT COUNT(*) AS record_count
            FROM collected_records
            WHERE local_run_id = %s AND platform = %s AND record_type = %s
            """,
            (source_task_id, platform, record_type),
        )
        row = cursor.fetchone()
        cursor.close()

        record_count = int(row["record_count"] or 0) if row is not None else 0
        if record_count <= 0:
            return None
        return {
            "source_task_name": self._build_source_task_name(run),
            "record_count": record_count,
            "created_at": str(run["created_at"] or ""),
        }

    def get_source_records_for_analysis(self, *, source_type: str, source_task_id: int) -> list[dict[str, Any]]:
        platform, record_type = self._resolve_source_filters(source_type)
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM collected_records
            WHERE local_run_id = %s AND platform = %s AND record_type = %s
            ORDER BY item_index ASC, id ASC
            """,
            (source_task_id, platform, record_type),
        )
        rows = cursor.fetchall()
        cursor.close()

        items: list[dict[str, Any]] = []
        for row in rows:
            record = MySQLResultStore._row_to_collected_record(row)
            items.append(
                {
                    "record_id": int(record["id"]),
                    "title": str(record["title"] or ""),
                    "content": str(record["content_text"] or ""),
                    "metadata": self._build_analysis_metadata(record, source_type),
                }
            )
        return items

    def count_source_records(
        self,
        *,
        source_type: str,
        task_id: int | None,
        search: str | None,
        matched_only: bool,
    ) -> int:
        where_sql, params = self._build_source_record_where(
            source_type=source_type,
            task_id=task_id,
            search=search,
            matched_only=matched_only,
        )
        cursor = self._cursor(dictionary=True)
        cursor.execute(f"SELECT COUNT(*) AS total FROM collected_records {where_sql}", params)
        row = cursor.fetchone()
        cursor.close()
        return int(row["total"] or 0) if row is not None else 0

    def list_source_records(
        self,
        *,
        source_type: str,
        task_id: int | None,
        search: str | None,
        matched_only: bool,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        where_sql, params = self._build_source_record_where(
            source_type=source_type,
            task_id=task_id,
            search=search,
            matched_only=matched_only,
        )
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            f"""
            SELECT *
            FROM collected_records
            {where_sql}
            ORDER BY local_run_id DESC, item_index ASC, id ASC
            LIMIT %s OFFSET %s
            """,
            (*params, limit, offset),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [MySQLResultStore._row_to_collected_record(row) for row in rows]

    def get_collected_records_by_ids(self, record_ids: list[int]) -> list[dict[str, Any]]:
        if not record_ids:
            return []
        placeholders = ", ".join(["%s" for _ in record_ids])
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            f"""
            SELECT *
            FROM collected_records
            WHERE id IN ({placeholders})
            """,
            record_ids,
        )
        rows = cursor.fetchall()
        cursor.close()
        return [MySQLResultStore._row_to_collected_record(row) for row in rows]

    def get_collected_record(self, record_id: int) -> dict[str, Any] | None:
        cursor = self._cursor(dictionary=True)
        cursor.execute("SELECT * FROM collected_records WHERE id = %s", (record_id,))
        row = cursor.fetchone()
        cursor.close()
        return MySQLResultStore._row_to_collected_record(row) if row is not None else None

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        return self.run_store.get_run(run_id)

    def upsert_keyword_category_row(self, row: dict[str, Any]) -> None:
        self._upsert_simple(
            """
            INSERT INTO keyword_categories (id, name, description, sort_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                description = VALUES(description),
                sort_order = VALUES(sort_order),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at)
            """,
            (
                int(row["id"]),
                str(row.get("name") or ""),
                str(row.get("description") or ""),
                int(row.get("sort_order") or 0),
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
            ),
        )

    def upsert_keyword_subcategory_row(self, row: dict[str, Any]) -> None:
        self._upsert_simple(
            """
            INSERT INTO keyword_subcategories (id, category_id, name, description, sort_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                category_id = VALUES(category_id),
                name = VALUES(name),
                description = VALUES(description),
                sort_order = VALUES(sort_order),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at)
            """,
            (
                int(row["id"]),
                int(row["category_id"]),
                str(row.get("name") or ""),
                str(row.get("description") or ""),
                int(row.get("sort_order") or 0),
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
            ),
        )

    def upsert_keyword_row(self, row: dict[str, Any]) -> None:
        self._upsert_simple(
            """
            INSERT INTO keywords (id, category_id, subcategory_id, keyword, meaning, sort_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                category_id = VALUES(category_id),
                subcategory_id = VALUES(subcategory_id),
                keyword = VALUES(keyword),
                meaning = VALUES(meaning),
                sort_order = VALUES(sort_order),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at)
            """,
            (
                int(row["id"]),
                int(row["category_id"]),
                int(row["subcategory_id"]),
                str(row.get("keyword") or ""),
                str(row.get("meaning") or ""),
                int(row.get("sort_order") or 0),
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
            ),
        )

    def upsert_jargon_task_row(self, row: dict[str, Any]) -> None:
        self._upsert_simple(
            """
            INSERT INTO jargon_analysis_tasks (
                id, source_type, source_task_id, source_task_name, keyword_id,
                keyword_name_snapshot, keyword_meaning_snapshot, category_name_snapshot,
                subcategory_name_snapshot, status, total_records, processed_records,
                matched_records, error_message, created_at, started_at, completed_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                source_type = VALUES(source_type),
                source_task_id = VALUES(source_task_id),
                source_task_name = VALUES(source_task_name),
                keyword_id = VALUES(keyword_id),
                keyword_name_snapshot = VALUES(keyword_name_snapshot),
                keyword_meaning_snapshot = VALUES(keyword_meaning_snapshot),
                category_name_snapshot = VALUES(category_name_snapshot),
                subcategory_name_snapshot = VALUES(subcategory_name_snapshot),
                status = VALUES(status),
                total_records = VALUES(total_records),
                processed_records = VALUES(processed_records),
                matched_records = VALUES(matched_records),
                error_message = VALUES(error_message),
                created_at = VALUES(created_at),
                started_at = VALUES(started_at),
                completed_at = VALUES(completed_at),
                updated_at = VALUES(updated_at)
            """,
            (
                int(row["id"]),
                str(row.get("source_type") or ""),
                int(row.get("source_task_id") or 0),
                str(row.get("source_task_name") or ""),
                int(row.get("keyword_id") or 0),
                str(row.get("keyword_name_snapshot") or row.get("keyword_name") or ""),
                str(row.get("keyword_meaning_snapshot") or row.get("keyword_meaning") or ""),
                str(row.get("category_name_snapshot") or row.get("category_name") or ""),
                str(row.get("subcategory_name_snapshot") or row.get("subcategory_name") or ""),
                str(row.get("status") or "pending"),
                int(row.get("total_records") or 0),
                int(row.get("processed_records") or 0),
                int(row.get("matched_records") or 0),
                str(row.get("error_message") or ""),
                str(row.get("created_at") or ""),
                row.get("started_at"),
                row.get("completed_at"),
                str(row.get("updated_at") or ""),
            ),
        )

    def upsert_jargon_result_row(self, row: dict[str, Any]) -> None:
        self._upsert_simple(
            """
            INSERT INTO jargon_analysis_results (
                id, task_id, source_type, source_record_id, is_match, confidence, reason,
                raw_response_json, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                task_id = VALUES(task_id),
                source_type = VALUES(source_type),
                source_record_id = VALUES(source_record_id),
                is_match = VALUES(is_match),
                confidence = VALUES(confidence),
                reason = VALUES(reason),
                raw_response_json = VALUES(raw_response_json),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at)
            """,
            (
                int(row["id"]),
                int(row["task_id"]),
                str(row.get("source_type") or ""),
                int(row.get("source_record_id") or 0),
                1 if bool(row.get("is_match")) else 0,
                float(row.get("confidence") or 0),
                str(row.get("reason") or ""),
                MySQLResultStore._dump_json(row.get("raw_response")),
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
            ),
        )

    def _ensure_tables(self) -> None:
        cursor = self._cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS keyword_categories (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                sort_order INT NOT NULL DEFAULT 0,
                created_at VARCHAR(32) NOT NULL DEFAULT '',
                updated_at VARCHAR(32) NOT NULL DEFAULT '',
                UNIQUE KEY uniq_keyword_categories_name (name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS keyword_subcategories (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                category_id BIGINT NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                sort_order INT NOT NULL DEFAULT 0,
                created_at VARCHAR(32) NOT NULL DEFAULT '',
                updated_at VARCHAR(32) NOT NULL DEFAULT '',
                UNIQUE KEY uniq_keyword_subcategories_name (category_id, name),
                INDEX idx_keyword_subcategories_category (category_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS keywords (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                category_id BIGINT NOT NULL,
                subcategory_id BIGINT NOT NULL,
                keyword VARCHAR(255) NOT NULL,
                meaning TEXT NOT NULL,
                sort_order INT NOT NULL DEFAULT 0,
                created_at VARCHAR(32) NOT NULL DEFAULT '',
                updated_at VARCHAR(32) NOT NULL DEFAULT '',
                UNIQUE KEY uniq_keywords_name (subcategory_id, keyword),
                INDEX idx_keywords_category (category_id, subcategory_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jargon_analysis_tasks (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                source_type VARCHAR(32) NOT NULL,
                source_task_id BIGINT NOT NULL,
                source_task_name VARCHAR(255) NOT NULL DEFAULT '',
                keyword_id BIGINT NOT NULL,
                keyword_name_snapshot VARCHAR(255) NOT NULL DEFAULT '',
                keyword_meaning_snapshot TEXT NOT NULL,
                category_name_snapshot VARCHAR(255) NOT NULL DEFAULT '',
                subcategory_name_snapshot VARCHAR(255) NOT NULL DEFAULT '',
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                total_records INT NOT NULL DEFAULT 0,
                processed_records INT NOT NULL DEFAULT 0,
                matched_records INT NOT NULL DEFAULT 0,
                error_message TEXT NOT NULL,
                created_at VARCHAR(32) NOT NULL DEFAULT '',
                started_at VARCHAR(32) NULL,
                completed_at VARCHAR(32) NULL,
                updated_at VARCHAR(32) NOT NULL DEFAULT '',
                INDEX idx_jargon_tasks_source (source_type, source_task_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jargon_analysis_results (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                task_id BIGINT NOT NULL,
                source_type VARCHAR(32) NOT NULL,
                source_record_id BIGINT NOT NULL,
                is_match TINYINT(1) NOT NULL DEFAULT 0,
                confidence DOUBLE NOT NULL DEFAULT 0,
                reason TEXT NOT NULL,
                raw_response_json LONGTEXT NULL,
                created_at VARCHAR(32) NOT NULL DEFAULT '',
                updated_at VARCHAR(32) NOT NULL DEFAULT '',
                UNIQUE KEY uniq_jargon_task_record (task_id, source_record_id),
                INDEX idx_jargon_results_source (source_type, source_record_id),
                INDEX idx_jargon_results_task (task_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.close()

    def _update_row(self, table_name: str, row_id: int, updates: dict[str, Any]) -> None:
        if not updates:
            return
        assignments = ", ".join(f"{key} = %s" for key in updates)
        values = [self._dump_json_if_needed(value) for value in updates.values()]
        cursor = self._cursor()
        cursor.execute(f"UPDATE {table_name} SET {assignments} WHERE id = %s", (*values, row_id))
        cursor.close()

    def _require_category(self, category_id: int) -> dict[str, Any]:
        cursor = self._cursor(dictionary=True)
        cursor.execute("SELECT * FROM keyword_categories WHERE id = %s", (category_id,))
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            raise KeyError(f"分类不存在：{category_id}")
        return {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "sort_order": int(row["sort_order"] or 0),
            "subcategories": [],
            "keywords": [],
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def _require_subcategory(self, subcategory_id: int) -> dict[str, Any]:
        cursor = self._cursor(dictionary=True)
        cursor.execute("SELECT * FROM keyword_subcategories WHERE id = %s", (subcategory_id,))
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            raise KeyError(f"二级分类不存在：{subcategory_id}")
        return {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "category_id": int(row["category_id"]),
            "sort_order": int(row["sort_order"] or 0),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def _require_keyword(self, keyword_id: int) -> dict[str, Any]:
        keyword = self.get_keyword(keyword_id)
        if keyword is None:
            raise KeyError(f"黑话词条不存在：{keyword_id}")
        return keyword

    def _resolve_source_filters(self, source_type: str) -> tuple[str, str]:
        platform = SOURCE_TYPE_TO_PLATFORM.get(source_type)
        record_type = SOURCE_TYPE_TO_RECORD_TYPE.get(source_type)
        if platform is None or record_type is None:
            raise ValueError("不支持的数据源类型")
        return platform, record_type

    def _build_source_record_where(
        self,
        *,
        source_type: str,
        task_id: int | None,
        search: str | None,
        matched_only: bool,
    ) -> tuple[str, list[Any]]:
        platform, record_type = self._resolve_source_filters(source_type)
        conditions = ["platform = %s", "record_type = %s"]
        params: list[Any] = [platform, record_type]

        if task_id is not None:
            conditions.append("local_run_id = %s")
            params.append(task_id)

        if search:
            like_pattern = f"%{str(search).strip()}%"
            conditions.append("(COALESCE(title, '') LIKE %s OR COALESCE(content_text, '') LIKE %s)")
            params.extend([like_pattern, like_pattern])

        if matched_only:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM jargon_analysis_results
                    JOIN jargon_analysis_tasks
                        ON jargon_analysis_tasks.id = jargon_analysis_results.task_id
                    WHERE jargon_analysis_results.source_record_id = collected_records.id
                      AND jargon_analysis_results.source_type = %s
                      AND jargon_analysis_results.is_match = 1
                      AND jargon_analysis_tasks.status = 'completed'
                )
                """
            )
            params.append(source_type)

        return f"WHERE {' AND '.join(conditions)}", params

    def _build_matched_record_where(
        self,
        *,
        source_type: str,
        task_id: int | None,
        search: str | None,
        keyword_id: int | None,
        category_id: int | None,
        subcategory_id: int | None,
        min_confidence: float | None,
    ) -> tuple[str, list[Any]]:
        platform, record_type = self._resolve_source_filters(source_type)
        conditions = ["collected_records.platform = %s", "collected_records.record_type = %s"]
        params: list[Any] = [platform, record_type]

        if task_id is not None:
            conditions.append("collected_records.local_run_id = %s")
            params.append(task_id)

        if search:
            like_pattern = f"%{str(search).strip()}%"
            conditions.append("(COALESCE(collected_records.title, '') LIKE %s OR COALESCE(collected_records.content_text, '') LIKE %s)")
            params.extend([like_pattern, like_pattern])

        match_conditions = [
            "jargon_analysis_results.source_record_id = collected_records.id",
            "jargon_analysis_results.source_type = %s",
            "jargon_analysis_results.is_match = 1",
            "jargon_analysis_tasks.status = 'completed'",
        ]
        match_params: list[Any] = [source_type]

        if keyword_id is not None:
            match_conditions.append("jargon_analysis_tasks.keyword_id = %s")
            match_params.append(keyword_id)

        if category_id is not None:
            match_conditions.append("keywords.category_id = %s")
            match_params.append(category_id)

        if subcategory_id is not None:
            match_conditions.append("keywords.subcategory_id = %s")
            match_params.append(subcategory_id)

        if min_confidence is not None:
            match_conditions.append("jargon_analysis_results.confidence >= %s")
            match_params.append(float(min_confidence))

        conditions.append(
            f"""
            EXISTS (
                SELECT 1
                FROM jargon_analysis_results
                JOIN jargon_analysis_tasks
                    ON jargon_analysis_tasks.id = jargon_analysis_results.task_id
                LEFT JOIN keywords
                    ON keywords.id = jargon_analysis_tasks.keyword_id
                WHERE {' AND '.join(match_conditions)}
            )
            """
        )
        params.extend(match_params)
        return f"WHERE {' AND '.join(conditions)}", params

    def _cursor(self, *, dictionary: bool = False):
        return self.run_store._cursor(dictionary=dictionary)

    def _upsert_simple(self, sql: str, params: tuple[Any, ...]) -> None:
        cursor = self._cursor()
        cursor.execute(sql, params)
        cursor.close()

    @staticmethod
    def _dump_json_if_needed(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value

    @staticmethod
    def _row_to_keyword(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "keyword": str(row["keyword"]),
            "meaning": str(row["meaning"] or ""),
            "category_id": int(row["category_id"]),
            "subcategory_id": int(row["subcategory_id"]),
            "category_name": str(row.get("category_name") or ""),
            "subcategory_name": str(row.get("subcategory_name") or ""),
            "sort_order": int(row.get("sort_order") or 0),
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }

    @staticmethod
    def _row_to_jargon_task(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "source_type": str(row["source_type"]),
            "source_task_id": int(row["source_task_id"]),
            "source_task_name": str(row.get("source_task_name") or ""),
            "keyword_id": int(row["keyword_id"]),
            "keyword_name": str(row.get("keyword_name_snapshot") or ""),
            "keyword_meaning": str(row.get("keyword_meaning_snapshot") or ""),
            "category_name": str(row.get("category_name_snapshot") or ""),
            "subcategory_name": str(row.get("subcategory_name_snapshot") or ""),
            "status": str(row["status"]),
            "total_records": int(row.get("total_records") or 0),
            "processed_records": int(row.get("processed_records") or 0),
            "matched_records": int(row.get("matched_records") or 0),
            "error_message": str(row.get("error_message") or ""),
            "created_at": str(row.get("created_at") or ""),
            "started_at": str(row.get("started_at") or ""),
            "completed_at": str(row.get("completed_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }

    @staticmethod
    def _row_to_jargon_result(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "task_id": int(row["task_id"]),
            "source_type": str(row["source_type"]),
            "source_record_id": int(row["source_record_id"]),
            "is_match": bool(int(row.get("is_match") or 0)),
            "confidence": float(row.get("confidence") or 0),
            "reason": str(row.get("reason") or ""),
            "raw_response": MySQLResultStore._load_json(row.get("raw_response_json")) or {},
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }

    @staticmethod
    def _build_source_task_name(run: dict[str, Any]) -> str:
        config = run.get("config") if isinstance(run.get("config"), dict) else {}
        adapter_options = config.get("adapter_options") if isinstance(config, dict) else {}
        if isinstance(adapter_options, dict):
            keyword = str(adapter_options.get("search_keyword") or "").strip()
            if keyword:
                return keyword
        task_name = str(run.get("task_name") or "").strip()
        return task_name or f"运行 #{run.get('id')}"

    @staticmethod
    def _build_analysis_metadata(record: dict[str, Any], source_type: str) -> str:
        metrics_value = record.get("metrics")
        extra_value = record.get("extra")
        metrics: dict[str, Any] = metrics_value if isinstance(metrics_value, dict) else {}
        extra: dict[str, Any] = extra_value if isinstance(extra_value, dict) else {}
        parts: list[str] = []
        keyword = str(record.get("keyword") or "").strip()
        if keyword:
            parts.append(f"关键词:{keyword}")

        if source_type == "xianyu":
            price = str(metrics.get("price") or "").strip()
            if price:
                parts.append(f"价格:{price}")
            author_name = str(record.get("author_name") or "").strip()
            if author_name:
                parts.append(f"卖家:{author_name}")
            location_text = str(record.get("location_text") or "").strip()
            if location_text:
                parts.append(f"地区:{location_text}")
            want_count = metrics.get("want_count")
            if want_count not in (None, ""):
                parts.append(f"想要:{want_count}")
            view_count = metrics.get("view_count")
            if view_count not in (None, ""):
                parts.append(f"浏览:{view_count}")
            link = str(extra.get("link") or "").strip()
            if link:
                parts.append(f"链接:{link}")
        else:
            author_name = str(record.get("author_name") or "").strip()
            if author_name:
                parts.append(f"作者:{author_name}")
            like_count = metrics.get("like_count")
            if like_count not in (None, ""):
                parts.append(f"点赞:{like_count}")
            favorite_count = metrics.get("favorite_count")
            if favorite_count not in (None, ""):
                parts.append(f"收藏:{favorite_count}")
            comment_count = metrics.get("comment_count")
            if comment_count not in (None, ""):
                parts.append(f"评论:{comment_count}")
            published_text = str(record.get("published_text") or "").strip()
            if published_text:
                parts.append(f"发布时间:{published_text}")
            topics = extra.get("topics")
            if isinstance(topics, list) and topics:
                parts.append(f"话题:{'/'.join(str(item) for item in topics[:5])}")

        return " ".join(parts)
