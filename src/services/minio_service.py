from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path, PurePosixPath
from typing import Any

from src.models.artifact_upload import ArtifactUploadRecord
from src.models.task_models import MinIOConfig
from src.utils.exceptions import ConfigError, DependencyError, StorageError

minio_module: Any | None
minio_error: type[Exception] | None

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:  # pragma: no cover - 依赖检查由 doctor 命令负责
    minio_module = None
    minio_error = None
else:
    minio_module = Minio
    minio_error = S3Error


class MinIOArtifactService:
    """负责将任务产物上传到 MinIO 并生成可持久化的公开 URL。"""

    def __init__(self, config: MinIOConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.client: Any | None = None

    def enabled(self) -> bool:
        return bool(self.config.enabled and self.config.endpoint and self.config.bucket)

    def plan_uploads(self, artifact_dir: Path, *, task_name: str) -> list[ArtifactUploadRecord]:
        if not artifact_dir.exists():
            return []

        prefix = PurePosixPath("android-spider", self._sanitize_name(task_name), self._sanitize_name(artifact_dir.name))
        records: list[ArtifactUploadRecord] = []
        for local_path in sorted(item for item in artifact_dir.rglob("*") if item.is_file()):
            relative_path = local_path.relative_to(artifact_dir).as_posix()
            object_path = str(prefix / PurePosixPath(relative_path))
            content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
            records.append(
                ArtifactUploadRecord(
                    local_path=local_path,
                    relative_path=relative_path,
                    object_path=object_path,
                    public_url=self._build_public_url(object_path),
                    content_type=content_type,
                )
            )
        return records

    def upload_records(self, records: list[ArtifactUploadRecord]) -> list[ArtifactUploadRecord]:
        if not records:
            return records
        self._ensure_client()
        self._ensure_bucket()
        client = self.client
        if client is None:
            raise DependencyError("MinIO 客户端尚未初始化。")

        for record in records:
            try:
                record.file_size = record.local_path.stat().st_size
                client.fput_object(
                    self.config.bucket,
                    record.object_path,
                    str(record.local_path),
                    content_type=record.content_type,
                )
            except OSError as exc:
                raise StorageError(f"读取待上传文件失败：{record.local_path}，原因：{exc}") from exc
            except Exception as exc:
                if minio_error is not None and isinstance(exc, minio_error):
                    raise StorageError(f"上传 MinIO 失败：{record.relative_path}，原因：{exc}") from exc
                raise
        self.logger.info("MinIO 产物上传完成：%s 个文件。", len(records))
        return records

    def _ensure_client(self) -> None:
        if self.client is not None:
            return
        if minio_module is None:
            raise DependencyError("缺少 minio 依赖，请先安装 requirements.txt。")
        if not self.config.endpoint or not self.config.access_key or not self.config.secret_key:
            raise ConfigError("MinIO 已启用，但 endpoint/access_key/secret_key/bucket 配置不完整。")
        client_class = minio_module
        self.client = client_class(
            self.config.endpoint,
            access_key=self.config.access_key,
            secret_key=self.config.secret_key,
            secure=self.config.secure,
        )

    def _ensure_bucket(self) -> None:
        client = self.client
        if client is None:
            raise DependencyError("MinIO 客户端尚未初始化。")
        try:
            exists = client.bucket_exists(self.config.bucket)
        except Exception as exc:
            if minio_error is not None and isinstance(exc, minio_error):
                raise StorageError(f"检测 MinIO Bucket 失败：{exc}") from exc
            raise
        if exists:
            return
        try:
            client.make_bucket(self.config.bucket)
        except Exception as exc:
            if minio_error is not None and isinstance(exc, minio_error):
                raise StorageError(f"创建 MinIO Bucket 失败：{self.config.bucket}，原因：{exc}") from exc
            raise
        self.logger.info("已创建 MinIO Bucket：%s", self.config.bucket)

    def _build_public_url(self, object_path: str) -> str:
        base_url = self.config.public_url.strip() or f"{'https' if self.config.secure else 'http'}://{self.config.endpoint}"
        return f"{base_url.rstrip('/')}/{self.config.bucket}/{object_path}"

    @staticmethod
    def _sanitize_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "task"
