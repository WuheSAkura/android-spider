from __future__ import annotations

from pathlib import Path
from typing import Any


class FileService:
    """本地产物文件管理，只允许操作项目输出目录。"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.allowed_roots = [
            project_root / "artifacts",
            project_root / "exports",
        ]

    def list_files(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for root in self.allowed_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                stat = path.stat()
                items.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "relative_path": str(path.relative_to(self.project_root)),
                        "root": root.name,
                        "size": int(stat.st_size),
                        "time": self._format_mtime(stat.st_mtime),
                        "type": self._detect_type(path),
                    }
                )

        items.sort(key=lambda item: (item["time"], item["path"]), reverse=True)
        return items

    def delete_file(self, target_path: str) -> None:
        path = self._validate_file_path(target_path)
        path.unlink()

    def delete_files(self, target_paths: list[str]) -> None:
        if not target_paths:
            raise ValueError("请选择至少一个文件")

        # 先统一校验，确保不会删到一半失败。
        paths = [self._validate_file_path(target_path) for target_path in target_paths]
        for path in paths:
            path.unlink()

    @staticmethod
    def _format_mtime(timestamp: float) -> str:
        from datetime import datetime

        return datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _detect_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix in {".csv", ".xlsx", ".xls"}:
            return "spreadsheet"
        if suffix in {".log", ".txt"}:
            return "text"
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return "image"
        if suffix == ".xml":
            return "xml"
        return "file"

    def _validate_file_path(self, target_path: str) -> Path:
        path = Path(target_path).resolve()
        if not path.exists():
            raise FileNotFoundError("文件不存在")
        if not path.is_file():
            raise IsADirectoryError("当前仅支持删除文件")
        if not any(self._is_relative_to(path, root.resolve()) for root in self.allowed_roots):
            raise PermissionError("禁止删除输出目录之外的文件")
        return path

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True
