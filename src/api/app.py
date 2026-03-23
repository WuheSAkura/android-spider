from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.api.schemas import (
    AppSettingsPayload,
    ArtifactResponse,
    DeviceResponse,
    DoctorResponse,
    RunCreateRequest,
    RunLogsResponse,
    RunSummaryResponse,
    TaskTemplateResponse,
)
from src.core.adb_manager import AdbManager
from src.core.device_manager import DeviceManager
from src.services.run_service import RunService
from src.services.settings_service import AppSettings, SettingsService
from src.services.task_template_service import TaskTemplateService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQLITE_PATH = PROJECT_ROOT / "data" / "local_runs.sqlite3"

template_service = TaskTemplateService(PROJECT_ROOT)
settings_service = SettingsService(SQLITE_PATH)
run_service = RunService(PROJECT_ROOT, SQLITE_PATH)

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


@app.get("/api/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/doctor", response_model=DoctorResponse)
def get_doctor_report() -> DoctorResponse:
    settings = settings_service.get_settings()
    adb_manager = AdbManager(settings.adb_path or None)
    device_manager = DeviceManager(adb_manager)
    dependencies = {
        "yaml": _check_module("yaml"),
        "uiautomator2": _check_module("uiautomator2"),
        "mysql.connector": _check_module("mysql.connector"),
        "fastapi": _check_module("fastapi"),
        "uvicorn": _check_module("uvicorn"),
    }
    report = device_manager.build_doctor_report(dependencies)
    return DoctorResponse(
        adb_available=report.adb_available,
        adb_version=report.adb_version,
        adb_path=report.adb_path,
        dependencies=report.dependencies,
        devices=[DeviceResponse(**device.__dict__) for device in report.devices],
        default_device_serial=report.default_device.serial if report.default_device is not None else None,
    )


@app.get("/api/system/devices", response_model=list[DeviceResponse])
def list_devices() -> list[DeviceResponse]:
    settings = settings_service.get_settings()
    adb_manager = AdbManager(settings.adb_path or None)
    device_manager = DeviceManager(adb_manager)
    return [DeviceResponse(**device.__dict__) for device in device_manager.discover_devices()]


@app.get("/api/task-templates", response_model=list[TaskTemplateResponse])
def list_task_templates() -> list[TaskTemplateResponse]:
    return [TaskTemplateResponse(**template.to_dict()) for template in template_service.list_templates()]


@app.get("/api/settings", response_model=AppSettingsPayload)
def get_settings() -> AppSettingsPayload:
    return AppSettingsPayload(**settings_service.get_settings().to_dict())


@app.put("/api/settings", response_model=AppSettingsPayload)
def save_settings(payload: AppSettingsPayload) -> AppSettingsPayload:
    settings = settings_service.save_settings(AppSettings(**payload.model_dump()))
    return AppSettingsPayload(**settings.to_dict())


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
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@app.get("/api/runs/{run_id}/records")
def get_run_records(run_id: int) -> list[dict[str, object]]:
    try:
        return run_service.get_run_records(run_id)
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


def _check_module(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True
