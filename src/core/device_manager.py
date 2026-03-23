from __future__ import annotations

from dataclasses import dataclass

from src.core.adb_manager import AdbManager, DeviceInfo
from src.utils.exceptions import DeviceNotFoundError


@dataclass(slots=True)
class DoctorReport:
    adb_available: bool
    adb_version: str
    adb_path: str | None
    dependencies: dict[str, bool]
    devices: list[DeviceInfo]
    default_device: DeviceInfo | None


class DeviceManager:
    """负责设备选择与健康检查。"""

    def __init__(self, adb_manager: AdbManager | None = None) -> None:
        self.adb_manager = adb_manager or AdbManager()

    def discover_devices(self) -> list[DeviceInfo]:
        return self.adb_manager.list_devices()

    def get_default_device(self) -> DeviceInfo:
        for device in self.discover_devices():
            if device.state == "device":
                return device
        raise DeviceNotFoundError("没有发现在线的 Android 模拟器或设备，请先启动 AVD 并确认 adb devices 状态为 device。")

    def build_doctor_report(self, dependencies: dict[str, bool]) -> DoctorReport:
        adb_available, adb_version = self.adb_manager.check_available()
        adb_path = self.adb_manager.peek_adb_path()
        devices = self.discover_devices() if adb_available else []
        default_device = next((item for item in devices if item.state == "device"), None)
        return DoctorReport(
            adb_available=adb_available,
            adb_version=adb_version,
            adb_path=adb_path,
            dependencies=dependencies,
            devices=devices,
            default_device=default_device,
        )
