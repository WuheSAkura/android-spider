from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from src.core.adb_manager import AdbManager, DeviceInfo
from src.core.device_manager import DeviceManager
from src.core.task_runner import TaskRunner
from src.models.task_models import TaskConfig
from src.services.cancellation_service import CancellationService
from src.services.settings_service import SettingsService
from src.services.shared_store_factory import SharedStoreFactory
from src.services.task_template_service import TaskTemplateService
from src.storage.result_store import ACTIVE_RUN_STATUSES
from src.utils.exceptions import ConfigError
from src.utils.time_utils import format_datetime


RUN_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="android_spider_run")
RUN_FUTURES: dict[int, Future[dict[str, Any]]] = {}


class RunService:
    """共享任务创建、查询、取消与产物读取服务。"""

    def __init__(self, project_root: Path, sqlite_path: Path) -> None:
        self.project_root = project_root
        self.sqlite_path = sqlite_path
        self.template_service = TaskTemplateService(project_root)
        self.settings_service = SettingsService(sqlite_path)
        self.store_factory = SharedStoreFactory(self.settings_service)
        self.cancellation_service = CancellationService(sqlite_path)
        self._scheduling_lock = threading.Lock()

    def bootstrap(self) -> int:
        store = self.store_factory.create_result_store(logger_name="run_service")
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
        with self._scheduling_lock:
            template = self.template_service.get_template(template_id)
            active_device_map = self.get_active_device_map()
            resolved_device_serial = self._resolve_device_serial(
                requested_device_serial=device_serial,
                active_device_map=active_device_map,
            )
            task_config = self._build_task_config(
                template_id=template_id,
                device_serial=resolved_device_serial,
                run_mode=run_mode,
                adapter_options=adapter_options,
            )
            store = self.store_factory.create_result_store(logger_name="run_service")
            try:
                requested_at = format_datetime(None)
                run_id = store.create_run(
                    task_name=task_config.task_name,
                    adapter=task_config.adapter,
                    platform=template.platform,
                    package_name=task_config.package_name,
                    run_mode=task_config.run_mode,
                    device_serial=resolved_device_serial,
                    status="pending",
                    started_at=requested_at,
                    requested_at=requested_at,
                    config_json={
                        "template_id": template_id,
                        "device_serial": task_config.device_serial or "",
                        "run_mode": task_config.run_mode,
                        "adapter_options": task_config.adapter_options,
                    },
                )
            finally:
                store.close()

        try:
            future = RUN_EXECUTOR.submit(self._run_task, run_id, task_config)
            RUN_FUTURES[run_id] = future
        except Exception as exc:
            self._mark_run_schedule_failed(run_id, task_config.device_serial or "", str(exc))
            raise RuntimeError(f"任务调度失败：{exc}") from exc
        return self.get_run(run_id)

    def request_cancel(self, run_id: int) -> dict[str, Any]:
        self.cancellation_service.request_cancel(run_id)
        return self.get_run(run_id)

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        store = self.store_factory.create_result_store(logger_name="run_service")
        try:
            return store.list_runs(limit=limit)
        finally:
            store.close()

    def list_active_runs(self) -> list[dict[str, Any]]:
        store = self.store_factory.create_result_store(logger_name="run_service")
        try:
            return store.list_active_runs()
        finally:
            store.close()

    def get_active_device_map(self) -> dict[str, dict[str, Any]]:
        return self._build_active_device_map(self.list_active_runs())

    def get_run(self, run_id: int) -> dict[str, Any]:
        store = self.store_factory.create_result_store(logger_name="run_service")
        try:
            run = store.get_run(run_id)
        finally:
            store.close()
        if run is None:
            raise KeyError(f"任务不存在：{run_id}")
        return run

    def get_run_records(self, run_id: int) -> list[dict[str, Any]]:
        self.get_run(run_id)
        store = self.store_factory.create_result_store(logger_name="run_service")
        try:
            return store.get_run_records(run_id)
        finally:
            store.close()

    def get_run_logs(self, run_id: int, tail: int = 200) -> dict[str, Any]:
        self.get_run(run_id)
        store = self.store_factory.create_result_store(logger_name="run_service")
        try:
            return store.get_run_logs(run_id, tail=tail)
        finally:
            store.close()

    def get_run_artifacts(self, run_id: int) -> list[dict[str, Any]]:
        self.get_run(run_id)
        store = self.store_factory.create_result_store(logger_name="run_service")
        try:
            return store.get_run_artifacts(run_id)
        finally:
            store.close()

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
        storage_config["ssh"] = {
            "enabled": settings.ssh_enabled,
            "host": settings.ssh_host,
            "port": settings.ssh_port,
            "user": settings.ssh_user,
            "password": settings.ssh_password,
            "local_port": settings.ssh_local_port,
            "remote_host": settings.ssh_remote_host,
            "remote_port": settings.ssh_remote_port,
        }
        storage_config["minio"] = {
            "enabled": settings.minio_enabled,
            "public_url": settings.minio_public_url,
            "endpoint": settings.minio_endpoint,
            "access_key": settings.minio_access_key,
            "secret_key": settings.minio_secret_key,
            "secure": settings.minio_secure,
            "bucket": settings.minio_bucket,
        }
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
                run_id=run_id,
            )
            return runner.run()
        finally:
            RUN_FUTURES.pop(run_id, None)

    def _resolve_device_serial(
        self,
        *,
        requested_device_serial: str | None,
        active_device_map: dict[str, dict[str, Any]],
    ) -> str:
        online_devices = {
            device.serial: device
            for device in self._list_online_devices()
            if device.state == "device"
        }

        if requested_device_serial:
            if requested_device_serial not in online_devices:
                raise ConfigError(f"指定设备不可用：{requested_device_serial}")
            active_run = active_device_map.get(requested_device_serial)
            if active_run is not None and active_run["status"] in ACTIVE_RUN_STATUSES:
                raise RuntimeError(f"设备 {requested_device_serial} 正在运行任务：#{active_run['id']}")
            return requested_device_serial

        for serial in online_devices:
            if serial not in active_device_map:
                return serial

        raise RuntimeError("当前没有空闲在线设备，请等待现有任务完成后重试。")

    def _list_online_devices(self) -> list[DeviceInfo]:
        settings = self.settings_service.get_settings()
        adb_manager = AdbManager(settings.adb_path or None)
        device_manager = DeviceManager(adb_manager)
        return device_manager.discover_devices()

    def _mark_run_schedule_failed(self, run_id: int, device_serial: str, error_message: str) -> None:
        store = self.store_factory.create_result_store(logger_name="run_service")
        try:
            store.finish_run(
                run_id,
                status="failed",
                finished_at=format_datetime(None),
                artifact_dir="",
                result={
                    "status": "failed",
                    "run_id": run_id,
                    "device_serial": device_serial,
                    "error_message": f"任务调度失败：{error_message}",
                },
                error_message=f"任务调度失败：{error_message}",
                mysql_run_id=run_id,
                device_serial=device_serial,
                items_count=0,
                comment_count=0,
            )
        finally:
            store.close()

    @staticmethod
    def _build_active_device_map(active_runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        device_map: dict[str, dict[str, Any]] = {}
        for run in active_runs:
            serial = str(run.get("device_serial") or "")
            if not serial or serial in device_map:
                continue
            device_map[serial] = run
        return device_map
