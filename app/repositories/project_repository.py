from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services import metadata_db
from app.utils import workspace


def _projects_path() -> str:
    return os.path.join(workspace.state_dir("projects", create=True), "projects.json")


def _read_legacy() -> Dict[str, List[Dict[str, Any]]]:
    path = _projects_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _project_from_row(row) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "status": str(row["status"]),
        "thumbnailUrl": row["thumbnail_url"],
        "videoUrl": row["video_url"],
        "videoFileName": row["video_file_name"],
        "videoDurationSec": row["video_duration_sec"],
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
        "currentStep": str(row["current_step"]),
        "inferenceMode": row["inference_mode"],
        "uploadedVideoPath": row["uploaded_video_path"],
        "uploadedSubtitlePath": row["uploaded_subtitle_path"],
        "config": metadata_db.json_loads(row["config_json"], None),
        "scriptItems": metadata_db.json_loads(row["script_items_json"], None),
    }


def _import_legacy_if_needed() -> None:
    row = metadata_db.fetch_one("SELECT COUNT(*) AS cnt FROM projects")
    if row and int(row["cnt"] or 0) > 0:
        return
    payload = _read_legacy()
    if not payload:
        return
    with metadata_db.connect() as conn:
        for owner, items in payload.items():
            normalized = _normalize_email(owner)
            for item in items:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO projects(
                        id, owner_email, name, status, thumbnail_url, video_url, video_file_name,
                        video_duration_sec, created_at, updated_at, current_step, inference_mode,
                        uploaded_video_path, uploaded_subtitle_path, config_json, script_items_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(item.get("id") or uuid.uuid4()),
                        normalized,
                        str(item.get("name") or "未命名项目"),
                        str(item.get("status") or "draft"),
                        item.get("thumbnailUrl"),
                        item.get("videoUrl"),
                        item.get("videoFileName"),
                        item.get("videoDurationSec"),
                        str(item.get("createdAt") or _now_iso()),
                        str(item.get("updatedAt") or item.get("createdAt") or _now_iso()),
                        str(item.get("currentStep") or "upload"),
                        item.get("inferenceMode") or "fast",
                        item.get("uploadedVideoPath"),
                        item.get("uploadedSubtitlePath"),
                        metadata_db.json_dumps(item.get("config")) if item.get("config") is not None else None,
                        metadata_db.json_dumps(item.get("scriptItems")) if item.get("scriptItems") is not None else None,
                    ),
                )


def list_projects(owner: str) -> List[Dict[str, Any]]:
    _import_legacy_if_needed()
    rows = metadata_db.fetch_all(
        "SELECT * FROM projects WHERE owner_email = ? ORDER BY updated_at DESC",
        (_normalize_email(owner),),
    )
    return [_project_from_row(row) for row in rows]


def get_project(owner: str, project_id: str) -> Optional[Dict[str, Any]]:
    _import_legacy_if_needed()
    row = metadata_db.fetch_one(
        "SELECT * FROM projects WHERE owner_email = ? AND id = ?",
        (_normalize_email(owner), str(project_id)),
    )
    return _project_from_row(row) if row else None


def get_project_by_id(project_id: str) -> Optional[Dict[str, Any]]:
    _import_legacy_if_needed()
    row = metadata_db.fetch_one("SELECT * FROM projects WHERE id = ?", (str(project_id),))
    return _project_from_row(row) if row else None


def create_project(owner: str, name: str, inference_mode: Optional[str] = "fast") -> Dict[str, Any]:
    now = _now_iso()
    project = {
        "id": str(uuid.uuid4()),
        "name": str(name or "").strip() or "未命名项目",
        "status": "draft",
        "thumbnailUrl": None,
        "videoUrl": None,
        "videoFileName": None,
        "videoDurationSec": None,
        "createdAt": now,
        "updatedAt": now,
        "currentStep": "upload",
        "inferenceMode": inference_mode or "fast",
        "uploadedVideoPath": None,
        "uploadedSubtitlePath": None,
        "config": None,
        "scriptItems": None,
    }
    metadata_db.execute(
        """
        INSERT INTO projects(
            id, owner_email, name, status, thumbnail_url, video_url, video_file_name,
            video_duration_sec, created_at, updated_at, current_step, inference_mode,
            uploaded_video_path, uploaded_subtitle_path, config_json, script_items_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project["id"],
            _normalize_email(owner),
            project["name"],
            project["status"],
            project["thumbnailUrl"],
            project["videoUrl"],
            project["videoFileName"],
            project["videoDurationSec"],
            project["createdAt"],
            project["updatedAt"],
            project["currentStep"],
            project["inferenceMode"],
            project["uploadedVideoPath"],
            project["uploadedSubtitlePath"],
            None,
            None,
        ),
    )
    return project


def update_project(owner: str, project_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    current = get_project(owner, project_id)
    if current is None:
        return None
    safe_patch = {k: v for k, v in patch.items() if k not in {"id", "createdAt", "updatedAt"}}
    merged = {**current, **safe_patch, "updatedAt": _now_iso()}
    metadata_db.execute(
        """
        UPDATE projects
        SET name = ?, status = ?, thumbnail_url = ?, video_url = ?, video_file_name = ?,
            video_duration_sec = ?, updated_at = ?, current_step = ?, inference_mode = ?,
            uploaded_video_path = ?, uploaded_subtitle_path = ?, config_json = ?, script_items_json = ?
        WHERE owner_email = ? AND id = ?
        """,
        (
            merged.get("name"),
            merged.get("status"),
            merged.get("thumbnailUrl"),
            merged.get("videoUrl"),
            merged.get("videoFileName"),
            merged.get("videoDurationSec"),
            merged.get("updatedAt"),
            merged.get("currentStep"),
            merged.get("inferenceMode"),
            merged.get("uploadedVideoPath"),
            merged.get("uploadedSubtitlePath"),
            metadata_db.json_dumps(merged.get("config")) if merged.get("config") is not None else None,
            metadata_db.json_dumps(merged.get("scriptItems")) if merged.get("scriptItems") is not None else None,
            _normalize_email(owner),
            str(project_id),
        ),
    )
    return get_project(owner, project_id)


def delete_project(owner: str, project_id: str) -> bool:
    existing = get_project(owner, project_id)
    if existing is None:
        return False
    metadata_db.execute(
        "DELETE FROM projects WHERE owner_email = ? AND id = ?",
        (_normalize_email(owner), str(project_id)),
    )
    return True
