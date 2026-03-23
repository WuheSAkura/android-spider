from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TemplateFieldResponse(BaseModel):
    key: str
    label: str
    field_type: str
    required: bool
    min_value: int | float | None = None
    max_value: int | float | None = None
    step: int | float | None = None
    description: str = ""


class TaskTemplateResponse(BaseModel):
    template_id: str
    display_name: str
    description: str
    adapter: str
    package_name: str
    platform: str
    default_options: dict[str, Any] = Field(default_factory=dict)
    light_smoke_overrides: dict[str, Any] = Field(default_factory=dict)
    fields: list[TemplateFieldResponse] = Field(default_factory=list)


class AppSettingsPayload(BaseModel):
    adb_path: str = ""
    output_dir: str = "artifacts"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "android_spider"
    mysql_charset: str = "utf8mb4"


class RunCreateRequest(BaseModel):
    template_id: str
    device_serial: str | None = None
    run_mode: Literal["normal", "light_smoke"] = "normal"
    adapter_options: dict[str, Any] = Field(default_factory=dict)


class DeviceResponse(BaseModel):
    serial: str
    state: str
    android_version: str | None = None
    model: str | None = None


class DoctorResponse(BaseModel):
    adb_available: bool
    adb_version: str
    adb_path: str | None = None
    dependencies: dict[str, bool] = Field(default_factory=dict)
    devices: list[DeviceResponse] = Field(default_factory=list)
    default_device_serial: str | None = None


class RunSummaryResponse(BaseModel):
    id: int
    task_name: str
    adapter: str
    platform: str
    package_name: str
    run_mode: str
    status: str
    device_serial: str = ""
    requested_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    artifact_dir: str = ""
    log_path: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    mysql_run_id: int | None = None
    items_count: int = 0
    comment_count: int = 0
    cancel_requested: bool = False
    created_at: str = ""
    updated_at: str = ""


class RunLogsResponse(BaseModel):
    path: str = ""
    content: str = ""
    line_count: int = 0


class ArtifactResponse(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int
    kind: str
