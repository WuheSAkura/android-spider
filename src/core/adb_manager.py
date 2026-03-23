from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src.utils.exceptions import DependencyError, DriverError


@dataclass(slots=True)
class DeviceInfo:
    serial: str
    state: str
    android_version: str | None = None
    model: str | None = None


class AdbManager:
    """负责 ADB 命令调用与设备发现。"""

    def __init__(self, adb_path: str | None = None) -> None:
        self.requested_adb_path = adb_path
        self.resolved_adb_path: str | None = None

    def run(self, args: Sequence[str], timeout: int = 15, check: bool = False) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.get_adb_path(), *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
        except FileNotFoundError as exc:
            raise DependencyError(
                "未找到 adb。请确认 Android SDK Platform Tools 已安装，并使用 --adb-path 指定，或将 platform-tools 加入当前终端的 PATH。"
            ) from exc
        except subprocess.SubprocessError as exc:
            raise DriverError(f"执行 adb 命令失败：{' '.join(args)}") from exc

    def check_available(self) -> tuple[bool, str]:
        try:
            result = self.run(["version"], timeout=10, check=True)
        except (DependencyError, DriverError):
            return False, ""
        return True, (result.stdout or result.stderr).strip()

    def get_device_property(self, serial: str, prop: str) -> str | None:
        result = self.run(["-s", serial, "shell", "getprop", prop], timeout=10)
        if result.returncode != 0:
            return None
        value = (result.stdout or "").strip()
        return value or None

    def get_adb_path(self) -> str:
        if self.resolved_adb_path:
            return self.resolved_adb_path

        candidate = self._discover_adb_path()
        if candidate is None:
            raise DependencyError(
                "未找到 adb。已检查显式参数、ANDROID_SPIDER_ADB_PATH、ADB_PATH、ANDROID_SDK_ROOT、ANDROID_HOME、PATH 以及常见 Windows 目录。"
            )
        self.resolved_adb_path = candidate
        return candidate

    def peek_adb_path(self) -> str | None:
        try:
            return self.get_adb_path()
        except DependencyError:
            return None

    def list_devices(self) -> list[DeviceInfo]:
        result = self.run(["devices"], timeout=10)
        if result.returncode != 0:
            raise DriverError(f"adb devices 执行失败：{result.stderr.strip()}")

        devices: list[DeviceInfo] = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            android_version = None
            model = None
            if state == "device":
                android_version = self.get_device_property(serial, "ro.build.version.release")
                model = self.get_device_property(serial, "ro.product.model")
            devices.append(
                DeviceInfo(
                    serial=serial,
                    state=state,
                    android_version=android_version,
                    model=model,
                )
            )
        return devices

    def _discover_adb_path(self) -> str | None:
        for candidate in self._iter_adb_candidates():
            resolved = self._resolve_candidate(candidate)
            if resolved:
                return resolved
        return None

    def _iter_adb_candidates(self) -> list[str]:
        candidates: list[str] = []

        if self.requested_adb_path:
            candidates.append(self.requested_adb_path)

        for env_name in ("ANDROID_SPIDER_ADB_PATH", "ADB_PATH"):
            env_value = os.environ.get(env_name)
            if env_value:
                candidates.append(env_value)

        for env_name in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            sdk_root = os.environ.get(env_name)
            if sdk_root:
                candidates.append(str(Path(sdk_root) / "platform-tools" / self._adb_filename()))

        candidates.append("adb")

        local_app_data = os.environ.get("LOCALAPPDATA")
        common_candidates = [
            r"D:\adb\platform-tools\adb.exe",
            r"C:\adb\platform-tools\adb.exe",
        ]
        if local_app_data:
            common_candidates.append(str(Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / self._adb_filename()))
        candidates.extend(common_candidates)
        return candidates

    def _resolve_candidate(self, candidate: str) -> str | None:
        if not candidate:
            return None

        which_result = shutil.which(candidate)
        if which_result:
            return which_result

        path_candidate = Path(candidate).expanduser()
        if path_candidate.exists():
            return str(path_candidate)
        return None

    @staticmethod
    def _adb_filename() -> str:
        return "adb.exe" if os.name == "nt" else "adb"
