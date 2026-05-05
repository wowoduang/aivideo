from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.schemas.project_results import ProjectArtifactListResponse, ProjectResultsOverviewResponse
from app.api.schemas.projects import DeleteResponse, ProjectCreateRequest, ProjectListResponse, ProjectResponse, ProjectUpdateRequest
from app.repositories import artifact_repository, project_repository
from app.services import auth_store, job_history
from app.utils import workspace

router = APIRouter(prefix="/projects", tags=["projects"])


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing_token")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="invalid_token")
    return authorization.split(" ", 1)[1].strip()


def _require_user(authorization: Optional[str]):
    token = _extract_token(authorization)
    user = auth_store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid_token")
    return user


def _require_project(user_email: str, project_id: str) -> dict:
    item = project_repository.get_project(user_email, project_id)
    if not item:
        raise HTTPException(status_code=404, detail="project_not_found")
    return item


def _workspace_file_response(path: str) -> FileResponse:
    candidate = Path(path).resolve()
    workspace_root = Path(workspace.workspace_dir()).resolve()
    try:
        candidate.relative_to(workspace_root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="path_outside_workspace") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="file_not_found")
    media_type, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(str(candidate), media_type=media_type or "application/octet-stream")


@router.get("", response_model=ProjectListResponse)
def list_projects(authorization: Optional[str] = Header(default=None)) -> ProjectListResponse:
    user = _require_user(authorization)
    return ProjectListResponse(items=project_repository.list_projects(user.email))


@router.post("", response_model=ProjectResponse)
def create_project(payload: ProjectCreateRequest, authorization: Optional[str] = Header(default=None)) -> ProjectResponse:
    user = _require_user(authorization)
    return ProjectResponse(item=project_repository.create_project(user.email, payload.name, payload.inferenceMode))


@router.get("/workspace-file")
def get_workspace_file(
    path: str = Query(...),
    project_id: str = Query(...),
    artifact_id: str = Query(default=""),
    authorization: Optional[str] = Header(default=None),
):
    user = _require_user(authorization)
    _require_project(user.email, project_id)

    artifact = None
    if artifact_id:
        artifact = artifact_repository.get_project_artifact(project_id, artifact_id)
    if artifact is None:
        artifact = artifact_repository.find_project_artifact_by_path(project_id, path)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return _workspace_file_response(str(artifact.get("path") or path))


@router.get("/{project_id}/artifacts", response_model=ProjectArtifactListResponse)
def list_project_artifacts(project_id: str, authorization: Optional[str] = Header(default=None)) -> ProjectArtifactListResponse:
    user = _require_user(authorization)
    _require_project(user.email, project_id)
    return ProjectArtifactListResponse(items=artifact_repository.list_project_artifacts(project_id))


@router.get("/{project_id}/results/overview", response_model=ProjectResultsOverviewResponse)
def get_project_results_overview(project_id: str, authorization: Optional[str] = Header(default=None)) -> ProjectResultsOverviewResponse:
    user = _require_user(authorization)
    _require_project(user.email, project_id)
    artifacts = artifact_repository.list_project_artifacts(project_id)
    latest_job = next(iter(job_history.list_project_jobs(project_id, limit=1)), None)
    latest_script = artifact_repository.get_latest_project_artifact(project_id, "script")
    latest_highlights = artifact_repository.get_latest_project_artifact(project_id, "highlights")
    latest_highlight_segments = artifact_repository.get_latest_project_artifact(project_id, "highlight_narration_segments")
    latest_audit = artifact_repository.get_latest_project_artifact(project_id, "audit")
    audit_payload = artifact_repository.read_json_artifact_content(latest_audit, {})
    global_summary = {}
    if isinstance(audit_payload, dict):
        global_summary = dict(audit_payload.get("global_summary") or {})
    return ProjectResultsOverviewResponse(
        project_id=project_id,
        latest_job=latest_job,
        artifacts=artifacts,
        script_items=artifact_repository.read_json_artifact_content(latest_script, []),
        highlights=artifact_repository.read_json_artifact_content(latest_highlights, []),
        highlight_narration_segments=artifact_repository.read_json_artifact_content(latest_highlight_segments, []),
        global_summary=global_summary,
        audit=audit_payload if isinstance(audit_payload, dict) else {},
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, authorization: Optional[str] = Header(default=None)) -> ProjectResponse:
    user = _require_user(authorization)
    item = _require_project(user.email, project_id)
    return ProjectResponse(item=item)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, payload: ProjectUpdateRequest, authorization: Optional[str] = Header(default=None)) -> ProjectResponse:
    user = _require_user(authorization)
    item = project_repository.update_project(user.email, project_id, payload.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="project_not_found")
    return ProjectResponse(item=item)


@router.delete("/{project_id}", response_model=DeleteResponse)
def delete_project(project_id: str, authorization: Optional[str] = Header(default=None)) -> DeleteResponse:
    user = _require_user(authorization)
    if not project_repository.delete_project(user.email, project_id):
        raise HTTPException(status_code=404, detail="project_not_found")
    return DeleteResponse(success=True)
