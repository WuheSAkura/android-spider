from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.core.driver import AndroidDriver
from src.utils.time_utils import format_fs_timestamp, now_local


@dataclass(slots=True)
class PageCapture:
    screenshot_path: str | None = None
    hierarchy_path: str | None = None
    visible_texts_path: str | None = None
    visible_texts: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArtifactManager:
    """负责本次任务运行的目录和文件写入。"""

    def __init__(self, output_root: Path, task_name: str) -> None:
        self.output_root = output_root
        self.task_name = task_name
        self.run_dir = self.output_root / f"{format_fs_timestamp(now_local())}_{self._sanitize_name(task_name)}"
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_file(self) -> Path:
        return self.run_dir / "run.log"

    def write_json(self, filename: str, data: Any) -> Path:
        path = self.run_dir / filename
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        return path

    def write_text(self, filename: str, content: str) -> Path:
        path = self.run_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def write_csv(
        self,
        output_dir: Path,
        *,
        filename_prefix: str,
        fieldnames: Sequence[str],
        rows: Iterable[Mapping[str, Any]],
    ) -> Path:
        export_dir = Path(output_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._sanitize_name(filename_prefix)}_{format_fs_timestamp(now_local())}.csv"
        path = export_dir / filename

        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(fieldnames))
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        fieldname: self._stringify_csv_value(row.get(fieldname))
                        for fieldname in fieldnames
                    }
                )

        return path

    def capture_page(
        self,
        driver: AndroidDriver,
        *,
        save_screenshot: bool,
        save_hierarchy: bool,
        save_visible_texts: bool,
        prefix: str = "",
    ) -> PageCapture:
        filename_prefix = f"{prefix}_" if prefix else ""
        hierarchy_xml = driver.get_hierarchy_xml()
        capture = PageCapture()

        if save_screenshot:
            screenshot_path = self.run_dir / f"{filename_prefix}screenshot.png"
            driver.screenshot(screenshot_path)
            capture.screenshot_path = str(screenshot_path)

        if save_hierarchy:
            hierarchy_path = self.run_dir / f"{filename_prefix}hierarchy.xml"
            hierarchy_path.write_text(hierarchy_xml, encoding="utf-8")
            capture.hierarchy_path = str(hierarchy_path)

        visible_texts = driver.get_visible_texts(hierarchy_xml)
        capture.visible_texts = visible_texts
        if save_visible_texts:
            visible_texts_path = self.run_dir / f"{filename_prefix}visible_texts.json"
            self.write_json(visible_texts_path.name, visible_texts)
            capture.visible_texts_path = str(visible_texts_path)

        return capture

    @staticmethod
    def _sanitize_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "task"

    @staticmethod
    def _stringify_csv_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
