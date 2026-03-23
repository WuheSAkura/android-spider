from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from src.models.collected_record import CollectedRecord
from src.utils.time_utils import format_datetime


ACTIVE_RUN_STATUSES = ("pending", "running", "cancel_requested")
FINAL_RUN_STATUSES = ("success", "failed", "cancelled")


class SQLiteStore:
    """本地 SQLite 主数据源，负责设置、任务、结果与取消状态。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._ensure_tables()

    def get_setting(self, key: str) -> str | None:
        cursor = self.connection.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        cursor.close()
        return str(row["value"]) if row is not None else None

    def get_all_settings(self) -> dict[str, str]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT key, value FROM settings ORDER BY key")
        rows = cursor.fetchall()
        cursor.close()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def set_setting(self, key: str, value: str) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, format_datetime(None)),
        )
        self.connection.commit()
        cursor.close()

    def create_run(
        self,
        *,
        task_name: str,
        adapter: str,
        platform: str,
        package_name: str,
        run_mode: str,
        config_json: dict[str, Any],
    ) -> int:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO task_runs (
                task_name, adapter, platform, package_name, run_mode, status,
                requested_at, config_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_name,
                adapter,
                platform,
                package_name,
                run_mode,
                "pending",
                format_datetime(None),
                json.dumps(config_json, ensure_ascii=False),
                format_datetime(None),
                format_datetime(None),
            ),
        )
        run_id = int(cursor.lastrowid)
        self.connection.commit()
        cursor.close()
        return run_id

    def mark_run_started(self, run_id: int, *, started_at: str, log_path: str) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE task_runs
            SET status = ?,
                started_at = ?,
                log_path = ?,
                updated_at = ?
            WHERE id = ?
            """,
            ("running", started_at, log_path, format_datetime(None), run_id),
        )
        self.connection.commit()
        cursor.close()

    def update_run_device(self, run_id: int, device_serial: str) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE task_runs
            SET device_serial = ?, updated_at = ?
            WHERE id = ?
            """,
            (device_serial, format_datetime(None), run_id),
        )
        self.connection.commit()
        cursor.close()

    def update_run_status(self, run_id: int, status: str) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE task_runs
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, format_datetime(None), run_id),
        )
        self.connection.commit()
        cursor.close()

    def request_cancel(self, run_id: int) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE task_runs
            SET cancel_requested = 1,
                status = CASE
                    WHEN status IN ('pending', 'running') THEN 'cancel_requested'
                    ELSE status
                END,
                updated_at = ?
            WHERE id = ?
            """,
            (format_datetime(None), run_id),
        )
        self.connection.commit()
        cursor.close()

    def is_cancel_requested(self, run_id: int) -> bool:
        cursor = self.connection.cursor()
        cursor.execute("SELECT cancel_requested FROM task_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        cursor.close()
        return bool(row is not None and int(row["cancel_requested"]) == 1)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        finished_at: str,
        artifact_dir: str,
        result: dict[str, Any] | None,
        error_message: str | None,
        mysql_run_id: int | None,
        device_serial: str,
        items_count: int,
        comment_count: int,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE task_runs
            SET status = ?,
                finished_at = ?,
                artifact_dir = ?,
                result_json = ?,
                error_message = ?,
                mysql_run_id = ?,
                device_serial = ?,
                items_count = ?,
                comment_count = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                finished_at,
                artifact_dir,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error_message,
                mysql_run_id,
                device_serial,
                items_count,
                comment_count,
                format_datetime(None),
                run_id,
            ),
        )
        self.connection.commit()
        cursor.close()

    def replace_collected_records(self, run_id: int, records: Iterable[CollectedRecord]) -> None:
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM collected_records WHERE local_run_id = ?", (run_id,))

        rows = []
        for index, record in enumerate(records, start=1):
            rows.append(
                (
                    run_id,
                    index,
                    record.platform,
                    record.record_type,
                    record.keyword or None,
                    record.title or None,
                    record.content_text or None,
                    record.author_name or None,
                    record.author_id or None,
                    record.location_text or None,
                    record.ip_location or None,
                    record.published_text or None,
                    json.dumps(record.metrics, ensure_ascii=False),
                    json.dumps(record.extra, ensure_ascii=False),
                    json.dumps(record.raw_visible_texts, ensure_ascii=False),
                    format_datetime(None),
                )
            )

        if rows:
            cursor.executemany(
                """
                INSERT INTO collected_records (
                    local_run_id, item_index, platform, record_type, keyword, title, content_text,
                    author_name, author_id, location_text, ip_location, published_text,
                    metrics_json, extra_json, raw_visible_texts_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        self.connection.commit()
        cursor.close()

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT *
            FROM task_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_run_summary(row) for row in rows]

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM task_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        cursor.close()
        return self._row_to_run_summary(row) if row is not None else None

    def get_run_records(self, run_id: int) -> list[dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT *
            FROM collected_records
            WHERE local_run_id = ?
            ORDER BY item_index ASC
            """,
            (run_id,),
        )
        rows = cursor.fetchall()
        cursor.close()

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
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
                    "metrics": self._load_json(row["metrics_json"]),
                    "extra": self._load_json(row["extra_json"]),
                    "raw_visible_texts": self._load_json(row["raw_visible_texts_json"]),
                    "created_at": str(row["created_at"]),
                }
            )
        return results

    def get_active_run(self) -> dict[str, Any] | None:
        placeholders = ", ".join("?" for _ in ACTIVE_RUN_STATUSES)
        cursor = self.connection.cursor()
        cursor.execute(
            f"""
            SELECT *
            FROM task_runs
            WHERE status IN ({placeholders})
            ORDER BY id DESC
            LIMIT 1
            """,
            ACTIVE_RUN_STATUSES,
        )
        row = cursor.fetchone()
        cursor.close()
        return self._row_to_run_summary(row) if row is not None else None

    def recover_interrupted_runs(self) -> int:
        placeholders = ", ".join("?" for _ in ACTIVE_RUN_STATUSES)
        cursor = self.connection.cursor()
        cursor.execute(
            f"""
            UPDATE task_runs
            SET status = 'failed',
                error_message = COALESCE(error_message, '本地服务重启，运行状态已中断。'),
                finished_at = COALESCE(finished_at, ?),
                updated_at = ?
            WHERE status IN ({placeholders})
            """,
            (format_datetime(None), format_datetime(None), *ACTIVE_RUN_STATUSES),
        )
        changed = int(cursor.rowcount or 0)
        self.connection.commit()
        cursor.close()
        return changed

    def record_failure(
        self,
        *,
        task_name: str,
        device_serial: str,
        started_at: str,
        finished_at: str,
        artifact_dir: str,
        error_message: str,
        traceback_text: str,
    ) -> None:
        run_id = self.create_run(
            task_name=task_name,
            adapter="legacy_failure",
            platform="unknown",
            package_name="",
            run_mode="normal",
            config_json={"traceback_text": traceback_text},
        )
        self.mark_run_started(run_id, started_at=started_at, log_path="")
        self.finish_run(
            run_id,
            status="failed",
            finished_at=finished_at,
            artifact_dir=artifact_dir,
            result=None,
            error_message=error_message,
            mysql_run_id=None,
            device_serial=device_serial,
            items_count=0,
            comment_count=0,
        )

    def close(self) -> None:
        self.connection.close()

    def _ensure_tables(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT NOT NULL,
                adapter TEXT NOT NULL DEFAULT '',
                platform TEXT NOT NULL DEFAULT '',
                package_name TEXT NOT NULL DEFAULT '',
                run_mode TEXT NOT NULL DEFAULT 'normal',
                status TEXT NOT NULL,
                device_serial TEXT NOT NULL DEFAULT '',
                requested_at TEXT NOT NULL DEFAULT '',
                started_at TEXT NULL,
                finished_at TEXT NULL,
                artifact_dir TEXT NOT NULL DEFAULT '',
                log_path TEXT NOT NULL DEFAULT '',
                config_json TEXT NULL,
                result_json TEXT NULL,
                error_message TEXT NULL,
                mysql_run_id INTEGER NULL,
                items_count INTEGER NOT NULL DEFAULT 0,
                comment_count INTEGER NOT NULL DEFAULT 0,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS collected_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                local_run_id INTEGER NOT NULL,
                item_index INTEGER NOT NULL,
                platform TEXT NOT NULL,
                record_type TEXT NOT NULL,
                keyword TEXT NULL,
                title TEXT NULL,
                content_text TEXT NULL,
                author_name TEXT NULL,
                author_id TEXT NULL,
                location_text TEXT NULL,
                ip_location TEXT NULL,
                published_text TEXT NULL,
                metrics_json TEXT NULL,
                extra_json TEXT NULL,
                raw_visible_texts_json TEXT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(local_run_id) REFERENCES task_runs(id)
            )
            """
        )
        self.connection.commit()

        self._ensure_column("task_runs", "adapter", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("task_runs", "platform", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("task_runs", "package_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("task_runs", "run_mode", "TEXT NOT NULL DEFAULT 'normal'")
        self._ensure_column("task_runs", "requested_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("task_runs", "log_path", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("task_runs", "config_json", "TEXT NULL")
        self._ensure_column("task_runs", "result_json", "TEXT NULL")
        self._ensure_column("task_runs", "mysql_run_id", "INTEGER NULL")
        self._ensure_column("task_runs", "items_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("task_runs", "comment_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("task_runs", "cancel_requested", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("task_runs", "created_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("task_runs", "updated_at", "TEXT NOT NULL DEFAULT ''")

        cursor.close()

    def _ensure_column(self, table_name: str, column_name: str, column_type_sql: str) -> None:
        cursor = self.connection.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = {str(row["name"]) for row in cursor.fetchall()}
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type_sql}")
            self.connection.commit()
        cursor.close()

    def _row_to_run_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        result_json = self._load_json(row["result_json"])
        config_json = self._load_json(row["config_json"])
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
            "config": config_json if isinstance(config_json, dict) else {},
            "result": result_json if isinstance(result_json, dict) else {},
            "error_message": str(row["error_message"] or ""),
            "mysql_run_id": int(row["mysql_run_id"]) if row["mysql_run_id"] is not None else None,
            "items_count": int(row["items_count"] or 0),
            "comment_count": int(row["comment_count"] or 0),
            "cancel_requested": bool(int(row["cancel_requested"] or 0)),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

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
