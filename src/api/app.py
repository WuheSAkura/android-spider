from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.schemas import (
    AppSettingsPayload,
    ArtifactResponse,
    DeviceResponse,
    DoctorResponse,
    FileBatchDeleteRequest,
    FileDeleteRequest,
    FileEntryResponse,
    HitTracingRecordDetailResponse,
    HitTracingRecordListResponse,
    JargonAnalysisCreateRequest,
    JargonSourceDatasetResponse,
    JargonSourceRecordListResponse,
    JargonTaskListResponse,
    JargonTaskResponse,
    JargonTaskResultsResponse,
    KeywordCategoryCreatePayload,
    KeywordCategoryResponse,
    KeywordCategoryUpdatePayload,
    KeywordCreatePayload,
    KeywordResponse,
    KeywordUpdatePayload,
    KeywordSubcategoryCreatePayload,
    KeywordSubcategoryResponse,
    KeywordSubcategoryUpdatePayload,
    RunCreateRequest,
    RunLogsResponse,
    RunRecordResponse,
    RunSummaryResponse,
    TaskTemplateResponse,
)
from src.core.adb_manager import AdbManager, DeviceInfo
from src.core.device_manager import DeviceManager
from src.services.dictionary_service import DictionaryService
from src.services.file_service import FileService
from src.services.jargon_analysis_service import JargonAnalysisService
from src.services.run_service import RunService
from src.services.settings_service import AppSettings, SettingsService
from src.services.task_template_service import TaskTemplateService
from src.utils.dependency_check import build_dependency_report
from src.utils.exceptions import ConfigError, DependencyError, StorageError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQLITE_PATH = PROJECT_ROOT / "data" / "local_runs.sqlite3"

template_service = TaskTemplateService(PROJECT_ROOT)
settings_service = SettingsService(SQLITE_PATH)
run_service = RunService(PROJECT_ROOT, SQLITE_PATH)
dictionary_service = DictionaryService(SQLITE_PATH)
jargon_analysis_service = JargonAnalysisService(SQLITE_PATH)
file_service = FileService(PROJECT_ROOT)

