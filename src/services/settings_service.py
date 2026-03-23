from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

    def to_dict(self) -> dict[str, str | int]:
        return {
            "adb_path": self.adb_path,
            "output_dir": self.output_dir,
            "mysql_host": self.mysql_host,
            "mysql_port": self.mysql_port,
            "mysql_user": self.mysql_user,
            "mysql_password": self.mysql_password,
            "mysql_database": self.mysql_database,
            "mysql_charset": self.mysql_charset,
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
            adb_path=str(raw_settings.get("adb_path", "")),
            output_dir=str(raw_settings.get("output_dir", "artifacts")),
            mysql_host=str(raw_settings.get("mysql_host", "127.0.0.1")),
            mysql_port=int(raw_settings.get("mysql_port", 3306)),
            mysql_user=str(raw_settings.get("mysql_user", "root")),
            mysql_password=str(raw_settings.get("mysql_password", "123456")),
            mysql_database=str(raw_settings.get("mysql_database", "android_spider")),
            mysql_charset=str(raw_settings.get("mysql_charset", "utf8mb4")),
        )

    def save_settings(self, settings: AppSettings) -> AppSettings:
        store = SQLiteStore(self.sqlite_path)
        try:
            for key, value in settings.to_dict().items():
                store.set_setting(key, str(value))
        finally:
            store.close()
        return settings
