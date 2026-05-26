from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.api.schemas.jobs import WorkspaceInfoResponse
from app.services import auth_store, usage_meter, usage_pricing
from app.config import config
from app.utils import utils
from app.utils import workspace


router = APIRouter(prefix="/system", tags=["system"])


def _bool_env(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _ffmpeg_status() -> dict[str, Any]:
    exe = os.getenv("IMAGEIO_FFMPEG_EXE") or config.app.get("ffmpeg_path") or shutil.which("ffmpeg") or ""
    available = bool(exe and (shutil.which(str(exe)) or Path(str(exe)).exists()))
    version = ""
    if available:
        try:
            completed = subprocess.run([str(exe), "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
            version = (completed.stdout or completed.stderr).splitlines()[0] if (completed.stdout or completed.stderr) else ""
        except Exception:
            version = ""
    return {"available": available, "path": str(exe or ""), "version": version}


def _path_exists(value: Any) -> bool:
    return bool(str(value or "").strip() and Path(str(value)).expanduser().exists())


def _configured(value: Any) -> bool:
    return bool(str(value or "").strip())


def _job_worker_status() -> dict[str, Any]:
    try:
        from app.services.job_runner import runner_api

        return runner_api()["get_local_job_worker_status"]()
    except Exception as exc:
        return {"backend": "unavailable", "error": str(exc)}


@router.get("/workspace", response_model=WorkspaceInfoResponse)
def get_workspace_info(user: auth_store.StoredUser = Depends(require_user)):
    _ = user
    return WorkspaceInfoResponse(
        project_root=config.root_dir,
        workspace_root=utils.workspace_dir(),
        config_file=config.config_file,
        project_version=config.project_version,
        layout=workspace.workspace_layout_paths(create=False),
        task_root=utils.task_dir(),
    )


@router.get("/health")
def get_system_health(user: auth_store.StoredUser = Depends(require_user)):
    """Deployment readiness information without exposing secret values."""
    _ = user
    workspace_root = Path(utils.workspace_dir())
    disk = shutil.disk_usage(workspace_root)
    whisper_cfg = getattr(config, "whisper", {}) or {}
    app_cfg = getattr(config, "app", {}) or {}
    tts_qwen_cfg = getattr(config, "tts_qwen", {}) or {}
    azure_cfg = getattr(config, "azure", {}) or {}
    return {
        "project_version": config.project_version,
        "environment": os.getenv("AIVIDEO_ENV") or os.getenv("ENV") or "development",
        "workspace": {
            "root": str(workspace_root),
            "exists": workspace_root.exists(),
            "free_bytes": int(disk.free),
            "total_bytes": int(disk.total),
        },
        "runtime": {
            "ffmpeg": _ffmpeg_status(),
            "imagemagick_configured": _configured(app_cfg.get("imagemagick_path")),
            "public_uploads_enabled": _bool_env("AIVIDEO_PUBLIC_UPLOADS"),
            "local_job_max_workers": int(os.getenv("AIVIDEO_LOCAL_JOB_MAX_WORKERS", "2") or 2),
        },
        "jobs": _job_worker_status(),
        "asr": {
            "bailian_key_configured": _configured(whisper_cfg.get("bailian_api_key") or os.getenv("DASHSCOPE_API_KEY")),
            "funasr_model_path_exists": _path_exists(whisper_cfg.get("funasr_model_path")),
            "sensevoice_model_path_exists": _path_exists(whisper_cfg.get("sensevoice_model_path")),
        },
        "tts": {
            "qwen_key_configured": _configured(tts_qwen_cfg.get("api_key") or os.getenv("DASHSCOPE_API_KEY")),
            "azure_key_configured": _configured(os.getenv("AZURE_SPEECH_KEY") or azure_cfg.get("speech_key")),
        },
        "usage_pricing": usage_pricing.pricing_status(),
    }


@router.get("/usage")
def get_usage_summary(limit: int = 20, user: auth_store.StoredUser = Depends(require_user)):
    safe_limit = max(1, min(100, int(limit or 20)))
    return usage_meter.summarize_usage(user.email, limit=safe_limit)


@router.get("/config")
def get_runtime_config():
    """
    获取运行时配置（供前端使用）
    """
    host = config.app.get("local_api_host", "127.0.0.1")
    port = config.app.get("local_api_port", 18000)
    return {
        "API_BASE_URL": f"http://{host}:{port}",
        "project_name": config.project_name,
        "project_version": config.project_version,
    }
