from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.utils.time_utils import format_datetime


SOURCE_TYPE_TO_PLATFORM = {
    "xianyu": "xianyu",
    "xhs": "xiaohongshu",
}

SOURCE_TYPE_TO_RECORD_TYPE = {
    "xianyu": "listing",
    "xhs": "note",
}

ACTIVE_ANALYSIS_STATUSES = ("pending", "running")


class AnalysisStore:
    """黑话字典与黑话研判专用存储层。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self._ensure_tables()

    def list_keyword_categories(self) -> list[dict[str, Any]]:
        cursor = self.connection.cursor()
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
            item = {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "description": str(row["description"] or ""),
                "category_id": int(row["category_id"]),
                "sort_order": int(row["sort_order"] or 0),
                "keywords": [],
                "created_at": str(row["created_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
            subcategories[item["id"]] = item
            category = categories.get(item["category_id"])
            if category is not None:
                category["subcategories"].append(item)

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
                category["keywords"].append(keyword)
            subcategory = subcategories.get(keyword["subcategory_id"])
            if subcategory is not None:
                subcategory["keywords"].append(keyword)

        return list(categories.values())

    def create_keyword_category(self, *, name: str, description: str, sort_order: int) -> dict[str, Any]:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("分类名称不能为空")

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM keyword_categories WHERE name = ?", (normalized_name,))
        if cursor.fetchone() is not None:
            cursor.close()
            raise ValueError(f"分类名称 '{normalized_name}' 已存在")

        timestamp = format_datetime(None)
        cursor.execute(
            """
            INSERT INTO keyword_categories (name, description, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (normalized_name, str(description or "").strip(), int(sort_order), timestamp, timestamp),
        )
        category_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO keyword_subcategories (category_id, name, description, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (category_id, "未分类", "系统自动创建的默认二级分类", 0, timestamp, timestamp),
        )
        self.connection.commit()
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
                cursor = self.connection.cursor()
                cursor.execute("SELECT id FROM keyword_categories WHERE name = ? AND id != ?", (name, category_id))
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
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM keyword_categories WHERE id = ?", (category_id,))
        self.connection.commit()
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

        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id
            FROM keyword_subcategories
            WHERE category_id = ? AND name = ?
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
            VALUES (?, ?, ?, ?, ?, ?)
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
        self.connection.commit()
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
                cursor = self.connection.cursor()
                cursor.execute(
                    """
                    SELECT id
                    FROM keyword_subcategories
                    WHERE category_id = ? AND name = ? AND id != ?
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
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM keyword_subcategories WHERE id = ?", (subcategory_id,))
        self.connection.commit()
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

        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id
            FROM keywords
            WHERE subcategory_id = ? AND keyword = ?
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
            VALUES (?, ?, ?, ?, ?, ?, ?)
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
        self.connection.commit()
        cursor.close()
        return self._require_keyword(keyword_id)

    def update_keyword(self, keyword_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._require_keyword(keyword_id)
        target_subcategory_id = int(payload.get("subcategory_id") or current["subcategory_id"])
        subcategory = self._require_subcategory(target_subcategory_id)

        normalized_keyword = str(payload.get("keyword") or current["keyword"]).strip()
        if not normalized_keyword:
            raise ValueError("黑话词条不能为空")
        normalized_meaning = str(payload.get("meaning") if "meaning" in payload else current["meaning"]).strip()
        if not normalized_meaning:
            normalized_meaning = normalized_keyword

        if normalized_keyword != current["keyword"] or target_subcategory_id != current["subcategory_id"]:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                SELECT id
                FROM keywords
                WHERE subcategory_id = ? AND keyword = ? AND id != ?
                """,
                (target_subcategory_id, normalized_keyword, keyword_id),
            )
            if cursor.fetchone() is not None:
                cursor.close()
                raise ValueError(f"黑话词条 '{normalized_keyword}' 已存在")
            cursor.close()

        updates: dict[str, Any] = {
            "category_id": int(subcategory["category_id"]),
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
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
        self.connection.commit()
        cursor.close()

    def get_keyword(self, keyword_id: int) -> dict[str, Any] | None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                keywords.*,
                keyword_categories.name AS category_name,
                keyword_subcategories.name AS subcategory_name
            FROM keywords
            LEFT JOIN keyword_categories ON keyword_categories.id = keywords.category_id
            LEFT JOIN keyword_subcategories ON keyword_subcategories.id = keywords.subcategory_id
            WHERE keywords.id = ?
            """,
            (keyword_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return self._row_to_keyword(row) if row is not None else None

    def recover_interrupted_jargon_tasks(self) -> int:
        placeholders = ", ".join("?" for _ in ACTIVE_ANALYSIS_STATUSES)
        cursor = self.connection.cursor()
        cursor.execute(
            f"""
            UPDATE jargon_analysis_tasks
            SET status = 'failed',
                error_message = CASE
                    WHEN COALESCE(error_message, '') = '' THEN '本地服务重启，黑话研判任务已中断。'
                    ELSE error_message
                END,
                completed_at = COALESCE(completed_at, ?),
                updated_at = ?
            WHERE status IN ({placeholders})
            """,
            (format_datetime(None), format_datetime(None), *ACTIVE_ANALYSIS_STATUSES),
        )
        changed = int(cursor.rowcount or 0)
        self.connection.commit()
        cursor.close()
        return changed

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
        cursor = self.connection.cursor()
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        self.connection.commit()
        cursor.close()
        return self.get_jargon_analysis_task(task_id) or {}

    def count_jargon_analysis_tasks(self) -> int:
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM jargon_analysis_tasks")
        row = cursor.fetchone()
        cursor.close()
        return int(row["total"] or 0) if row is not None else 0

    def list_jargon_analysis_tasks(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT *
            FROM jargon_analysis_tasks
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_jargon_task(row) for row in rows]

    def get_jargon_analysis_task(self, task_id: int) -> dict[str, Any] | None:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM jargon_analysis_tasks WHERE id = ?", (task_id,))
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

        cursor = self.connection.cursor()
        cursor.executemany(
            """
            INSERT INTO jargon_analysis_results (
                task_id,
                source_type,
                source_record_id,
                is_match,
                confidence,
                reason,
                raw_response_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id, source_record_id) DO UPDATE SET
                source_type = excluded.source_type,
                is_match = excluded.is_match,
                confidence = excluded.confidence,
                reason = excluded.reason,
                raw_response_json = excluded.raw_response_json,
                updated_at = excluded.updated_at
            """,
            rows,
        )
        self.connection.commit()
        cursor.close()

    def get_jargon_analysis_results(self, task_id: int) -> list[dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT *
            FROM jargon_analysis_results
            WHERE task_id = ?
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

        placeholders = ", ".join("?" for _ in record_ids)
        cursor = self.connection.cursor()
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
            WHERE jargon_analysis_results.source_type = ?
              AND jargon_analysis_results.source_record_id IN ({placeholders})
              AND jargon_analysis_tasks.status = 'completed'
            ORDER BY
                jargon_analysis_results.source_record_id ASC,
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
            matched_map[record_id] = sorted(
                deduplicated.values(),
                key=lambda item: float(item["confidence"]),
                reverse=True,
            )

        return matched_map, analyzed_ids

    def get_record_match_map(self, *, source_type: str, record_ids: list[int]) -> tuple[dict[int, list[dict[str, Any]]], set[int]]:
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
        cursor = self.connection.cursor()
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
        cursor = self.connection.cursor()
        cursor.execute(
            f"""
            SELECT *
            FROM collected_records
            {where_sql}
            ORDER BY local_run_id DESC, item_index ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_collected_record(row) for row in rows]

    def list_analysis_sources(self) -> list[dict[str, Any]]:
        cursor = self.connection.cursor()
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
            ORDER BY COALESCE(NULLIF(task_runs.created_at, ''), NULLIF(task_runs.requested_at, ''), task_runs.id) DESC, task_runs.id DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()

        items: list[dict[str, Any]] = []
        for row in rows:
            run = self._row_to_run_summary(row)
            run["platform"] = str(row["collected_platform"] or run["platform"])
            run["record_count"] = int(row["record_count"] or 0)
            items.append(run)
        return items

    def get_analysis_source_snapshot(self, *, source_type: str, source_task_id: int) -> dict[str, Any] | None:
        platform, record_type = self._resolve_source_filters(source_type)
        run = self.get_run(source_task_id)
        if run is None:
            return None

        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) AS record_count
            FROM collected_records
            WHERE local_run_id = ?
              AND platform = ?
              AND record_type = ?
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
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT *
            FROM collected_records
            WHERE local_run_id = ?
              AND platform = ?
              AND record_type = ?
            ORDER BY item_index ASC, id ASC
            """,
            (source_task_id, platform, record_type),
        )
        rows = cursor.fetchall()
        cursor.close()

        items: list[dict[str, Any]] = []
        for row in rows:
            record = self._row_to_collected_record(row)
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
        cursor = self.connection.cursor()
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
        cursor = self.connection.cursor()
        cursor.execute(
            f"""
            SELECT *
            FROM collected_records
            {where_sql}
            ORDER BY local_run_id DESC, item_index ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_collected_record(row) for row in rows]

    def get_collected_records_by_ids(self, record_ids: list[int]) -> list[dict[str, Any]]:
        if not record_ids:
            return []
        placeholders = ", ".join("?" for _ in record_ids)
        cursor = self.connection.cursor()
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
        return [self._row_to_collected_record(row) for row in rows]

    def get_collected_record(self, record_id: int) -> dict[str, Any] | None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT *
            FROM collected_records
            WHERE id = ?
            """,
            (record_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return self._row_to_collected_record(row) if row is not None else None

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM task_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        cursor.close()
        return self._row_to_run_summary(row) if row is not None else None

    def close(self) -> None:
        self.connection.close()

    def _ensure_tables(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS keyword_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS keyword_subcategories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                UNIQUE(category_id, name),
                FOREIGN KEY(category_id) REFERENCES keyword_categories(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                subcategory_id INTEGER NOT NULL,
                keyword TEXT NOT NULL,
                meaning TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                UNIQUE(subcategory_id, keyword),
                FOREIGN KEY(category_id) REFERENCES keyword_categories(id) ON DELETE CASCADE,
                FOREIGN KEY(subcategory_id) REFERENCES keyword_subcategories(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jargon_analysis_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_task_id INTEGER NOT NULL,
                source_task_name TEXT NOT NULL DEFAULT '',
                keyword_id INTEGER NOT NULL,
                keyword_name_snapshot TEXT NOT NULL DEFAULT '',
                keyword_meaning_snapshot TEXT NOT NULL DEFAULT '',
                category_name_snapshot TEXT NOT NULL DEFAULT '',
                subcategory_name_snapshot TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                total_records INTEGER NOT NULL DEFAULT 0,
                processed_records INTEGER NOT NULL DEFAULT 0,
                matched_records INTEGER NOT NULL DEFAULT 0,
                error_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                started_at TEXT NULL,
                completed_at TEXT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jargon_analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                source_record_id INTEGER NOT NULL,
                is_match INTEGER NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                raw_response_json TEXT NULL,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                UNIQUE(task_id, source_record_id),
                FOREIGN KEY(task_id) REFERENCES jargon_analysis_tasks(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_category ON keywords(category_id, subcategory_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jargon_tasks_source ON jargon_analysis_tasks(source_type, source_task_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jargon_results_source ON jargon_analysis_results(source_type, source_record_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jargon_results_task ON jargon_analysis_results(task_id)")
        self.connection.commit()
        cursor.close()

    def _update_row(self, table_name: str, row_id: int, updates: dict[str, Any]) -> None:
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = [self._dump_json_if_needed(value) for value in updates.values()]
        cursor = self.connection.cursor()
        cursor.execute(f"UPDATE {table_name} SET {assignments} WHERE id = ?", (*values, row_id))
        self.connection.commit()
        cursor.close()

    def _require_category(self, category_id: int) -> dict[str, Any]:
        for item in self.list_keyword_categories():
            if int(item["id"]) == category_id:
                return item
        raise KeyError(f"分类不存在：{category_id}")

    def _require_subcategory(self, subcategory_id: int) -> dict[str, Any]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM keyword_subcategories WHERE id = ?", (subcategory_id,))
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
        conditions = ["platform = ?", "record_type = ?"]
        params: list[Any] = [platform, record_type]

        if task_id is not None:
            conditions.append("local_run_id = ?")
            params.append(task_id)

        if search:
            like_pattern = f"%{str(search).strip()}%"
            conditions.append("(COALESCE(title, '') LIKE ? OR COALESCE(content_text, '') LIKE ?)")
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
                      AND jargon_analysis_results.source_type = ?
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
        conditions = ["collected_records.platform = ?", "collected_records.record_type = ?"]
        params: list[Any] = [platform, record_type]

        if task_id is not None:
            conditions.append("collected_records.local_run_id = ?")
            params.append(task_id)

        if search:
            like_pattern = f"%{str(search).strip()}%"
            conditions.append("(COALESCE(collected_records.title, '') LIKE ? OR COALESCE(collected_records.content_text, '') LIKE ?)")
            params.extend([like_pattern, like_pattern])

        match_conditions = [
            "jargon_analysis_results.source_record_id = collected_records.id",
            "jargon_analysis_results.source_type = ?",
            "jargon_analysis_results.is_match = 1",
            "jargon_analysis_tasks.status = 'completed'",
        ]
        match_params: list[Any] = [source_type]

        if keyword_id is not None:
            match_conditions.append("jargon_analysis_tasks.keyword_id = ?")
            match_params.append(keyword_id)

        if category_id is not None:
            match_conditions.append("keywords.category_id = ?")
            match_params.append(category_id)

        if subcategory_id is not None:
            match_conditions.append("keywords.subcategory_id = ?")
            match_params.append(subcategory_id)

        if min_confidence is not None:
            match_conditions.append("jargon_analysis_results.confidence >= ?")
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

    @staticmethod
    def _row_to_run_summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "task_name": str(row["task_name"]),
            "adapter": str(row["adapter"] or ""),
            "platform": str(row["platform"] or ""),
            "package_name": str(row["package_name"] or ""),
            "run_mode": str(row["run_mode"] or "normal"),
            "status": str(row["status"]),
            "device_serial": str(row["device_serial"] or ""),
            "requested_at": str(row["requested_at"] or ""),
            "started_at": str(row["started_at"] or ""),
            "finished_at": str(row["finished_at"] or ""),
            "artifact_dir": str(row["artifact_dir"] or ""),
            "log_path": str(row["log_path"] or ""),
            "config": AnalysisStore._load_json(row["config_json"]) or {},
            "result": AnalysisStore._load_json(row["result_json"]) or {},
            "error_message": str(row["error_message"] or ""),
            "mysql_run_id": int(row["mysql_run_id"]) if row["mysql_run_id"] is not None else None,
            "items_count": int(row["items_count"] or 0),
            "comment_count": int(row["comment_count"] or 0),
            "cancel_requested": bool(int(row["cancel_requested"] or 0)),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    @staticmethod
    def _row_to_collected_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "local_run_id": int(row["local_run_id"]),
            "item_index": int(row["item_index"]),
            "platform": str(row["platform"]),
            "record_type": str(row["record_type"]),
            "keyword": str(row["keyword"] or ""),
            "title": str(row["title"] or ""),
            "content_text": str(row["content_text"] or ""),
            "author_name": str(row["author_name"] or ""),
            "author_id": str(row["author_id"] or ""),
            "location_text": str(row["location_text"] or ""),
            "ip_location": str(row["ip_location"] or ""),
            "published_text": str(row["published_text"] or ""),
            "metrics": AnalysisStore._load_json(row["metrics_json"]) or {},
            "extra": AnalysisStore._load_json(row["extra_json"]) or {},
            "raw_visible_texts": AnalysisStore._load_json(row["raw_visible_texts_json"]) or [],
            "created_at": str(row["created_at"] or ""),
        }

    @staticmethod
    def _row_to_keyword(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "keyword": str(row["keyword"]),
            "meaning": str(row["meaning"] or ""),
            "category_id": int(row["category_id"]),
            "subcategory_id": int(row["subcategory_id"]),
            "category_name": str(row["category_name"] or ""),
            "subcategory_name": str(row["subcategory_name"] or ""),
            "sort_order": int(row["sort_order"] or 0),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    @staticmethod
    def _row_to_jargon_task(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "source_type": str(row["source_type"]),
            "source_task_id": int(row["source_task_id"]),
            "source_task_name": str(row["source_task_name"] or ""),
            "keyword_id": int(row["keyword_id"]),
            "keyword_name": str(row["keyword_name_snapshot"] or ""),
            "keyword_meaning": str(row["keyword_meaning_snapshot"] or ""),
            "category_name": str(row["category_name_snapshot"] or ""),
            "subcategory_name": str(row["subcategory_name_snapshot"] or ""),
            "status": str(row["status"]),
            "total_records": int(row["total_records"] or 0),
            "processed_records": int(row["processed_records"] or 0),
            "matched_records": int(row["matched_records"] or 0),
            "error_message": str(row["error_message"] or ""),
            "created_at": str(row["created_at"] or ""),
            "started_at": str(row["started_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    @staticmethod
    def _row_to_jargon_result(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "task_id": int(row["task_id"]),
            "source_type": str(row["source_type"]),
            "source_record_id": int(row["source_record_id"]),
            "is_match": bool(int(row["is_match"] or 0)),
            "confidence": float(row["confidence"] or 0),
            "reason": str(row["reason"] or ""),
            "raw_response": AnalysisStore._load_json(row["raw_response_json"]) or {},
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
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
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
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

    @staticmethod
    def _dump_json_if_needed(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value

    @staticmethod
    def _load_json(raw_value: Any) -> Any:
        if raw_value in (None, ""):
            return None
        if isinstance(raw_value, (dict, list)):
            return raw_value
        try:
            return json.loads(str(raw_value))
        except json.JSONDecodeError:
            return None
