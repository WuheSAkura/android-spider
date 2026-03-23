from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from src.core.adb_manager import AdbManager
from src.core.task_runner import TaskRunner
from src.models.task_models import TaskConfig
from src.services.cancellation_service import CancellationService
from src.services.settings_service import SettingsService
from src.services.task_template_service import TaskTemplateService
from src.storage.sqlite_store import ACTIVE_RUN_STATUSES, SQLiteStore


RUN_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="android_spider_run")
RUN_FUTURES: dict[int, Future[dict[str, Any]]] = {}


class RunService:
    """任务创建、查询、取消与本地文件读取。"""

    def __init__(self, project_root: Path, sqlite_path: Path) -> None:
        self.project_root = project_root
        self.sqlite_path = sqlite_path
        self.template_service = TaskTemplateService(project_root)
        self.settings_service = SettingsService(sqlite_path)
        self.cancellation_service = CancellationService(sqlite_path)

    def bootstrap(self) -> int:
        store = SQLiteStore(self.sqlite_path)
        try:
            return store.recover_interrupted_runs()
        finally:
            store.close()

    def create_run(
        self,
        *,
        template_id: str,
        device_serial: str | None,
        run_mode: str,
        adapter_options: dict[str, Any],
    ) -> dict[str, Any]:
        store = SQLiteStore(self.sqlite_path)
        try:
            active_run = store.get_active_run()
            if active_run is not None and active_run["status"] in ACTIVE_RUN_STATUSES:
                raise RuntimeError(f"已有运行中的任务：#{active_run['id']}")

            template = self.template_service.get_template(template_id)
            task_config = self._build_task_config(
                template_id=template_id,
                device_serial=device_serial,
                run_mode=run_mode,
                adapter_options=adapter_options,
            )
            run_id = store.create_run(
                task_name=task_config.task_name,
                adapter=task_config.adapter,
                platform=template.platform,
                package_name=task_config.package_name,
                run_mode=task_config.run_mode,
                config_json={
                    "template_id": template_id,
                    "device_serial": task_config.device_serial or "",
                    "run_mode": task_config.run_mode,
                    "adapter_options": task_config.adapter_options,
                },
            )
        finally:
            store.close()

        future = RUN_EXECUTOR.submit(self._run_task, run_id, task_config)
        RUN_FUTURES[run_id] = future
        return self.get_run(run_id)

    def request_cancel(self, run_id: int) -> dict[str, Any]:
        self.cancellation_service.request_cancel(run_id)
        return self.get_run(run_id)

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        store = SQLiteStore(self.sqlite_path)
        try:
            return store.list_runs(limit=limit)
        finally:
            store.close()

    def get_run(self, run_id: int) -> dict[str, Any]:
        store = SQLiteStore(self.sqlite_path)
        try:
            run = store.get_run(run_id)
        finally:
            store.close()
        if run is None:
            raise KeyError(f"任务不存在：{run_id}")
        return run

    def get_run_records(self, run_id: int) -> list[dict[str, Any]]:
        self.get_run(run_id)
        store = SQLiteStore(self.sqlite_path)
        try:
            return store.get_run_records(run_id)
        finally:
            store.close()

    def get_run_logs(self, run_id: int, tail: int = 200) -> dict[str, Any]:
        run = self.get_run(run_id)
        log_path_value = str(run.get("log_path") or "")
        if not log_path_value:
            return {"path": "", "content": "", "line_count": 0}

        log_path = Path(log_path_value)
        if not log_path.exists():
            return {"path": str(log_path), "content": "", "line_count": 0}

        content = log_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        tail_lines = lines[-tail:] if tail > 0 else lines
        return {
            "path": str(log_path),
            "content": "\n".join(tail_lines),
            "line_count": len(lines),
        }

    def get_run_artifacts(self, run_id: int) -> list[dict[str, Any]]:
        run = self.get_run(run_id)
        artifact_dir_value = str(run.get("artifact_dir") or "")
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
                    "kind": self._detect_artifact_kind(path),
                }
            )
        return items

    def _build_task_config(
        self,
        *,
        template_id: str,
        device_serial: str | None,
        run_mode: str,
        adapter_options: dict[str, Any],
    ) -> TaskConfig:
        settings = self.settings_service.get_settings()
        raw_config = self.template_service.load_template_config(template_id)
        template = self.template_service.get_template(template_id)

        raw_config["device_serial"] = device_serial or None
        raw_config["run_mode"] = run_mode
        raw_config["steps"] = []
        raw_config["output_dir"] = settings.output_dir or str(raw_config.get("output_dir", "artifacts"))

        storage_config = dict(raw_config.get("storage", {}) or {})
        mysql_config = dict(storage_config.get("mysql", {}) or {})
        mysql_config.update(
            {
                "host": settings.mysql_host,
                "port": settings.mysql_port,
                "user": settings.mysql_user,
                "password": settings.mysql_password,
                "database": settings.mysql_database,
                "charset": settings.mysql_charset,
            }
        )
        storage_config["mysql"] = mysql_config
        storage_config["sqlite_path"] = str(self.sqlite_path)
        raw_config["storage"] = storage_config

        merged_options = dict(template.default_options)
        merged_options.update(adapter_options)
        if run_mode == "light_smoke":
            merged_options.update(template.light_smoke_overrides)
        raw_config["adapter_options"] = merged_options

        return TaskConfig.from_dict(raw_config)

    def _run_task(self, run_id: int, task_config: TaskConfig) -> dict[str, Any]:
        try:
            adb_path = self.settings_service.get_settings().adb_path or None
            runner = TaskRunner(
                task_config,
                AdbManager(adb_path),
                local_run_id=run_id,
            )
            return runner.run()
        finally:
            RUN_FUTURES.pop(run_id, None)

    @staticmethod
    def _detect_artifact_kind(path: Path) -> str:
        if path.is_dir():
            return "directory"
        suffix = path.suffix.lower()
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
