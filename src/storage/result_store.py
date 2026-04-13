from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from src.models.artifact_upload import ArtifactUploadRecord
from src.models.collected_record import CollectedRecord
from src.models.task_models import MySQLConfig
from src.utils.exceptions import DependencyError, DriverError, StorageError
from src.utils.time_utils import format_datetime

mysql: Any | None

try:
    import mysql.connector as mysql_connector
except ImportError:  # pragma: no cover - 依赖检查由 doctor 命令负责
    mysql = None
else:
    mysql = mysql_connector


class MySQLResultStore:
    """负责 MySQL 建表和运行结果写入。"""

    def __init__(self, config: MySQLConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.connection = None

    def connect(self) -> None:
        if mysql is None:
            raise DependencyError("缺少 mysql-connector-python 依赖，请先安装 requirements.txt。")
        mysql_module = mysql
        try:
            self.connection = self._connect_database()
        except mysql_module.Error as exc:
            if getattr(exc, "errno", None) != 1049:
                raise
            self._ensure_database()
            self.connection = self._connect_database()
        self._ensure_tables()
        self.logger.info("MySQL 已连接：%s:%s/%s", self.config.host, self.config.port, self.config.database)

    def create_run(self, task_name: str, device_serial: str, status: str, started_at: str) -> int:
        cursor = self._cursor()
        cursor.execute(
            """
            INSERT INTO task_runs (task_name, device_serial, status, started_at)
            VALUES (%s, %s, %s, %s)
            """,
            (task_name, device_serial, status, started_at),
        )
        run_id = int(cursor.lastrowid)
        cursor.close()
        return run_id

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        finished_at: str,
        artifact_dir: str,
        error_message: str | None,
    ) -> None:
        cursor = self._cursor()
        cursor.execute(
            """
            UPDATE task_runs
            SET status = %s,
                finished_at = %s,
                artifact_dir = %s,
                error_message = %s
            WHERE id = %s
            """,
            (status, finished_at, artifact_dir, error_message, run_id),
        )
        cursor.close()

    def save_collected_items(self, run_id: int, page_name: str, texts: Iterable[str]) -> None:
        text_rows = [(run_id, page_name, text, format_datetime(None)) for text in texts if text.strip()]
        if not text_rows:
            return
        cursor = self._cursor()
        cursor.executemany(
            """
            INSERT INTO collected_items (run_id, page_name, text_content, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            text_rows,
        )
        cursor.close()

    def save_collected_records(self, run_id: int, records: Iterable[CollectedRecord]) -> None:
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

        if not rows:
            return

        cursor = self._cursor()
        cursor.executemany(
            """
            INSERT INTO collected_records (
                run_id, item_index, platform, record_type, keyword, title, content_text,
                author_name, author_id, location_text, ip_location, published_text,
                metrics_json, extra_json, raw_visible_texts_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        cursor.close()

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

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _ensure_database(self) -> None:
        if mysql is None:
            raise DependencyError("缺少 mysql-connector-python 依赖，请先安装 requirements.txt。")
        mysql_module = mysql
        try:
            server_connection = mysql_module.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                autocommit=True,
            )
        except mysql_module.Error as exc:
            raise StorageError(f"MySQL 建库前连接失败：{exc}") from exc

        cursor = server_connection.cursor()
        try:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{self.config.database}` CHARACTER SET {self.config.charset} COLLATE {self.config.charset}_unicode_ci"
            )
        except mysql_module.Error as exc:
            raise StorageError(
                f"MySQL 数据库 `{self.config.database}` 不存在，且当前账号无权自动创建。请先在服务器上创建该数据库。"
            ) from exc
        finally:
            cursor.close()
            server_connection.close()

    def _ensure_tables(self) -> None:
        cursor = self._cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                task_name VARCHAR(100) NOT NULL,
                device_serial VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL,
                started_at DATETIME NOT NULL,
                finished_at DATETIME NULL,
                artifact_dir VARCHAR(255) NULL,
                error_message TEXT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS collected_items (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                run_id BIGINT NOT NULL,
                page_name VARCHAR(100) NOT NULL,
                text_content TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                INDEX idx_run_id (run_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS collected_records (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                run_id BIGINT NOT NULL,
                item_index INT NOT NULL,
                platform VARCHAR(64) NOT NULL,
                record_type VARCHAR(64) NOT NULL,
                keyword VARCHAR(255) NULL,
                title TEXT NULL,
                content_text LONGTEXT NULL,
                author_name VARCHAR(255) NULL,
                author_id VARCHAR(255) NULL,
                location_text VARCHAR(255) NULL,
                ip_location VARCHAR(255) NULL,
                published_text VARCHAR(255) NULL,
                metrics_json LONGTEXT NULL,
                extra_json LONGTEXT NULL,
                raw_visible_texts_json LONGTEXT NULL,
                created_at DATETIME NOT NULL,
                INDEX idx_records_run_id (run_id),
                INDEX idx_records_platform_type (platform, record_type)
            )
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
                created_at DATETIME NOT NULL,
                INDEX idx_run_artifacts_run_id (run_id)
            )
            """
        )
        cursor.close()

    def _connect_database(self):
        if mysql is None:
            raise DependencyError("缺少 mysql-connector-python 依赖，请先安装 requirements.txt。")
        mysql_module = mysql
        return mysql_module.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset=self.config.charset,
            autocommit=True,
        )

    def _cursor(self):
        if self.connection is None:
            raise DriverError("MySQL 连接尚未建立。")
        return self.connection.cursor()
