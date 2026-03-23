from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from src.adapters import ADAPTER_REGISTRY
from src.adapters.base_adapter import AdapterPartialResult, AdapterRunResult, BaseAdapter
from src.core.actions import ActionExecutor
from src.core.adb_manager import AdbManager
from src.core.artifacts import ArtifactManager
from src.core.device_manager import DeviceManager
from src.core.driver import AndroidDriver
from src.models.collected_record import CollectedRecord
from src.models.task_models import TaskConfig
from src.storage.result_store import MySQLResultStore
from src.storage.sqlite_store import SQLiteStore
from src.utils.exceptions import ConfigError, TaskCancelledError
from src.utils.logger import setup_logger
from src.utils.time_utils import format_datetime, now_local


class TaskRunner:
    """负责将配置、驱动、Adapter 和存储串成完整执行闭环。"""

    def __init__(
        self,
        task_config: TaskConfig,
        adb_manager: AdbManager | None = None,
        *,
        local_run_id: int | None = None,
    ) -> None:
        self.task_config = task_config
        self.adb_manager = adb_manager or AdbManager()
        self.device_manager = DeviceManager(self.adb_manager)
        self.adapter = self._load_adapter(task_config.adapter)
        self.local_run_id = local_run_id

    def run(self) -> dict[str, Any]:
        logger = setup_logger("task_runner.bootstrap")
        artifacts: ArtifactManager | None = None
        sqlite_store: SQLiteStore | None = None
        mysql_store: MySQLResultStore | None = None

        started_at = format_datetime(now_local())
        device_serial = "unknown"
        mysql_run_id: int | None = None
        driver: AndroidDriver | None = None

        try:
            artifacts = ArtifactManager(self.task_config.output_dir, self.task_config.task_name)
            logger = setup_logger(f"task_runner.{self.task_config.task_name}", artifacts.log_file)
            sqlite_store = SQLiteStore(self.task_config.storage.sqlite_path)
            if self.local_run_id is not None:
                sqlite_store.mark_run_started(self.local_run_id, started_at=started_at, log_path=str(artifacts.log_file))

            mysql_store = MySQLResultStore(self.task_config.storage.mysql, logger)
            self.adapter.validate_config(self.task_config)
            self._check_cancelled(sqlite_store)

            device = self._select_device()
            device_serial = device.serial
            if self.local_run_id is not None:
                sqlite_store.update_run_device(self.local_run_id, device_serial)

            mysql_store.connect()
            mysql_run_id = mysql_store.create_run(self.task_config.task_name, device_serial, "running", started_at)

            driver = AndroidDriver(device_serial, logger).connect()
            if not driver.is_alive():
                raise ConfigError("设备连接成功但驱动不可用，请检查 uiautomator2 初始化状态。")

            self.adapter.before_run(self.task_config, logger)
            self._check_cancelled(sqlite_store)
            driver.start_app(self.task_config.package_name, self.task_config.launch_activity)
            self._sleep_with_cancel(sqlite_store, self.task_config.startup_wait_seconds)

            custom_result = self.adapter.execute_task(
                driver=driver,
                task_config=self.task_config,
                artifacts=artifacts,
                logger=logger,
                mysql_store=mysql_store,
                run_id=mysql_run_id,
                check_cancelled=lambda: self._check_cancelled(sqlite_store),
            )

            last_visible_texts: list[str] = []
            last_page_name = "current_page"
            result: dict[str, Any]
            collected_records: list[CollectedRecord] = []

            if custom_result is None:
                executor = ActionExecutor(driver, self.task_config, artifacts, logger)
                for step in self.task_config.steps:
                    self._check_cancelled(sqlite_store)
                    step_result = executor.execute(step)
                    self._check_cancelled(sqlite_store)
                    if step_result and "capture" in step_result:
                        capture_data = step_result["capture"]
                        last_page_name = str(step_result.get("page_name", last_page_name))
                        last_visible_texts = list(capture_data.get("visible_texts") or [])

                if not last_visible_texts and (
                    self.task_config.save_screenshot or self.task_config.save_hierarchy or self.task_config.save_visible_texts
                ):
                    self._check_cancelled(sqlite_store)
                    final_capture = artifacts.capture_page(
                        driver,
                        save_screenshot=self.task_config.save_screenshot,
                        save_hierarchy=self.task_config.save_hierarchy,
                        save_visible_texts=self.task_config.save_visible_texts,
                        prefix="final",
                    )
                    last_page_name = "final"
                    last_visible_texts = final_capture.visible_texts or []

                result = self.adapter.build_result(
                    task_config=self.task_config,
                    device_serial=device_serial,
                    artifact_dir=artifacts.run_dir,
                    page_name=last_page_name,
                    visible_texts=last_visible_texts,
                )
            else:
                last_page_name = custom_result.page_name
                last_visible_texts = custom_result.visible_texts
                collected_records = custom_result.collected_records
                result = custom_result.result

            result["run_id"] = mysql_run_id
            if self.local_run_id is not None:
                result["local_run_id"] = self.local_run_id
            result_path = artifacts.write_json("result.json", result)
            mysql_store.save_collected_items(mysql_run_id, last_page_name, last_visible_texts)
            mysql_store.save_collected_records(mysql_run_id, collected_records)
            mysql_store.finish_run(
                mysql_run_id,
                status="success",
                finished_at=format_datetime(now_local()),
                artifact_dir=str(artifacts.run_dir),
                error_message=None,
            )
            if self.local_run_id is not None:
                sqlite_store.replace_collected_records(self.local_run_id, collected_records)
                sqlite_store.finish_run(
                    self.local_run_id,
                    status="success",
                    finished_at=format_datetime(now_local()),
                    artifact_dir=str(artifacts.run_dir),
                    result=result,
                    error_message=None,
                    mysql_run_id=mysql_run_id,
                    device_serial=device_serial,
                    items_count=self._extract_int(result.get("item_count")),
                    comment_count=self._extract_int(result.get("comment_count")),
                )
            self.adapter.after_run(self.task_config, logger)
            logger.info("任务执行成功，结果文件：%s", result_path)
            return result
        except TaskCancelledError as exc:
            logger.info("任务已取消：%s", exc)
            return self._finalize_terminated_run(
                status="cancelled",
                error_message=str(exc),
                logger=logger,
                artifacts=artifacts,
                sqlite_store=sqlite_store,
                mysql_store=mysql_store,
                mysql_run_id=mysql_run_id,
                driver=driver,
                device_serial=device_serial,
                save_traceback=False,
            )
        except (Exception, KeyboardInterrupt) as exc:
            logger.exception("任务执行失败。")
            return self._finalize_terminated_run(
                status="failed",
                error_message=str(exc),
                logger=logger,
                artifacts=artifacts,
                sqlite_store=sqlite_store,
                mysql_store=mysql_store,
                mysql_run_id=mysql_run_id,
                driver=driver,
                device_serial=device_serial,
                save_traceback=True,
            )
        finally:
            if driver is not None:
                try:
                    driver.stop_app(self.task_config.package_name)
                except Exception:
                    logger.debug("停止应用失败，忽略。", exc_info=True)
            if mysql_store is not None:
                mysql_store.close()
            if sqlite_store is not None:
                sqlite_store.close()

    def dump_current_page(self, output_dir: Path) -> dict[str, Any]:
        artifacts = ArtifactManager(output_dir, "dump_page")
        logger = setup_logger("dump_page", artifacts.log_file)
        device = self._select_device()
        driver = AndroidDriver(device.serial, logger).connect()

        try:
            capture = artifacts.capture_page(
                driver,
                save_screenshot=True,
                save_hierarchy=True,
                save_visible_texts=True,
                prefix="dump",
            )
            result = {
                "status": "success",
                "device_serial": device.serial,
                "artifact_dir": str(artifacts.run_dir),
                "capture": capture.to_dict(),
            }
            artifacts.write_json("result.json", result)
            return result
        finally:
            logger.info("当前页面导出完成：%s", artifacts.run_dir)

    def _finalize_terminated_run(
        self,
        *,
        status: str,
        error_message: str,
        logger,
        artifacts: ArtifactManager | None,
        sqlite_store: SQLiteStore | None,
        mysql_store: MySQLResultStore | None,
        mysql_run_id: int | None,
        driver: AndroidDriver | None,
        device_serial: str,
        save_traceback: bool,
    ) -> dict[str, Any]:
        traceback_text = traceback.format_exc() if save_traceback else ""
        artifact_dir = str(artifacts.run_dir) if artifacts is not None else ""
        partial_result: AdapterPartialResult | None = None

        if driver is not None and artifacts is not None:
            try:
                artifacts.capture_page(
                    driver,
                    save_screenshot=True,
                    save_hierarchy=True,
                    save_visible_texts=True,
                    prefix="cancelled" if status == "cancelled" else "failure",
                )
            except Exception:
                logger.exception("保存终止现场失败。")

        if artifacts is not None:
            try:
                partial_result = self.adapter.export_partial_result(
                    task_config=self.task_config,
                    artifacts=artifacts,
                    logger=logger,
                )
            except Exception:
                logger.exception("导出部分采集结果失败。")

        result: dict[str, Any] = {
            "task_name": self.task_config.task_name,
            "status": status,
            "device_serial": device_serial,
            "artifact_dir": artifact_dir,
            "error_message": error_message,
        }
        if self.local_run_id is not None:
            result["local_run_id"] = self.local_run_id
        if mysql_run_id is not None:
            result["run_id"] = mysql_run_id
        if partial_result is not None:
            result["partial_exported"] = True
            result.update(partial_result.result)

        if artifacts is not None:
            artifacts.write_json("result.json", result)
            if save_traceback and traceback_text:
                artifacts.write_text("traceback.txt", traceback_text)

        finished_at = format_datetime(now_local())
        partial_records = partial_result.collected_records if partial_result is not None else []

        if mysql_run_id is not None and mysql_store is not None:
            try:
                if partial_records:
                    mysql_store.save_collected_records(mysql_run_id, partial_records)
                mysql_store.finish_run(
                    mysql_run_id,
                    status=status,
                    finished_at=finished_at,
                    artifact_dir=artifact_dir,
                    error_message=error_message,
                )
            except Exception:
                logger.exception("写入 MySQL 终止状态时出现异常。")

        if sqlite_store is not None and self.local_run_id is not None:
            sqlite_store.replace_collected_records(self.local_run_id, partial_records)
            sqlite_store.finish_run(
                self.local_run_id,
                status=status,
                finished_at=finished_at,
                artifact_dir=artifact_dir,
                result=result,
                error_message=error_message,
                mysql_run_id=mysql_run_id,
                device_serial=device_serial,
                items_count=self._extract_partial_count(result, partial_result, "partial_item_count"),
                comment_count=self._extract_partial_count(result, partial_result, "partial_comment_count"),
            )

        return result

    def _select_device(self):
        if self.task_config.device_serial:
            for device in self.device_manager.discover_devices():
                if device.serial == self.task_config.device_serial and device.state == "device":
                    return device
            raise ConfigError(f"指定设备不可用：{self.task_config.device_serial}")
        return self.device_manager.get_default_device()

    def _check_cancelled(self, sqlite_store: SQLiteStore | None) -> None:
        if sqlite_store is None or self.local_run_id is None:
            return
        if sqlite_store.is_cancel_requested(self.local_run_id):
            raise TaskCancelledError("任务已收到停止指令，准备结束本次采集。")

    def _sleep_with_cancel(self, sqlite_store: SQLiteStore | None, seconds: float) -> None:
        remaining = max(seconds, 0)
        while remaining > 0:
            self._check_cancelled(sqlite_store)
            step = min(remaining, 0.25)
            time_sleep(step)
            remaining -= step
        self._check_cancelled(sqlite_store)

    def _load_adapter(self, adapter_name: str) -> BaseAdapter:
        adapter_class = ADAPTER_REGISTRY.get(adapter_name)
        if adapter_class is None:
            raise ConfigError(f"未注册的 adapter：{adapter_name}")
        return adapter_class()

    @staticmethod
    def _extract_int(value: Any) -> int:
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_partial_count(
        result: dict[str, Any],
        partial_result: AdapterPartialResult | None,
        key: str,
    ) -> int:
        if partial_result is not None:
            try:
                return int(partial_result.result.get(key, 0))
            except (TypeError, ValueError):
                return 0
        return TaskRunner._extract_int(result.get(key))


def time_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
