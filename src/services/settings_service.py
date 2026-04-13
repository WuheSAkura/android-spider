from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.services.env_service import get_env, get_env_bool, get_env_int
from src.storage.sqlite_store import SQLiteStore


@dataclass(slots=True)
class AppSettings:
    adb_path: str = ""
    output_dir: str = "artifacts"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "android_spider"
    mysql_charset: str = "utf8mb4"
    ssh_enabled: bool = False
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_user: str = ""
    ssh_password: str = ""
    ssh_local_port: int = 13306
    ssh_remote_host: str = "127.0.0.1"
    ssh_remote_port: int = 3306
    minio_enabled: bool = False
    minio_public_url: str = ""
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_secure: bool = False
    minio_bucket: str = ""

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "adb_path": self.adb_path,
            "output_dir": self.output_dir,
            "mysql_host": self.mysql_host,
            "mysql_port": self.mysql_port,
            "mysql_user": self.mysql_user,
            "mysql_password": self.mysql_password,
            "mysql_database": self.mysql_database,
            "mysql_charset": self.mysql_charset,
            "ssh_enabled": self.ssh_enabled,
            "ssh_host": self.ssh_host,
            "ssh_port": self.ssh_port,
            "ssh_user": self.ssh_user,
            "ssh_password": self.ssh_password,
            "ssh_local_port": self.ssh_local_port,
            "ssh_remote_host": self.ssh_remote_host,
            "ssh_remote_port": self.ssh_remote_port,
            "minio_enabled": self.minio_enabled,
            "minio_public_url": self.minio_public_url,
            "minio_endpoint": self.minio_endpoint,
            "minio_access_key": self.minio_access_key,
            "minio_secret_key": self.minio_secret_key,
            "minio_secure": self.minio_secure,
            "minio_bucket": self.minio_bucket,
        }


class SettingsService:
    """桌面端本地设置读写。"""

    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path

    def get_settings(self) -> AppSettings:
        store = SQLiteStore(self.sqlite_path)
        try:
            raw_settings = store.get_all_settings()
        finally:
            store.close()

        return AppSettings(
            adb_path=self._get_str(raw_settings, "adb_path", "", env_name="ADB_PATH"),
            output_dir=self._get_str(raw_settings, "output_dir", "artifacts", env_name="OUTPUT_DIR"),
            mysql_host=self._get_str(raw_settings, "mysql_host", "127.0.0.1", env_name="MYSQL_HOST"),
            mysql_port=self._get_int(raw_settings, "mysql_port", 3306, env_name="MYSQL_PORT"),
            mysql_user=self._get_str(raw_settings, "mysql_user", "root", env_name="MYSQL_USER"),
            mysql_password=self._get_str(raw_settings, "mysql_password", "123456", env_name="MYSQL_PASSWORD"),
            mysql_database=self._get_str(raw_settings, "mysql_database", "android_spider", env_name="MYSQL_DATABASE"),
            mysql_charset=self._get_str(raw_settings, "mysql_charset", "utf8mb4", env_name="MYSQL_CHARSET"),
            ssh_enabled=self._get_bool(raw_settings, "ssh_enabled", False, env_name="SSH_ENABLED"),
            ssh_host=self._get_str(raw_settings, "ssh_host", "", env_name="SSH_HOST"),
            ssh_port=self._get_int(raw_settings, "ssh_port", 22, env_name="SSH_PORT"),
            ssh_user=self._get_str(raw_settings, "ssh_user", "", env_name="SSH_USER"),
            ssh_password=self._get_str(raw_settings, "ssh_password", "", env_name="SSH_PASSWORD"),
            ssh_local_port=self._get_int(raw_settings, "ssh_local_port", 13306, env_name="SSH_LOCAL_PORT"),
            ssh_remote_host=self._get_str(raw_settings, "ssh_remote_host", "127.0.0.1", env_name="SSH_REMOTE_HOST"),
            ssh_remote_port=self._get_int(raw_settings, "ssh_remote_port", 3306, env_name="SSH_REMOTE_PORT"),
            minio_enabled=self._get_bool(raw_settings, "minio_enabled", False, env_name="MINIO_ENABLED"),
            minio_public_url=self._get_str(raw_settings, "minio_public_url", "", env_name="MINIO_PUBLIC_URL"),
            minio_endpoint=self._get_str(raw_settings, "minio_endpoint", "", env_name="MINIO_ENDPOINT"),
            minio_access_key=self._get_str(raw_settings, "minio_access_key", "", env_name="MINIO_ACCESS_KEY"),
            minio_secret_key=self._get_str(raw_settings, "minio_secret_key", "", env_name="MINIO_SECRET_KEY"),
            minio_secure=self._get_bool(raw_settings, "minio_secure", False, env_name="MINIO_SECURE"),
            minio_bucket=self._get_str(raw_settings, "minio_bucket", "", env_name="MINIO_BUCKET", fallback_env_name="MINIO_BUCKET_NAME"),
        )

    def save_settings(self, settings: AppSettings) -> AppSettings:
        store = SQLiteStore(self.sqlite_path)
        try:
            for key, value in settings.to_dict().items():
                store.set_setting(key, str(value))
        finally:
            store.close()
        return settings

    @staticmethod
    def _get_str(
        raw_settings: dict[str, str],
        key: str,
        default: str,
        *,
        env_name: str | None = None,
        fallback_env_name: str | None = None,
    ) -> str:
        if key in raw_settings:
            return str(raw_settings[key])
        env_value = get_env(env_name, None) if env_name is not None else None
        if env_value not in (None, ""):
            return str(env_value)
        fallback_value = get_env(fallback_env_name, None) if fallback_env_name is not None else None
        if fallback_value not in (None, ""):
            return str(fallback_value)
        return default

    @staticmethod
    def _get_int(raw_settings: dict[str, str], key: str, default: int, *, env_name: str | None = None) -> int:
        if key in raw_settings:
            try:
                return int(raw_settings[key])
            except ValueError:
                return default
        return get_env_int(env_name, default) if env_name is not None else default

    @staticmethod
    def _get_bool(raw_settings: dict[str, str], key: str, default: bool, *, env_name: str | None = None) -> bool:
        if key in raw_settings:
            return str(raw_settings[key]).strip().lower() in {"1", "true", "yes", "on"}
        return get_env_bool(env_name, default) if env_name is not None else default
