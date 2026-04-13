from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.minio_service import MinIOArtifactService
from src.services.settings_service import SettingsService
from src.storage.mysql_analysis_store import MySQLAnalysisStore
from src.storage.result_store import MySQLResultStore


def load_json(raw_value: Any) -> Any:
    if raw_value in (None, ""):
        return None
    if isinstance(raw_value, (dict, list)):
        return raw_value
    try:
        return json.loads(str(raw_value))
    except json.JSONDecodeError:
        return None


def row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    result_json = load_json(row["result_json"])
    config_json = load_json(row["config_json"])
    run_id = int(row["id"])
    return {
        "id": run_id,
        "task_name": str(row["task_name"]),
        "adapter": str(row["adapter"] or ""),
        "platform": str(row["platform"] or ""),
        "package_name": str(row["package_name"] or ""),
        "run_mode": str(row["run_mode"] or "normal"),
        "status": str(row["status"]),
        "device_serial": str(row["device_serial"] or ""),
        "requested_at": str(row["requested_at"] or ""),
        "started_at": str(row["started_at"] or ""),
        "finished_at": str(row["finished_at"] or ""),
        "artifact_dir": str(row["artifact_dir"] or ""),
        "log_path": str(row["log_path"] or ""),
        "config": config_json if isinstance(config_json, dict) else {},
        "result": result_json if isinstance(result_json, dict) else {},
        "error_message": str(row["error_message"] or ""),
        "mysql_run_id": int(row["mysql_run_id"]) if row["mysql_run_id"] is not None else run_id,
        "items_count": int(row["items_count"] or 0),
        "comment_count": int(row["comment_count"] or 0),
        "cancel_requested": bool(int(row["cancel_requested"] or 0)),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "local_run_id": int(row["local_run_id"]),
        "item_index": int(row["item_index"]),
        "platform": str(row["platform"]),
        "record_type": str(row["record_type"]),
        "keyword": str(row["keyword"] or ""),
        "title": str(row["title"] or ""),
        "content_text": str(row["content_text"] or ""),
        "author_name": str(row["author_name"] or ""),
        "author_id": str(row["author_id"] or ""),
        "location_text": str(row["location_text"] or ""),
        "ip_location": str(row["ip_location"] or ""),
        "published_text": str(row["published_text"] or ""),
        "metrics": load_json(row["metrics_json"]) or {},
        "extra": load_json(row["extra_json"]) or {},
        "raw_visible_texts": load_json(row["raw_visible_texts_json"]) or [],
        "created_at": str(row["created_at"] or ""),
    }


def row_to_jargon_result(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "task_id": int(row["task_id"]),
        "source_type": str(row["source_type"]),
        "source_record_id": int(row["source_record_id"]),
        "is_match": bool(int(row["is_match"] or 0)),
        "confidence": float(row["confidence"] or 0),
        "reason": str(row["reason"] or ""),
        "raw_response": load_json(row["raw_response_json"]) or {},
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将本地 SQLite 历史迁移到共享 MySQL 与 MinIO。")
    parser.add_argument(
        "--sqlite-path",
        default=str(PROJECT_ROOT / "data" / "local_runs.sqlite3"),
        help="本地 SQLite 文件路径",
    )
    parser.add_argument(
        "--skip-artifacts",
        action="store_true",
        help="只迁移结构化数据，不上传历史产物到 MinIO",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path).resolve()
    if not sqlite_path.exists():
        raise FileNotFoundError(f"未找到 SQLite 文件：{sqlite_path}")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("sqlite_to_mysql_migrator")
    settings = SettingsService(sqlite_path).get_settings()

    result_store = MySQLResultStore(
        settings.to_mysql_config(),
        logger,
        ssh_config=settings.to_ssh_config(),
    )
    minio_service = MinIOArtifactService(settings.to_minio_config(), logger)
    analysis_store: MySQLAnalysisStore | None = None

    sqlite_connection = sqlite3.connect(sqlite_path, check_same_thread=False, timeout=30)
    sqlite_connection.row_factory = sqlite3.Row

    try:
        migrated_counts = {
            "task_runs": 0,
            "collected_records": 0,
            "keyword_categories": 0,
            "keyword_subcategories": 0,
            "keywords": 0,
            "jargon_analysis_tasks": 0,
            "jargon_analysis_results": 0,
            "run_artifacts": 0,
        }

        cursor = sqlite_connection.cursor()

        result_store.connect()

        cursor.execute("SELECT * FROM task_runs ORDER BY id ASC")
        run_rows = cursor.fetchall()
        runs = [row_to_run(row) for row in run_rows]
        for run in runs:
            result_store.upsert_run_row(run)
        migrated_counts["task_runs"] = len(runs)

        cursor.execute("SELECT * FROM collected_records ORDER BY id ASC")
        record_rows = cursor.fetchall()
        for row in record_rows:
            result_store.upsert_collected_record_row(row_to_record(row))
        migrated_counts["collected_records"] = len(record_rows)

        if not args.skip_artifacts and minio_service.enabled():
            for run in runs:
                artifact_dir_value = str(run.get("artifact_dir") or "")
                if not artifact_dir_value:
                    continue
                artifact_dir = Path(artifact_dir_value)
                if not artifact_dir.exists() or not artifact_dir.is_dir():
                    logger.warning("跳过不存在的产物目录：%s", artifact_dir)
                    continue

                uploads = minio_service.plan_uploads(artifact_dir, task_name=str(run.get("task_name") or f"run_{run['id']}"))
                if not uploads:
                    continue
                minio_service.upload_records(uploads)
                result_store.save_artifact_uploads(int(run["id"]), uploads)
                migrated_counts["run_artifacts"] += len(uploads)

        result_store.close()

        analysis_store = MySQLAnalysisStore(
            settings.to_mysql_config(),
            logger,
            ssh_config=settings.to_ssh_config(),
        )
        analysis_store.connect()

        cursor.execute("SELECT * FROM keyword_categories ORDER BY id ASC")
        category_rows = cursor.fetchall()
        for row in category_rows:
            analysis_store.upsert_keyword_category_row(dict(row))
        migrated_counts["keyword_categories"] = len(category_rows)

        cursor.execute("SELECT * FROM keyword_subcategories ORDER BY id ASC")
        subcategory_rows = cursor.fetchall()
        for row in subcategory_rows:
            analysis_store.upsert_keyword_subcategory_row(dict(row))
        migrated_counts["keyword_subcategories"] = len(subcategory_rows)

        cursor.execute("SELECT * FROM keywords ORDER BY id ASC")
        keyword_rows = cursor.fetchall()
        for row in keyword_rows:
            analysis_store.upsert_keyword_row(dict(row))
        migrated_counts["keywords"] = len(keyword_rows)

        cursor.execute("SELECT * FROM jargon_analysis_tasks ORDER BY id ASC")
        jargon_task_rows = cursor.fetchall()
        for row in jargon_task_rows:
            analysis_store.upsert_jargon_task_row(dict(row))
        migrated_counts["jargon_analysis_tasks"] = len(jargon_task_rows)

        cursor.execute("SELECT * FROM jargon_analysis_results ORDER BY id ASC")
        jargon_result_rows = cursor.fetchall()
        for row in jargon_result_rows:
            analysis_store.upsert_jargon_result_row(row_to_jargon_result(row))
        migrated_counts["jargon_analysis_results"] = len(jargon_result_rows)

        logger.info("迁移完成：%s", migrated_counts)
        return 0
    finally:
        sqlite_connection.close()
        if analysis_store is not None:
            analysis_store.close()
        result_store.close()


if __name__ == "__main__":
    raise SystemExit(main())