app = FastAPI(title="Android Spider Local API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    run_service.bootstrap()
    jargon_analysis_service.bootstrap()


@app.get("/api/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/doctor", response_model=DoctorResponse)
def get_doctor_report() -> DoctorResponse:
    settings = settings_service.get_settings()
    adb_manager = AdbManager(settings.adb_path or None)
    device_manager = DeviceManager(adb_manager)
    dependencies = build_dependency_report()
    report = device_manager.build_doctor_report(dependencies)
    device_responses = _to_device_responses(report.devices)
    default_idle_device = next((item for item in device_responses if item.state == "device" and not item.busy), None)
    return DoctorResponse(
        adb_available=report.adb_available,
        adb_version=report.adb_version,
        adb_path=report.adb_path,
        dependencies=report.dependencies,
        devices=device_responses,
        default_device_serial=default_idle_device.serial if default_idle_device is not None else None,
    )


@app.get("/api/system/devices", response_model=list[DeviceResponse])
def list_devices() -> list[DeviceResponse]:
    settings = settings_service.get_settings()
    adb_manager = AdbManager(settings.adb_path or None)
    device_manager = DeviceManager(adb_manager)
    return _to_device_responses(device_manager.discover_devices())


@app.get("/api/task-templates", response_model=list[TaskTemplateResponse])
def list_task_templates() -> list[TaskTemplateResponse]:
    return [TaskTemplateResponse(**template.to_dict()) for template in template_service.list_templates()]


@app.get("/api/settings", response_model=AppSettingsPayload)
def get_settings() -> AppSettingsPayload:
    return AppSettingsPayload(**asdict(settings_service.get_settings()))


@app.put("/api/settings", response_model=AppSettingsPayload)
def save_settings(payload: AppSettingsPayload) -> AppSettingsPayload:
    settings = settings_service.save_settings(AppSettings(**payload.model_dump()))
    return AppSettingsPayload(**asdict(settings))


@app.get("/api/runs", response_model=list[RunSummaryResponse])
def list_runs(limit: int = 100) -> list[RunSummaryResponse]:
    return [RunSummaryResponse(**item) for item in run_service.list_runs(limit=limit)]


@app.post("/api/runs", response_model=RunSummaryResponse, status_code=201)
def create_run(payload: RunCreateRequest) -> RunSummaryResponse:
    try:
        run = run_service.create_run(
            template_id=payload.template_id,
            device_serial=payload.device_serial,
            run_mode=payload.run_mode,
            adapter_options=payload.adapter_options,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (StorageError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=500, detail=f"本地任务库写入失败：{exc}") from exc
    return RunSummaryResponse(**run)


@app.get("/api/runs/{run_id}", response_model=RunSummaryResponse)
def get_run(run_id: int) -> RunSummaryResponse:
    try:
        return RunSummaryResponse(**run_service.get_run(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/cancel", response_model=RunSummaryResponse)
def cancel_run(run_id: int) -> RunSummaryResponse:
    try:
        return RunSummaryResponse(**run_service.request_cancel(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}/records", response_model=list[RunRecordResponse])
def get_run_records(run_id: int) -> list[RunRecordResponse]:
    try:
        return [RunRecordResponse(**item) for item in run_service.get_run_records(run_id)]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}/logs", response_model=RunLogsResponse)
def get_run_logs(run_id: int, tail: int = 200) -> RunLogsResponse:
    try:
        return RunLogsResponse(**run_service.get_run_logs(run_id, tail=tail))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}/artifacts", response_model=list[ArtifactResponse])
def get_run_artifacts(run_id: int) -> list[ArtifactResponse]:
    try:
        return [ArtifactResponse(**item) for item in run_service.get_run_artifacts(run_id)]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/keyword-categories", response_model=list[KeywordCategoryResponse])
def list_keyword_categories() -> list[KeywordCategoryResponse]:
    return [KeywordCategoryResponse(**item) for item in dictionary_service.list_categories()]


@app.post("/api/keyword-categories", response_model=KeywordCategoryResponse, status_code=201)
def create_keyword_category(payload: KeywordCategoryCreatePayload) -> KeywordCategoryResponse:
    try:
        item = dictionary_service.create_category(
            name=payload.name,
            description=payload.description,
            sort_order=payload.sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KeywordCategoryResponse(**item)


@app.put("/api/keyword-categories/{category_id}", response_model=KeywordCategoryResponse)
def update_keyword_category(category_id: int, payload: KeywordCategoryUpdatePayload) -> KeywordCategoryResponse:
    try:
        item = dictionary_service.update_category(category_id, payload.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KeywordCategoryResponse(**item)


@app.delete("/api/keyword-categories/{category_id}", status_code=204)
def delete_keyword_category(category_id: int) -> Response:
    try:
        dictionary_service.delete_category(category_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@app.post("/api/keyword-categories/{category_id}/subcategories", response_model=KeywordSubcategoryResponse, status_code=201)
def create_keyword_subcategory(
    category_id: int,
    payload: KeywordSubcategoryCreatePayload,
) -> KeywordSubcategoryResponse:
    try:
        item = dictionary_service.create_subcategory(
            category_id=category_id,
            name=payload.name,
            description=payload.description,
            sort_order=payload.sort_order,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KeywordSubcategoryResponse(**item)


@app.put("/api/keyword-subcategories/{subcategory_id}", response_model=KeywordSubcategoryResponse)
def update_keyword_subcategory(
    subcategory_id: int,
    payload: KeywordSubcategoryUpdatePayload,
) -> KeywordSubcategoryResponse:
    try:
        item = dictionary_service.update_subcategory(subcategory_id, payload.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KeywordSubcategoryResponse(**item)


@app.delete("/api/keyword-subcategories/{subcategory_id}", status_code=204)
def delete_keyword_subcategory(subcategory_id: int) -> Response:
    try:
        dictionary_service.delete_subcategory(subcategory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@app.post("/api/keyword-subcategories/{subcategory_id}/keywords", response_model=KeywordResponse, status_code=201)
def create_keyword(subcategory_id: int, payload: KeywordCreatePayload) -> KeywordResponse:
    categories = dictionary_service.list_categories()
    subcategory = next(
        (
            item
            for category in categories
            for item in category.get("subcategories", [])
            if int(item["id"]) == subcategory_id
        ),
        None,
    )
    if subcategory is None:
        raise HTTPException(status_code=404, detail="未找到对应的二级分类")

    try:
        item = dictionary_service.create_keyword(
            category_id=int(subcategory["category_id"]),
            subcategory_id=subcategory_id,
            keyword=payload.keyword,
            meaning=payload.meaning,
            sort_order=payload.sort_order,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KeywordResponse(**item)


@app.put("/api/keywords/{keyword_id}", response_model=KeywordResponse)
def update_keyword(keyword_id: int, payload: KeywordUpdatePayload) -> KeywordResponse:
    try:
        item = dictionary_service.update_keyword(keyword_id, payload.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KeywordResponse(**item)


@app.delete("/api/keywords/{keyword_id}", status_code=204)
def delete_keyword(keyword_id: int) -> Response:
    try:
        dictionary_service.delete_keyword(keyword_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@app.get("/api/jargon-analysis/sources", response_model=list[JargonSourceDatasetResponse])
def list_analysis_sources() -> list[JargonSourceDatasetResponse]:
    return [JargonSourceDatasetResponse(**item) for item in jargon_analysis_service.list_source_datasets()]


@app.post("/api/jargon-analysis/tasks", response_model=JargonTaskResponse, status_code=201)
def create_analysis_task(payload: JargonAnalysisCreateRequest) -> JargonTaskResponse:
    try:
        item = jargon_analysis_service.create_task(
            source_type=payload.source_type,
            source_task_id=payload.source_task_id,
            keyword_id=payload.keyword_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConfigError, DependencyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JargonTaskResponse(**item)


@app.get("/api/jargon-analysis/tasks", response_model=JargonTaskListResponse)
def list_analysis_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> JargonTaskListResponse:
    return JargonTaskListResponse(**jargon_analysis_service.list_tasks(page=page, page_size=page_size))


@app.get("/api/jargon-analysis/tasks/{task_id}", response_model=JargonTaskResponse)
def get_analysis_task(task_id: int) -> JargonTaskResponse:
    detail = jargon_analysis_service.get_task_detail(task_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="未找到分析任务")
    return JargonTaskResponse(**detail)


@app.get("/api/jargon-analysis/tasks/{task_id}/results", response_model=JargonTaskResultsResponse)
def get_analysis_task_results(task_id: int) -> JargonTaskResultsResponse:
    detail = jargon_analysis_service.get_task_detail(task_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="未找到分析任务")
    return JargonTaskResultsResponse(
        task=JargonTaskResponse(**detail),
        items=jargon_analysis_service.get_task_results(task_id),
    )


@app.get("/api/jargon-analysis/records", response_model=JargonSourceRecordListResponse)
def list_analysis_records(
    source_type: str = Query(..., pattern="^(xianyu|xhs)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    task_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None),
    matched_only: bool = Query(default=False),
) -> JargonSourceRecordListResponse:
    try:
        data = jargon_analysis_service.list_source_records(
            source_type=source_type,
            page=page,
            page_size=page_size,
            task_id=task_id,
            search=search,
            matched_only=matched_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JargonSourceRecordListResponse(**data)


@app.get("/api/jargon-analysis/matches", response_model=HitTracingRecordListResponse)
def list_matched_records(
    source_type: str = Query(..., pattern="^(xianyu|xhs)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    task_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None),
    keyword_id: int | None = Query(default=None, ge=1),
    category_id: int | None = Query(default=None, ge=1),
    subcategory_id: int | None = Query(default=None, ge=1),
    min_confidence: float | None = Query(default=None, ge=0, le=100),
) -> HitTracingRecordListResponse:
    try:
        data = jargon_analysis_service.list_matched_records(
            source_type=source_type,
            page=page,
            page_size=page_size,
            task_id=task_id,
            search=search,
            keyword_id=keyword_id,
            category_id=category_id,
            subcategory_id=subcategory_id,
            min_confidence=min_confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HitTracingRecordListResponse(**data)


@app.get("/api/jargon-analysis/matches/{record_id}", response_model=HitTracingRecordDetailResponse)
def get_matched_record_detail(record_id: int) -> HitTracingRecordDetailResponse:
    detail = jargon_analysis_service.get_matched_record_detail(record_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="未找到命中记录")
    return HitTracingRecordDetailResponse(**detail)


@app.get("/api/files", response_model=list[FileEntryResponse])
def list_files() -> list[FileEntryResponse]:
    return [FileEntryResponse(**item) for item in file_service.list_files()]


@app.delete("/api/files", status_code=204)
def delete_file(payload: FileDeleteRequest) -> Response:
    try:
        file_service.delete_file(payload.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (IsADirectoryError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)


@app.post("/api/files/batch-delete", status_code=204)
def batch_delete_files(payload: FileBatchDeleteRequest) -> Response:
    try:
        file_service.delete_files(payload.paths)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (IsADirectoryError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)


def _to_device_responses(devices: list[DeviceInfo]) -> list[DeviceResponse]:
    active_device_map = run_service.get_active_device_map()
    return [_to_device_response(device, active_device_map.get(device.serial)) for device in devices]


def _to_device_response(device: DeviceInfo, active_run: dict[str, object] | None = None) -> DeviceResponse:
    return DeviceResponse(
        serial=device.serial,
        state=device.state,
        android_version=device.android_version,
        model=device.model,
        busy=active_run is not None,
        active_run_id=int(active_run["id"]) if active_run is not None else None,
        active_run_status=str(active_run.get("status") or "") if active_run is not None else "",
    )
