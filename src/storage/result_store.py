from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Iterable
from urllib.error import URLError
from urllib.request import urlopen

from src.models.artifact_upload import ArtifactUploadRecord
from src.models.collected_record import CollectedRecord
from src.models.task_models import MySQLConfig, SSHTunnelConfig
from src.services.ssh_tunnel_service import SSHTunnelService
from src.utils.exceptions import DependencyError, DriverError, StorageError
from src.utils.time_utils import format_datetime

ACTIVE_RUN_STATUSES = ("pending", "running", "cancel_requested")

mysql: Any | None

try:
    import mysql.connector as mysql_connector
except ImportError:  # pragma: no cover - 依赖检查由 doctor 命令负责
    mysql = None
else:
    mysql = mysql_connector


class MySQLResultStore:
    """共享 MySQL 运行主库。"""

    _schema_ready_keys: set[str] = set()
    _schema_lock = threading.Lock()

    def __init__(
        self,
        config: MySQLConfig,
        logger: logging.Logger,
        *,
        ssh_config: SSHTunnelConfig | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.ssh_config = ssh_config or SSHTunnelConfig()
        self.connection = None
        self.ssh_tunnel: SSHTunnelService | None = None

    def connect(self) -> None:
        if mysql is None:
            raise DependencyError("缺少 mysql-connector-python 依赖，请先安装 requirements.txt。")
        self._start_tunnel_if_needed()
        try:
            self.connection = self._connect_database()
        except mysql.Error as exc:
            if getattr(exc, "errno", None) != 1049:
                raise
            self._ensure_database()
            self.connection = self._connect_database()
        self._ensure_schema_ready()
        self.logger.info("MySQL 已连接：%s:%s/%s", self._effective_host, self._effective_port, self.config.database)

    def create_run(
        self,
        task_name: str,
        device_serial: str,
        status: str,
        started_at: str,
        *,
        adapter: str = "",
        platform: str = "",
        package_name: str = "",
        run_mode: str = "normal",
        requested_at: str | None = None,
        config_json: dict[str, Any] | None = None,
    ) -> int:
        timestamp = format_datetime(None)
        cursor = self._cursor()
        cursor.execute(
            """
            INSERT INTO task_runs (
                task_name, adapter, platform, package_name, run_mode, status,
                device_serial, requested_at, started_at, config_json, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                task_name,
                adapter,
                platform,
                package_name,
                run_mode,
                status,
                device_serial,
                requested_at or started_at,
                started_at,
                self._dump_json(config_json),
                timestamp,
                timestamp,
            ),
        )
        run_id = int(cursor.lastrowid)
        cursor.execute("UPDATE task_runs SET mysql_run_id = %s WHERE id = %s", (run_id, run_id))
        cursor.close()
        return run_id

    def mark_run_started(self, run_id: int, *, started_at: str, log_path: str) -> None:
        self._execute(
            """
            UPDATE task_runs
            SET status = %s,
                started_at = %s,
                log_path = %s,
                updated_at = %s
            WHERE id = %s
            """,
            ("running", started_at, log_path, format_datetime(None), run_id),
        )

    def update_run_device(self, run_id: int, device_serial: str) -> None:
        self._execute(
            """
            UPDATE task_runs
            SET device_serial = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (device_serial, format_datetime(None), run_id),
        )

    def update_run_status(self, run_id: int, status: str) -> None:
        self._execute(
            """
            UPDATE task_runs
            SET status = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (status, format_datetime(None), run_id),
        )

    def request_cancel(self, run_id: int) -> None:
        self._execute(
            """
            UPDATE task_runs
            SET cancel_requested = 1,
                status = CASE
                    WHEN status IN ('pending', 'running') THEN 'cancel_requested'
                    ELSE status
                END,
                updated_at = %s
            WHERE id = %s
            """,
            (format_datetime(None), run_id),
        )

    def is_cancel_requested(self, run_id: int) -> bool:
        cursor = self._cursor(dictionary=True)
        cursor.execute("SELECT cancel_requested FROM task_runs WHERE id = %s", (run_id,))
        row = cursor.fetchone()
        cursor.close()
        return bool(row is not None and int(row["cancel_requested"] or 0) == 1)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        finished_at: str,
        artifact_dir: str,
        error_message: str | None,
        result: dict[str, Any] | None = None,
        mysql_run_id: int | None = None,
        device_serial: str | None = None,
        items_count: int = 0,
        comment_count: int = 0,
    ) -> None:
        self._execute(
            """
            UPDATE task_runs
            SET status = %s,
                finished_at = %s,
                artifact_dir = %s,
                result_json = %s,
                error_message = %s,
                mysql_run_id = %s,
                device_serial = %s,
                items_count = %s,
                comment_count = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (
                status,
                finished_at,
                artifact_dir,
                self._dump_json(result),
                error_message,
                mysql_run_id or run_id,
                device_serial or "",
                items_count,
                comment_count,
                format_datetime(None),
                run_id,
            ),
        )

    def save_collected_items(self, run_id: int, page_name: str, texts: Iterable[str]) -> None:
        rows = [(run_id, page_name, text, format_datetime(None)) for text in texts if text.strip()]
        if not rows:
            return
        cursor = self._cursor()
        cursor.executemany(
            """
            INSERT INTO collected_items (run_id, page_name, text_content, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            rows,
        )
        cursor.close()

    def replace_collected_records(self, run_id: int, records: Iterable[CollectedRecord]) -> None:
        cursor = self._cursor()
        cursor.execute("DELETE FROM collected_records WHERE local_run_id = %s OR run_id = %s", (run_id, run_id))
        rows = []
        for index, record in enumerate(records, start=1):
            rows.append(
                (
                    run_id,
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
                    self._dump_json(record.metrics),
                    self._dump_json(record.extra),
                    self._dump_json(record.raw_visible_texts),
                    format_datetime(None),
                )
            )
        if rows:
            cursor.executemany(
                """
                INSERT INTO collected_records (
                    run_id, local_run_id, item_index, platform, record_type, keyword, title, content_text,
                    author_name, author_id, location_text, ip_location, published_text,
                    metrics_json, extra_json, raw_visible_texts_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        cursor.close()

    def save_collected_records(self, run_id: int, records: Iterable[CollectedRecord]) -> None:
        self.replace_collected_records(run_id, records)

    def save_artifact_uploads(self, run_id: int, uploads: Iterable[ArtifactUploadRecord]) -> None:
        rows = [
            (
                run_id,
                item.relative_path,
                str(item.local_path),
                item.object_path,
                item.public_url,
                item.content_type,
                item.file_size,
                format_datetime(None),
            )
            for item in uploads
        ]
        if not rows:
            return
        cursor = self._cursor()
        cursor.execute("DELETE FROM run_artifacts WHERE run_id = %s", (run_id,))
        cursor.executemany(
            """
            INSERT INTO run_artifacts (
                run_id, file_name, local_path, object_path, public_url, content_type, file_size, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        cursor.close()

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM task_runs
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_run_summary(row) for row in rows]

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        cursor = self._cursor(dictionary=True)
        cursor.execute("SELECT * FROM task_runs WHERE id = %s", (run_id,))
        row = cursor.fetchone()
        cursor.close()
        return self._row_to_run_summary(row) if row is not None else None

    def get_run_records(self, run_id: int) -> list[dict[str, Any]]:
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM collected_records
            WHERE local_run_id = %s
            ORDER BY item_index ASC, id ASC
            """,
            (run_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_collected_record(row) for row in rows]

    def list_active_runs(self, limit: int | None = None) -> list[dict[str, Any]]:
        placeholders = ", ".join(["%s" for _ in ACTIVE_RUN_STATUSES])
        sql = f"""
            SELECT *
            FROM task_runs
            WHERE status IN ({placeholders})
            ORDER BY id DESC
        """
        params: list[Any] = list(ACTIVE_RUN_STATUSES)
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        cursor = self._cursor(dictionary=True)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        return [self._row_to_run_summary(row) for row in rows]

    def recover_interrupted_runs(self) -> int:
        return 0

    def get_run_artifacts(self, run_id: int) -> list[dict[str, Any]]:
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM run_artifacts
            WHERE run_id = %s
            ORDER BY file_name ASC, id ASC
            """,
            (run_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        if rows:
            return [
                {
                    "name": str(row["file_name"] or ""),
                    "path": str(row["public_url"] or row["local_path"] or ""),
                    "is_dir": False,
                    "size": int(row["file_size"] or 0),
                    "kind": self._detect_artifact_kind(str(row["file_name"] or "")),
                }
                for row in rows
            ]

        run = self.get_run(run_id)
        artifact_dir_value = str(run.get("artifact_dir") or "") if run is not None else ""
        if not artifact_dir_value:
            return []
        artifact_dir = Path(artifact_dir_value)
        if not artifact_dir.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(artifact_dir.iterdir(), key=lambda item: item.name.lower()):
            items.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "is_dir": path.is_dir(),
                    "size": path.stat().st_size if path.is_file() else 0,
                    "kind": self._detect_artifact_kind(path.name),
                }
            )
        return items

    def get_run_logs(self, run_id: int, tail: int = 200) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            return {"path": "", "content": "", "line_count": 0}

        log_path_value = str(run.get("log_path") or "")
        if log_path_value:
            log_path = Path(log_path_value)
            if log_path.exists():
                content = log_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                tail_lines = lines[-tail:] if tail > 0 else lines
                return {"path": str(log_path), "content": "\n".join(tail_lines), "line_count": len(lines)}

        cursor = self._cursor(dictionary=True)
        cursor.execute(
            """
            SELECT public_url, file_name
            FROM run_artifacts
            WHERE run_id = %s
              AND (file_name = 'run.log' OR file_name LIKE %s)
            ORDER BY id ASC
            LIMIT 1
            """,
            (run_id, "%/run.log"),
        )
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            return {"path": "", "content": "", "line_count": 0}

        url = str(row["public_url"] or "")
        if not url:
            return {"path": "", "content": "", "line_count": 0}

        try:
            with urlopen(url, timeout=10) as response:
                content = response.read().decode("utf-8", errors="ignore")
        except (URLError, TimeoutError, OSError):
            return {"path": url, "content": "", "line_count": 0}

        lines = content.splitlines()
        tail_lines = lines[-tail:] if tail > 0 else lines
        return {"path": url, "content": "\n".join(tail_lines), "line_count": len(lines)}

    def upsert_run_row(self, row: dict[str, Any]) -> None:
        cursor = self._cursor()
        cursor.execute(
            """
            INSERT INTO task_runs (
                id, task_name, adapter, platform, package_name, run_mode, status,
                device_serial, requested_at, started_at, finished_at, artifact_dir, log_path,
                config_json, result_json, error_message, mysql_run_id, items_count,
                comment_count, cancel_requested, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                task_name = VALUES(task_name),
                adapter = VALUES(adapter),
                platform = VALUES(platform),
                package_name = VALUES(package_name),
                run_mode = VALUES(run_mode),
                status = VALUES(status),
                device_serial = VALUES(device_serial),
                requested_at = VALUES(requested_at),
                started_at = VALUES(started_at),
                finished_at = VALUES(finished_at),
                artifact_dir = VALUES(artifact_dir),
                log_path = VALUES(log_path),
                config_json = VALUES(config_json),
                result_json = VALUES(result_json),
                error_message = VALUES(error_message),
                mysql_run_id = VALUES(mysql_run_id),
                items_count = VALUES(items_count),
                comment_count = VALUES(comment_count),
                cancel_requested = VALUES(cancel_requested),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at)
            """,
            (
                int(row["id"]),
                str(row.get("task_name") or ""),
                str(row.get("adapter") or ""),
                str(row.get("platform") or ""),
                str(row.get("package_name") or ""),
                str(row.get("run_mode") or "normal"),
                str(row.get("status") or "pending"),
                str(row.get("device_serial") or ""),
                str(row.get("requested_at") or ""),
                row.get("started_at"),
                row.get("finished_at"),
                str(row.get("artifact_dir") or ""),
                str(row.get("log_path") or ""),
                self._dump_json(row.get("config")),
                self._dump_json(row.get("result")),
                row.get("error_message"),
                int(row.get("mysql_run_id") or row["id"]),
                int(row.get("items_count") or 0),
                int(row.get("comment_count") or 0),
                1 if bool(row.get("cancel_requested")) else 0,
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
            ),
        )
        cursor.close()

    def upsert_collected_record_row(self, row: dict[str, Any]) -> None:
        cursor = self._cursor()
        cursor.execute(
            """
            INSERT INTO collected_records (
                id, run_id, local_run_id, item_index, platform, record_type, keyword, title, content_text,
                author_name, author_id, location_text, ip_location, published_text,
                metrics_json, extra_json, raw_visible_texts_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                run_id = VALUES(run_id),
                local_run_id = VALUES(local_run_id),
                item_index = VALUES(item_index),
                platform = VALUES(platform),
                record_type = VALUES(record_type),
                keyword = VALUES(keyword),
                title = VALUES(title),
                content_text = VALUES(content_text),
                author_name = VALUES(author_name),
                author_id = VALUES(author_id),
                location_text = VALUES(location_text),
                ip_location = VALUES(ip_location),
                published_text = VALUES(published_text),
                metrics_json = VALUES(metrics_json),
                extra_json = VALUES(extra_json),
                raw_visible_texts_json = VALUES(raw_visible_texts_json),
                created_at = VALUES(created_at)
            """,
            (
                int(row["id"]),
                int(row.get("run_id") or row["local_run_id"]),
                int(row["local_run_id"]),
                int(row["item_index"]),
                str(row.get("platform") or ""),
                str(row.get("record_type") or ""),
                row.get("keyword"),
                row.get("title"),
                row.get("content_text"),
                row.get("author_name"),
                row.get("author_id"),
                row.get("location_text"),
                row.get("ip_location"),
                row.get("published_text"),
                self._dump_json(row.get("metrics")),
                self._dump_json(row.get("extra")),
                self._dump_json(row.get("raw_visible_texts")),
                str(row.get("created_at") or ""),
            ),
        )
        cursor.close()

    def upsert_artifact_row(self, row: dict[str, Any]) -> None:
        cursor = self._cursor()
        cursor.execute(
            """
            INSERT INTO run_artifacts (
                run_id, file_name, local_path, object_path, public_url, content_type, file_size, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                local_path = VALUES(local_path),
                object_path = VALUES(object_path),
                public_url = VALUES(public_url),
                content_type = VALUES(content_type),
                file_size = VALUES(file_size),
                created_at = VALUES(created_at)
            """,
            (
                int(row["run_id"]),
                str(row.get("file_name") or ""),
                str(row.get("local_path") or ""),
                str(row.get("object_path") or ""),
                str(row.get("public_url") or ""),
                str(row.get("content_type") or "application/octet-stream"),
                int(row.get("file_size") or 0),
                str(row.get("created_at") or ""),
            ),
        )
        cursor.close()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.ssh_tunnel is not None:
            self.ssh_tunnel.close()
            self.ssh_tunnel = None

    def _start_tunnel_if_needed(self) -> None:
        if not self.ssh_config.enabled:
            return
        if self.ssh_tunnel is not None:
            return
        self.ssh_tunnel = SSHTunnelService(self.ssh_config, self.logger)
        self.ssh_tunnel.start()

    @property
    def _effective_host(self) -> str:
        if self.ssh_tunnel is None:
            return self.config.host
        return "127.0.0.1"

    @property
    def _effective_port(self) -> int:
        if self.ssh_tunnel is None:
            return self.config.port
        return self.ssh_tunnel.local_port

    def _ensure_database(self) -> None:
        if mysql is None:
            raise DependencyError("缺少 mysql-connector-python 依赖，请先安装 requirements.txt。")
        try:
            server_connection = mysql.connect(
                host=self._effective_host,
                port=self._effective_port,
                user=self.config.user,
                password=self.config.password,
                autocommit=True,
            )
        except mysql.Error as exc:
            raise StorageError(f"MySQL 建库前连接失败：{exc}") from exc

        cursor = server_connection.cursor()
        try:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{self.config.database}` CHARACTER SET {self.config.charset} COLLATE {self.config.charset}_unicode_ci"
            )
        except mysql.Error as exc:
            raise StorageError(
                f"MySQL 数据库 `{self.config.database}` 不存在，且当前账号无权自动创建。请先在服务器上创建该数据库。"
            ) from exc
        finally:
            cursor.close()
            server_connection.close()

    def _ensure_schema_ready(self) -> None:
        cache_key = self._schema_cache_key()
        if cache_key in self._schema_ready_keys:
            return

        with self._schema_lock:
            if cache_key in self._schema_ready_keys:
                return
            self._ensure_tables()
            self._schema_ready_keys.add(cache_key)

    def _ensure_tables(self) -> None:
        cursor = self._cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                task_name VARCHAR(255) NOT NULL,
                adapter VARCHAR(128) NOT NULL DEFAULT '',
                platform VARCHAR(64) NOT NULL DEFAULT '',
                package_name VARCHAR(255) NOT NULL DEFAULT '',
                run_mode VARCHAR(32) NOT NULL DEFAULT 'normal',
                status VARCHAR(32) NOT NULL,
                device_serial VARCHAR(255) NOT NULL DEFAULT '',
                requested_at VARCHAR(32) NOT NULL DEFAULT '',
                started_at VARCHAR(32) NULL,
                finished_at VARCHAR(32) NULL,
                artifact_dir TEXT NULL,
                log_path TEXT NULL,
                config_json LONGTEXT NULL,
                result_json LONGTEXT NULL,
                error_message LONGTEXT NULL,
                mysql_run_id BIGINT NULL,
                items_count INT NOT NULL DEFAULT 0,
                comment_count INT NOT NULL DEFAULT 0,
                cancel_requested TINYINT(1) NOT NULL DEFAULT 0,
                created_at VARCHAR(32) NOT NULL DEFAULT '',
                updated_at VARCHAR(32) NOT NULL DEFAULT '',
                INDEX idx_task_runs_status (status),
                INDEX idx_task_runs_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS collected_items (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                run_id BIGINT NOT NULL,
                page_name VARCHAR(100) NOT NULL,
                text_content LONGTEXT NOT NULL,
                created_at VARCHAR(32) NOT NULL,
                INDEX idx_collected_items_run_id (run_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS collected_records (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                run_id BIGINT NOT NULL,
                local_run_id BIGINT NOT NULL,
                item_index INT NOT NULL,
                platform VARCHAR(64) NOT NULL,
                record_type VARCHAR(64) NOT NULL,
                keyword VARCHAR(255) NULL,
                title LONGTEXT NULL,
                content_text LONGTEXT NULL,
                author_name VARCHAR(255) NULL,
                author_id VARCHAR(255) NULL,
                location_text VARCHAR(255) NULL,
                ip_location VARCHAR(255) NULL,
                published_text VARCHAR(255) NULL,
                metrics_json LONGTEXT NULL,
                extra_json LONGTEXT NULL,
                raw_visible_texts_json LONGTEXT NULL,
                created_at VARCHAR(32) NOT NULL,
                INDEX idx_records_local_run_id (local_run_id),
                INDEX idx_records_platform_type (platform, record_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS run_artifacts (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                run_id BIGINT NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                local_path TEXT NOT NULL,
                object_path VARCHAR(512) NOT NULL,
                public_url TEXT NOT NULL,
                content_type VARCHAR(128) NOT NULL,
                file_size BIGINT NOT NULL DEFAULT 0,
                created_at VARCHAR(32) NOT NULL,
                UNIQUE KEY uniq_run_artifact (run_id, file_name),
                INDEX idx_run_artifacts_run_id (run_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.close()

        required_columns: dict[str, list[tuple[str, str]]] = {
            "task_runs": [
                ("task_name", "VARCHAR(255) NOT NULL DEFAULT ''"),
                ("adapter", "VARCHAR(128) NOT NULL DEFAULT ''"),
                ("platform", "VARCHAR(64) NOT NULL DEFAULT ''"),
                ("package_name", "VARCHAR(255) NOT NULL DEFAULT ''"),
                ("run_mode", "VARCHAR(32) NOT NULL DEFAULT 'normal'"),
                ("status", "VARCHAR(32) NOT NULL DEFAULT 'pending'"),
                ("device_serial", "VARCHAR(255) NOT NULL DEFAULT ''"),
                ("requested_at", "VARCHAR(32) NOT NULL DEFAULT ''"),
                ("started_at", "VARCHAR(32) NULL"),
                ("finished_at", "VARCHAR(32) NULL"),
                ("artifact_dir", "TEXT NULL"),
                ("log_path", "TEXT NULL"),
                ("config_json", "LONGTEXT NULL"),
                ("result_json", "LONGTEXT NULL"),
                ("error_message", "LONGTEXT NULL"),
                ("mysql_run_id", "BIGINT NULL"),
                ("items_count", "INT NOT NULL DEFAULT 0"),
                ("comment_count", "INT NOT NULL DEFAULT 0"),
                ("cancel_requested", "TINYINT(1) NOT NULL DEFAULT 0"),
                ("created_at", "VARCHAR(32) NOT NULL DEFAULT ''"),
                ("updated_at", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ],
            "collected_items": [
                ("run_id", "BIGINT NOT NULL DEFAULT 0"),
                ("page_name", "VARCHAR(100) NOT NULL DEFAULT ''"),
                ("text_content", "LONGTEXT NULL"),
                ("created_at", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ],
            "collected_records": [
                ("run_id", "BIGINT NOT NULL DEFAULT 0"),
                ("local_run_id", "BIGINT NOT NULL DEFAULT 0"),
                ("item_index", "INT NOT NULL DEFAULT 0"),
                ("platform", "VARCHAR(64) NOT NULL DEFAULT ''"),
                ("record_type", "VARCHAR(64) NOT NULL DEFAULT ''"),
                ("keyword", "VARCHAR(255) NULL"),
                ("title", "LONGTEXT NULL"),
                ("content_text", "LONGTEXT NULL"),
                ("author_name", "VARCHAR(255) NULL"),
                ("author_id", "VARCHAR(255) NULL"),
                ("location_text", "VARCHAR(255) NULL"),
                ("ip_location", "VARCHAR(255) NULL"),
                ("published_text", "VARCHAR(255) NULL"),
                ("metrics_json", "LONGTEXT NULL"),
                ("extra_json", "LONGTEXT NULL"),
                ("raw_visible_texts_json", "LONGTEXT NULL"),
                ("created_at", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ],
            "run_artifacts": [
                ("run_id", "BIGINT NOT NULL DEFAULT 0"),
                ("file_name", "VARCHAR(255) NOT NULL DEFAULT ''"),
                ("local_path", "TEXT NULL"),
                ("object_path", "VARCHAR(512) NOT NULL DEFAULT ''"),
                ("public_url", "TEXT NULL"),
                ("content_type", "VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream'"),
                ("file_size", "BIGINT NOT NULL DEFAULT 0"),
                ("created_at", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ],
        }
        existing_columns = self._load_existing_columns(required_columns)
        for table_name, columns in required_columns.items():
            self._ensure_columns(table_name, columns, existing_columns.get(table_name, set()))

    def _connect_database(self):
        if mysql is None:
            raise DependencyError("缺少 mysql-connector-python 依赖，请先安装 requirements.txt。")
        return mysql.connect(
            host=self._effective_host,
            port=self._effective_port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset=self.config.charset,
            autocommit=True,
        )

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        cursor = self._cursor()
        cursor.execute(sql, params)
        cursor.close()

    def _load_existing_columns(self, table_columns: dict[str, list[tuple[str, str]]]) -> dict[str, set[str]]:
        table_names = sorted(table_columns)
        placeholders = ", ".join(["%s"] * len(table_names))
        cursor = self._cursor(dictionary=True)
        cursor.execute(
            f"""
            SELECT
                table_name AS table_name,
                column_name AS column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name IN ({placeholders})
            """,
            (self.config.database, *table_names),
        )
        rows = cursor.fetchall()
        cursor.close()

        existing_columns = {table_name: set() for table_name in table_names}
        for row in rows:
            table_name = str(row["table_name"] or "")
            column_name = str(row["column_name"] or "")
            if table_name in existing_columns and column_name:
                existing_columns[table_name].add(column_name)
        return existing_columns

    def _ensure_columns(self, table_name: str, columns: list[tuple[str, str]], existing_columns: set[str]) -> None:
        for column_name, column_sql in columns:
            if column_name in existing_columns:
                continue
            alter_cursor = self._cursor()
            alter_cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {column_sql}")
            alter_cursor.close()

    def _schema_cache_key(self) -> str:
        return self._dump_json(
            {
                "mysql": {
                    "host": self.config.host,
                    "port": self.config.port,
                    "user": self.config.user,
                    "password": self.config.password,
                    "database": self.config.database,
                    "charset": self.config.charset,
                },
                "ssh": {
                    "enabled": self.ssh_config.enabled,
                    "host": self.ssh_config.host,
                    "port": self.ssh_config.port,
                    "user": self.ssh_config.user,
                    "password": self.ssh_config.password,
                    "local_port": self.ssh_config.local_port,
                    "remote_host": self.ssh_config.remote_host,
                    "remote_port": self.ssh_config.remote_port,
                },
            }
        ) or ""

    def _cursor(self, *, dictionary: bool = False):
        if self.connection is None:
            raise DriverError("MySQL 连接尚未建立。")
        return self.connection.cursor(dictionary=dictionary)

    @staticmethod
    def _dump_json(data: Any) -> str | None:
        if data is None:
            return None
        return json.dumps(data, ensure_ascii=False)

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

    @classmethod
    def _row_to_run_summary(cls, row: dict[str, Any]) -> dict[str, Any]:
        result_json = cls._load_json(row.get("result_json"))
        config_json = cls._load_json(row.get("config_json"))
        run_id = int(row["id"])
        return {
            "id": run_id,
            "task_name": str(row.get("task_name") or ""),
            "adapter": str(row.get("adapter") or ""),
            "platform": str(row.get("platform") or ""),
            "package_name": str(row.get("package_name") or ""),
            "run_mode": str(row.get("run_mode") or "normal"),
            "status": str(row.get("status") or ""),
            "device_serial": str(row.get("device_serial") or ""),
            "requested_at": str(row.get("requested_at") or ""),
            "started_at": str(row.get("started_at") or ""),
            "finished_at": str(row.get("finished_at") or ""),
            "artifact_dir": str(row.get("artifact_dir") or ""),
            "log_path": str(row.get("log_path") or ""),
            "config": config_json if isinstance(config_json, dict) else {},
            "result": result_json if isinstance(result_json, dict) else {},
            "error_message": str(row.get("error_message") or ""),
            "mysql_run_id": int(row["mysql_run_id"]) if row.get("mysql_run_id") is not None else run_id,
            "items_count": int(row.get("items_count") or 0),
            "comment_count": int(row.get("comment_count") or 0),
            "cancel_requested": bool(int(row.get("cancel_requested") or 0)),
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }

    @classmethod
    def _row_to_collected_record(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "local_run_id": int(row["local_run_id"]),
            "item_index": int(row["item_index"]),
            "platform": str(row.get("platform") or ""),
            "record_type": str(row.get("record_type") or ""),
            "keyword": str(row.get("keyword") or ""),
            "title": str(row.get("title") or ""),
            "content_text": str(row.get("content_text") or ""),
            "author_name": str(row.get("author_name") or ""),
            "author_id": str(row.get("author_id") or ""),
            "location_text": str(row.get("location_text") or ""),
            "ip_location": str(row.get("ip_location") or ""),
            "published_text": str(row.get("published_text") or ""),
            "metrics": cls._load_json(row.get("metrics_json")) or {},
            "extra": cls._load_json(row.get("extra_json")) or {},
            "raw_visible_texts": cls._load_json(row.get("raw_visible_texts_json")) or [],
            "created_at": str(row.get("created_at") or ""),
        }

    @staticmethod
    def _detect_artifact_kind(filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return "image"
        if suffix == ".json":
            return "json"
        if suffix == ".xml":
            return "xml"
        if suffix == ".csv":
            return "csv"
        if suffix in {".log", ".txt"}:
            return "text"
        return "file"
