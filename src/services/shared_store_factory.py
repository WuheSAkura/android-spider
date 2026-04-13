from __future__ import annotations

import logging

from src.services.settings_service import AppSettings, SettingsService
from src.storage.mysql_analysis_store import MySQLAnalysisStore
from src.storage.result_store import MySQLResultStore


class SharedStoreFactory:
    """按当前设置创建已连接的共享 MySQL 存储。"""

    def __init__(self, settings_service: SettingsService) -> None:
        self.settings_service = settings_service

    def get_settings(self) -> AppSettings:
        return self.settings_service.get_settings()

    def create_result_store(self, *, logger_name: str) -> MySQLResultStore:
        settings = self.get_settings()
        store = MySQLResultStore(
            settings.to_mysql_config(),
            logging.getLogger(logger_name),
            ssh_config=settings.to_ssh_config(),
        )
        store.connect()
        return store

    def create_analysis_store(self, *, logger_name: str) -> MySQLAnalysisStore:
        settings = self.get_settings()
        store = MySQLAnalysisStore(
            settings.to_mysql_config(),
            logging.getLogger(logger_name),
            ssh_config=settings.to_ssh_config(),
        )
        store.connect()
        return store
