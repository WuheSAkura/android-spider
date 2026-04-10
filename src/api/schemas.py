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
    busy: bool = False
    active_run_id: int | None = None
    active_run_status: str = ""


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


class RunRecordResponse(BaseModel):
    id: int
    local_run_id: int
    item_index: int
    platform: str
    record_type: str
    keyword: str = ""
    title: str = ""
    content_text: str = ""
    author_name: str = ""
    author_id: str = ""
    location_text: str = ""
    ip_location: str = ""
    published_text: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
    raw_visible_texts: list[str] = Field(default_factory=list)
    created_at: str = ""


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


class KeywordCreatePayload(BaseModel):
    keyword: str
    meaning: str = ""
    sort_order: int = 0


class KeywordUpdatePayload(BaseModel):
    keyword: str | None = None
    meaning: str | None = None
    subcategory_id: int | None = None
    sort_order: int | None = None


class KeywordResponse(BaseModel):
    id: int
    keyword: str
    meaning: str
    category_id: int
    subcategory_id: int
    category_name: str = ""
    subcategory_name: str = ""
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""


class KeywordSubcategoryCreatePayload(BaseModel):
    name: str
    description: str = ""
    sort_order: int = 0


class KeywordSubcategoryUpdatePayload(BaseModel):
    name: str | None = None
    description: str | None = None
    sort_order: int | None = None


class KeywordSubcategoryResponse(BaseModel):
    id: int
    name: str
    description: str = ""
    category_id: int
    sort_order: int = 0
    keywords: list[KeywordResponse] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class KeywordCategoryCreatePayload(BaseModel):
    name: str
    description: str = ""
    sort_order: int = 0


class KeywordCategoryUpdatePayload(BaseModel):
    name: str | None = None
    description: str | None = None
    sort_order: int | None = None


class KeywordCategoryResponse(BaseModel):
    id: int
    name: str
    description: str = ""
    sort_order: int = 0
    subcategories: list[KeywordSubcategoryResponse] = Field(default_factory=list)
    keywords: list[KeywordResponse] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class JargonAnalysisCreateRequest(BaseModel):
    source_type: Literal["xianyu", "xhs"]
    source_task_id: int
    keyword_id: int


class JargonSourceDatasetResponse(BaseModel):
    source_type: Literal["xianyu", "xhs"]
    source_task_id: int
    source_task_name: str
    label: str
    record_count: int
    created_at: str = ""


class JargonTaskResponse(BaseModel):
    id: int
    source_type: Literal["xianyu", "xhs"]
    source_task_id: int
    source_task_name: str
    keyword_id: int
    keyword_name: str
    keyword_meaning: str
    category_name: str = ""
    subcategory_name: str = ""
    status: str
    total_records: int = 0
    processed_records: int = 0
    matched_records: int = 0
    error_message: str = ""
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    updated_at: str = ""


class JargonTaskListResponse(BaseModel):
    items: list[JargonTaskResponse] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    total_pages: int


class MatchedKeywordResponse(BaseModel):
    task_id: int
    keyword_id: int
    keyword: str
    meaning: str
    confidence: float


class JargonSourceRecordResponse(BaseModel):
    id: int
    platform: str
    source_task_id: int
    source_label: str = ""
    title: str = ""
    content: str = ""
    image_url: str = ""
    price: str | float | int | None = None
    price_label: str = ""
    link: str = ""
    created_at: str = ""
    matched_keywords: list[MatchedKeywordResponse] = Field(default_factory=list)
    analysis_status: str
    want_count: int | None = None
    view_count: int | None = None
    seller_name: str = ""
    seller_region: str = ""
    author: str = ""
    publish_time: str = ""
    likes: int = 0
    collects: int = 0
    comment_count: int = 0
    topics: list[str] = Field(default_factory=list)
    ip_location: str = ""


class JargonSourceRecordListResponse(BaseModel):
    items: list[JargonSourceRecordResponse] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    total_pages: int


class JargonTaskResultItemResponse(BaseModel):
    id: int
    source_record_id: int
    is_match: bool
    confidence: float
    reason: str = ""
    record: JargonSourceRecordResponse


class JargonTaskResultsResponse(BaseModel):
    task: JargonTaskResponse
    items: list[JargonTaskResultItemResponse] = Field(default_factory=list)


class HitTracingMatchResponse(BaseModel):
    task_id: int
    keyword_id: int
    keyword: str
    meaning: str
    confidence: float
    reason: str = ""
    category_name: str = ""
    subcategory_name: str = ""
    task_created_at: str = ""
    task_completed_at: str = ""


class HitTracingRecordSummaryResponse(BaseModel):
    id: int
    local_run_id: int
    item_index: int
    platform: str
    record_type: str
    source_task_id: int
    source_label: str = ""
    title: str = ""
    content: str = ""
    image_url: str = ""
    price: str | float | int | None = None
    price_label: str = ""
    link: str = ""
    created_at: str = ""
    match_count: int = 0
    top_confidence: float = 0
    matches: list[HitTracingMatchResponse] = Field(default_factory=list)
    want_count: int | None = None
    view_count: int | None = None
    seller_name: str = ""
    seller_region: str = ""
    author: str = ""
    publish_time: str = ""
    likes: int = 0
    collects: int = 0
    comment_count: int = 0
    topics: list[str] = Field(default_factory=list)
    ip_location: str = ""


class HitTracingRecordListResponse(BaseModel):
    items: list[HitTracingRecordSummaryResponse] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    total_pages: int


class HitTracingRecordDetailResponse(HitTracingRecordSummaryResponse):
    author_name: str = ""
    author_id: str = ""
    location_text: str = ""
    published_text: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
    raw_visible_texts: list[str] = Field(default_factory=list)


class FileEntryResponse(BaseModel):
    name: str
    path: str
    relative_path: str
    root: str
    size: int
    time: str
    type: str


class FileDeleteRequest(BaseModel):
    path: str


class FileBatchDeleteRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
