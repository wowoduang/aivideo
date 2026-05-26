from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.services import metadata_db
from app.utils import workspace


def _history_dir() -> str:
    return workspace.state_dir("jobs", create=True)


def _history_path() -> str:
    return os.path.join(_history_dir(), "history.json")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _read_legacy() -> Dict[str, List[Dict]]:
    path = _history_path()
    if not os.path.exists(path):
        return {"items": []}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        payload = {"items": []}
    if not isinstance(payload, dict):
        return {"items": []}
    items = payload.get("items", [])
    return {"items": list(items) if isinstance(items, list) else []}


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _row_to_item(row) -> Dict:
    return {
        "owner": row["owner_email"],
        "project_id": row["project_id"],
        "task_id": row["task_id"],
        "job_type": row["job_type"],
        "task_dir": row["task_dir"],
        "status": row["status"],
        "progress": int(row["progress"] or 0),
        "message": row["message"] or "",
        "error": row["error"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _import_legacy_if_needed() -> None:
    row = metadata_db.fetch_one("SELECT COUNT(*) AS cnt FROM jobs")
    if row and int(row["cnt"] or 0) > 0:
        return
    payload = _read_legacy()
    items = payload.get("items", [])
    if not items:
        return
    with metadata_db.connect() as conn:
        for item in items:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs(
                    task_id, owner_email, project_id, job_type, task_dir, status, progress,
                    message, error, created_at, updated_at, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(item.get("task_id") or ""),
                    _normalize_email(item.get("owner") or ""),
                    item.get("project_id"),
                    str(item.get("job_type") or "video"),
                    str(item.get("task_dir") or ""),
                    str(item.get("status") or "processing"),
                    int(item.get("progress") or 0),
                    str(item.get("message") or ""),
                    str(item.get("error") or ""),
                    str(item.get("created_at") or _now_iso()),
                    str(item.get("updated_at") or item.get("created_at") or _now_iso()),
                    None,
                ),
            )


def record_job(
    *,
    owner: str,
    task_id: str,
    job_type: str,
    task_dir: str,
    project_id: str = "",
    status: str = "processing",
    progress: int = 0,
    message: str = "",
    error: str = "",
    created_at: Optional[str] = None,
) -> Dict:
    _import_legacy_if_needed()
    created_at = created_at or _now_iso()
    item = {
        "owner": _normalize_email(owner),
        "project_id": str(project_id or "") or None,
        "task_id": task_id,
        "job_type": job_type,
        "task_dir": task_dir,
        "status": status,
        "progress": int(progress),
        "message": message,
        "error": error,
        "created_at": created_at,
        "updated_at": created_at,
    }
    metadata_db.execute(
        """
        INSERT OR REPLACE INTO jobs(
            task_id, owner_email, project_id, job_type, task_dir, status, progress,
            message, error, created_at, updated_at, result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["task_id"],
            item["owner"],
            item["project_id"],
            item["job_type"],
            item["task_dir"],
            item["status"],
            item["progress"],
            item["message"],
            item["error"],
            item["created_at"],
            item["updated_at"],
            None,
        ),
    )
    return item


def update_job(
    *,
    task_id: str,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    result: Optional[Dict] = None,
) -> Optional[Dict]:
    _import_legacy_if_needed()
    row = metadata_db.fetch_one("SELECT * FROM jobs WHERE task_id = ?", (task_id,))
    if row is None:
        return None
    next_status = status if status is not None else row["status"]
    next_progress = int(progress) if progress is not None else int(row["progress"] or 0)
    next_message = message if message is not None else str(row["message"] or "")
    next_error = error if error is not None else str(row["error"] or "")
    result_json = metadata_db.json_dumps(result) if result is not None else row["result_json"]
    updated_at = _now_iso()
    metadata_db.execute(
        """
        UPDATE jobs
        SET status = ?, progress = ?, message = ?, error = ?, updated_at = ?, result_json = ?
        WHERE task_id = ?
        """,
        (next_status, next_progress, next_message, next_error, updated_at, result_json, task_id),
    )
    return get_job(task_id)


def get_job(task_id: str) -> Optional[Dict]:
    _import_legacy_if_needed()
    row = metadata_db.fetch_one("SELECT * FROM jobs WHERE task_id = ?", (task_id,))
    if row is None:
        return None
    item = _row_to_item(row)
    item["result"] = metadata_db.json_loads(row["result_json"], None)
    return item


def list_jobs(owner: str, limit: int = 60) -> List[Dict]:
    _import_legacy_if_needed()
    rows = metadata_db.fetch_all(
        "SELECT * FROM jobs WHERE owner_email = ? ORDER BY updated_at DESC LIMIT ?",
        (_normalize_email(owner), max(1, limit)),
    )
    return [_row_to_item(row) for row in rows]


def list_project_jobs(project_id: str, limit: int = 30) -> List[Dict]:
    _import_legacy_if_needed()
    rows = metadata_db.fetch_all(
        "SELECT * FROM jobs WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
        (str(project_id), max(1, limit)),
    )
    return [_row_to_item(row) for row in rows]
