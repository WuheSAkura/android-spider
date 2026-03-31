from __future__ import annotations

import importlib


DEPENDENCY_MODULES: tuple[tuple[str, str], ...] = (
    ("PyYAML", "yaml"),
    ("uiautomator2", "uiautomator2"),
    ("mysql-connector-python", "mysql.connector"),
    ("python-dotenv", "dotenv"),
    ("FastAPI", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("openai", "openai"),
)


def check_module_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def build_dependency_report() -> dict[str, bool]:
    return {name: check_module_available(module_name) for name, module_name in DEPENDENCY_MODULES}
