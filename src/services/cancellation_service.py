from __future__ import annotations

from pathlib import Path

from src.services.settings_service import SettingsService
from src.services.shared_store_factory import SharedStoreFactory
from src.utils.exceptions import TaskCancelledError


class CancellationService:
    """基于共享 MySQL 的协作式取消控制。"""

    def __init__(self, sqlite_path: Path) -> None:
        self.settings_service = SettingsService(sqlite_path)
        self.store_factory = SharedStoreFactory(self.settings_service)

    def request_cancel(self, run_id: int) -> None:
        store = self.store_factory.create_result_store(logger_name="cancellation_service")
        try:
            store.request_cancel(run_id)
        finally:
            store.close()

    def is_cancel_requested(self, run_id: int) -> bool:
        store = self.store_factory.create_result_store(logger_name="cancellation_service")
        try:
            return store.is_cancel_requested(run_id)
        finally:
            store.close()

    def check_cancelled(self, run_id: int) -> None:
        if self.is_cancel_requested(run_id):
            raise TaskCancelledError("任务已收到停止指令，准备结束本次采集。")
