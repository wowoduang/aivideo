from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.services import metadata_db
from app.utils import workspace


ARTIFACT_TYPES = {
    "script": "解说脚本",
    "highlights": "高光列表",
    "highlight_script": "高光脚本",
    "highlight_narration_segments": "高光解说段",
    "audit": "审计结果",
    "subtitle": "字幕文件",
    "subtitle_segments": "字幕分段",
    "video_output": "视频输出",
    "composition_plan": "混剪计划",
}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _workspace_root() -> Path:
    return Path(workspace.workspace_dir())


def _row_to_item(row) -> Dict[str, Any]:
    payload = {
        "id": str(row["id"]),
        "owner_email": row["owner_email"],
        "project_id": row["project_id"],
        "task_id": row["task_id"],
        "artifact_type": row["artifact_type"],
        "label": row["label"],
        "path": row["path"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "metadata": metadata_db.json_loads(row["metadata_json"], {}),
    }
    path = str(payload["path"] or "")
    try:
        payload["exists"] = os.path.exists(path)
    except Exception:
        payload["exists"] = False
    return payload


def upsert_artifact(
    *,
    owner_email: str,
    project_id: str,
    task_id: str,
    artifact_type: str,
    path: str,
    label: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    path = str(path or "").strip()
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    now = _now_iso()
    row = metadata_db.fetch_one(
        "SELECT id FROM artifacts WHERE project_id = ? AND task_id = ? AND artifact_type = ? AND path = ?",
        (str(project_id or ""), str(task_id or ""), artifact_type, path),
    )
    artifact_id = str(row["id"]) if row else str(uuid.uuid4())
    metadata_db.execute(
        """
        INSERT OR REPLACE INTO artifacts(
            id, owner_email, project_id, task_id, artifact_type, path, label, created_at, updated_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            _normalize_email(owner_email),
            str(project_id or "") or None,
            str(task_id or "") or None,
            artifact_type,
            path,
            label or ARTIFACT_TYPES.get(artifact_type, artifact_type),
            now,
            now,
            metadata_db.json_dumps(metadata or {}),
        ),
    )
    fresh = metadata_db.fetch_one("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
    return _row_to_item(fresh) if fresh else None


def list_project_artifacts(project_id: str, artifact_type: str | None = None) -> list[Dict[str, Any]]:
    if artifact_type:
        rows = metadata_db.fetch_all(
            "SELECT * FROM artifacts WHERE project_id = ? AND artifact_type = ? ORDER BY updated_at DESC",
            (str(project_id), artifact_type),
        )
    else:
        rows = metadata_db.fetch_all(
            "SELECT * FROM artifacts WHERE project_id = ? ORDER BY updated_at DESC",
            (str(project_id),),
        )
    return [_row_to_item(row) for row in rows]


def get_latest_project_artifact(project_id: str, artifact_type: str) -> Optional[Dict[str, Any]]:
    row = metadata_db.fetch_one(
        "SELECT * FROM artifacts WHERE project_id = ? AND artifact_type = ? ORDER BY updated_at DESC LIMIT 1",
        (str(project_id), artifact_type),
    )
    return _row_to_item(row) if row else None


def index_movie_story_result(owner_email: str, project_id: str, task_id: str, payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    indexed: list[Dict[str, Any]] = []
    mappings: Iterable[tuple[str, str, str]] = (
        ("script_path", "script", "解说脚本"),
        ("composition_script_path", "highlight_script", "高光脚本"),
        ("highlight_script_path", "highlight_script", "高光脚本"),
        ("highlights_path", "highlights", "高光列表"),
        ("highlight_narration_segments_path", "highlight_narration_segments", "高光解说段"),
        ("audit_path", "audit", "审计结果"),
        ("subtitle_path", "subtitle", "字幕文件"),
        ("subtitle_segments_path", "subtitle_segments", "字幕分段"),
    )
    for key, artifact_type, label in mappings:
        item = upsert_artifact(
            owner_email=owner_email,
            project_id=project_id,
            task_id=task_id,
            artifact_type=artifact_type,
            path=str(payload.get(key, "") or ""),
            label=label,
            metadata={"source_key": key},
        )
        if item:
            indexed.append(item)

    for idx, video_path in enumerate(list(payload.get("combined_videos", []) or []) + list(payload.get("videos", []) or []), start=1):
        item = upsert_artifact(
            owner_email=owner_email,
            project_id=project_id,
            task_id=task_id,
            artifact_type="video_output",
            path=str(video_path or ""),
            label=f"视频输出 {idx}",
            metadata={"index": idx},
        )
        if item:
            indexed.append(item)
    return indexed


def read_json_artifact_content(artifact: Optional[Dict[str, Any]], default: Any) -> Any:
    if not artifact:
        return default
    path = str(artifact.get("path") or "")
    if not path or not os.path.exists(path):
        return default
    try:
        import json

        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def workspace_relative_path(path: str) -> str:
    candidate = Path(path).resolve()
    try:
        return str(candidate.relative_to(_workspace_root().resolve()))
    except Exception:
        return str(candidate)


def find_project_artifact_by_path(project_id: str, path: str) -> Optional[Dict[str, Any]]:
    normalized = str(path or "").strip()
    if not normalized:
        return None
    candidate = Path(normalized)
    query = "SELECT * FROM artifacts WHERE project_id = ? AND path = ? ORDER BY updated_at DESC LIMIT 1"
    row = metadata_db.fetch_one(query, (str(project_id), str(candidate)))
    if not row:
        try:
            resolved = str(candidate.resolve())
        except Exception:
            resolved = str(candidate)
        row = metadata_db.fetch_one(query, (str(project_id), resolved))
    return _row_to_item(row) if row else None


def get_project_artifact(project_id: str, artifact_id: str) -> Optional[Dict[str, Any]]:
    row = metadata_db.fetch_one(
        "SELECT * FROM artifacts WHERE project_id = ? AND id = ? LIMIT 1",
        (str(project_id), str(artifact_id)),
    )
    return _row_to_item(row) if row else None
