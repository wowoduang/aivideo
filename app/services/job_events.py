from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from app.services import metadata_db


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _row_to_event(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "owner_email": row["owner_email"],
        "project_id": row["project_id"] or "",
        "job_type": row["job_type"] or "",
        "event_type": row["event_type"],
        "status": row["status"] or "",
        "progress": int(row["progress"] or 0),
        "message": row["message"] or "",
        "metadata": metadata_db.json_loads(row["metadata_json"], {}),
        "created_at": row["created_at"],
    }


def record_event(
    *,
    owner: str,
    task_id: str,
    event_type: str,
    project_id: str = "",
    job_type: str = "",
    status: str = "",
    progress: int = 0,
    message: str = "",
    metadata: Dict[str, Any] | None = None,
    created_at: str | None = None,
) -> Dict[str, Any] | None:
    """Append a durable task event for task-center UI and debugging."""

    normalized_owner = _normalize_email(owner)
    normalized_task_id = str(task_id or "").strip()
    normalized_event = str(event_type or "").strip() or "event"
    if not normalized_owner or not normalized_task_id:
        return None

    event = {
        "id": str(uuid4()),
        "owner_email": normalized_owner,
        "task_id": normalized_task_id,
        "project_id": str(project_id or "") or None,
        "job_type": str(job_type or ""),
        "event_type": normalized_event,
        "status": str(status or ""),
        "progress": max(0, min(100, int(progress or 0))),
        "message": str(message or ""),
        "metadata_json": metadata_db.json_dumps(metadata or {}),
        "created_at": created_at or _now_iso(),
    }
    metadata_db.execute(
        """
        INSERT INTO job_events(
            id, owner_email, task_id, project_id, job_type, event_type, status,
            progress, message, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["id"], event["owner_email"], event["task_id"], event["project_id"],
            event["job_type"], event["event_type"], event["status"], event["progress"],
            event["message"], event["metadata_json"], event["created_at"],
        ),
    )
    return {
        "id": event["id"],
        "task_id": event["task_id"],
        "owner_email": event["owner_email"],
        "project_id": event["project_id"] or "",
        "job_type": event["job_type"],
        "event_type": event["event_type"],
        "status": event["status"],
        "progress": event["progress"],
        "message": event["message"],
        "metadata": metadata or {},
        "created_at": event["created_at"],
    }


def list_events(task_id: str, *, owner: str, limit: int = 200) -> List[Dict[str, Any]]:
    normalized_owner = _normalize_email(owner)
    normalized_task_id = str(task_id or "").strip()
    if not normalized_owner or not normalized_task_id:
        return []
    rows = metadata_db.fetch_all(
        """
        SELECT * FROM job_events
        WHERE task_id = ? AND owner_email = ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (normalized_task_id, normalized_owner, max(1, min(500, int(limit or 200)))),
    )
    return [_row_to_event(row) for row in rows]
