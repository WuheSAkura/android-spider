from __future__ import annotations

from datetime import datetime


def now_local() -> datetime:
    """返回带本地时区信息的当前时间。"""
    return datetime.now().astimezone()


def format_datetime(value: datetime | None) -> str:
    """格式化为适合日志和数据库写入的时间字符串。"""
    current = value or now_local()
    return current.strftime("%Y-%m-%d %H:%M:%S")


def format_fs_timestamp(value: datetime | None = None) -> str:
    """格式化为适合文件夹命名的时间戳。"""
    current = value or now_local()
    return current.strftime("%Y-%m-%d_%H%M%S")

