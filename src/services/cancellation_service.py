from __future__ import annotations

from pathlib import Path

from src.storage.sqlite_store import SQLiteStore
from src.utils.exceptions import TaskCancelledError


class CancellationService:
    """基于 SQLite 的协作式取消控制。"""

    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path

    def request_cancel(self, run_id: int) -> None:
        store = SQLiteStore(self.sqlite_path)
        try:
            store.request_cancel(run_id)
        finally:
            store.close()

    def is_cancel_requested(self, run_id: int) -> bool:
        store = SQLiteStore(self.sqlite_path)
        try:
            return store.is_cancel_requested(run_id)
        finally:
            store.close()

    def check_cancelled(self, run_id: int) -> None:
        if self.is_cancel_requested(run_id):
            raise TaskCancelledError("任务已收到停止指令，准备结束本次采集。")
