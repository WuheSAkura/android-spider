from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from src.core.adb_manager import AdbManager
from src.core.device_manager import DeviceManager
from src.core.task_runner import TaskRunner
from src.models.task_models import TaskConfig
from src.utils.logger import setup_logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows 本地 Android 模拟器自动化采集基础项目")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="检查 adb、依赖和在线设备状态")
    doctor_parser.add_argument("--adb-path", help="可选，显式指定 adb.exe 路径")

    run_parser = subparsers.add_parser("run", help="执行 YAML 任务")
    run_parser.add_argument("--config", required=True, help="任务配置文件路径")
    run_parser.add_argument("--adb-path", help="可选，显式指定 adb.exe 路径")

    serve_parser = subparsers.add_parser("serve", help="启动本地桌面端 API 服务")
    serve_parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")

    dump_parser = subparsers.add_parser("dump-page", help="导出当前页面截图、层级和文本")
    dump_parser.add_argument("--output-dir", default="artifacts", help="导出目录，默认 artifacts")
    dump_parser.add_argument("--adb-path", help="可选，显式指定 adb.exe 路径")

    return parser


def command_doctor(adb_path: str | None) -> int:
    logger = setup_logger("doctor")
    dependencies = {
        "yaml": _check_module("yaml"),
        "uiautomator2": _check_module("uiautomator2"),
        "mysql.connector": _check_module("mysql.connector"),
    }
    device_manager = DeviceManager(AdbManager(adb_path))
    report = device_manager.build_doctor_report(dependencies)

    print("=== Doctor 检查结果 ===")
    print(f"ADB 可用: {'是' if report.adb_available else '否'}")
    print(f"ADB 路径: {report.adb_path or '未解析到'}")
    if report.adb_version:
        print(f"ADB 版本: {report.adb_version}")

    print("Python 依赖:")
    for name, ok in report.dependencies.items():
        print(f"  - {name}: {'已就绪' if ok else '缺失'}")

    if not report.devices:
        print("在线设备: 未发现")
    else:
        print("设备列表:")
        for item in report.devices:
            version = item.android_version or "未知"
            model = item.model or "未知"
            print(f"  - serial={item.serial}, state={item.state}, android={version}, model={model}")

    if report.default_device:
        print(f"默认设备: {report.default_device.serial}")
    else:
        print("默认设备: 无在线设备")

    all_ok = report.adb_available and all(report.dependencies.values()) and report.default_device is not None
    if not all_ok:
        logger.warning("Doctor 检查未完全通过，请根据输出修复环境。")
        return 1
    logger.info("Doctor 检查通过。")
    return 0


def command_run(config_path: str, adb_path: str | None) -> int:
    from src.utils.config_loader import load_task_config

    task_config = load_task_config(Path(config_path))
    runner = TaskRunner(task_config, AdbManager(adb_path))
    result = runner.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_serve(host: str, port: int) -> int:
    import uvicorn

    uvicorn.run("src.api.app:app", host=host, port=port, reload=False)
    return 0


def command_dump_page(output_dir: str, adb_path: str | None) -> int:
    temp_config = TaskConfig.from_dict(
        {
            "task_name": "dump_page",
            "adapter": "target_app_template",
            "package_name": "com.android.settings",
            "steps": [{"action": "capture", "page_name": "dump"}],
            "output_dir": output_dir,
        }
    )
    runner = TaskRunner(temp_config, AdbManager(adb_path))
    result = runner.dump_current_page(Path(output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _check_module(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "doctor":
            return command_doctor(args.adb_path)
        if args.command == "run":
            return command_run(args.config, args.adb_path)
        if args.command == "serve":
            return command_serve(args.host, args.port)
        if args.command == "dump-page":
            return command_dump_page(args.output_dir, args.adb_path)
    except Exception as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
