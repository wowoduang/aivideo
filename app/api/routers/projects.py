from __future__ import annotations

import mimetypes
from urllib.parse import urlencode
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.schemas.project_results import ProjectArtifactListResponse, ProjectResultsOverviewResponse
from app.api.schemas.projects import DeleteResponse, ProjectCreateRequest, ProjectListResponse, ProjectResponse, ProjectUpdateRequest
from app.repositories import artifact_repository, project_repository
from app.api.deps import extract_bearer_token, require_user
from app.services import auth_store, file_signing, job_history
from app.utils import workspace

router = APIRouter(prefix="/projects", tags=["projects"])


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


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
def list_projects(user: auth_store.StoredUser = Depends(require_user)) -> ProjectListResponse:
    return ProjectListResponse(items=project_repository.list_projects(user.email))


@router.post("", response_model=ProjectResponse)
def create_project(payload: ProjectCreateRequest, user: auth_store.StoredUser = Depends(require_user)) -> ProjectResponse:
    return ProjectResponse(item=project_repository.create_project(user.email, payload.name, payload.inferenceMode))


@router.get("/workspace-file")
def get_workspace_file(
    path: str = Query(...),
    project_id: str = Query(...),
    artifact_id: str = Query(default=""),
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Query(default=None),
    signed_user: Optional[str] = Query(default=None),
    expires: Optional[str] = Query(default=None),
    signature: Optional[str] = Query(default=None),
):
    artifact = None
    if artifact_id:
        artifact = artifact_repository.get_project_artifact(project_id, artifact_id)
    if artifact is None:
        artifact = artifact_repository.find_project_artifact_by_path(project_id, path)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    resolved_path = str(artifact.get("path") or path)

    user = None
    token = str(access_token or "").strip()
    if not token and authorization:
        token = extract_bearer_token(authorization)
    if token:
        user = auth_store.get_user_by_token(token)
        if user:
            auth_store.touch_session(token, _now_iso())
    if user is None:
        signed_email = str(signed_user or "").strip().lower()
        if not signed_email or not file_signing.verify_path_signature(
            scope=f"workspace:{project_id}:{artifact_id or ''}",
            path=resolved_path,
            user_email=signed_email,
            expires=expires,
            signature=signature,
        ):
            raise HTTPException(status_code=401, detail="invalid_token")
        project = _require_project(signed_email, project_id)
        _ = project
    else:
        _require_project(user.email, project_id)
    return _workspace_file_response(resolved_path)


@router.get("/workspace-file/signed-url")
def get_signed_workspace_file_url(
    path: str = Query(...),
    project_id: str = Query(...),
    artifact_id: str = Query(default=""),
    user: auth_store.StoredUser = Depends(require_user),
):
    _require_project(user.email, project_id)
    artifact = None
    if artifact_id:
        artifact = artifact_repository.get_project_artifact(project_id, artifact_id)
    if artifact is None:
        artifact = artifact_repository.find_project_artifact_by_path(project_id, path)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    resolved_path = str(artifact.get("path") or path)
    signed = file_signing.sign_path(
        scope=f"workspace:{project_id}:{artifact_id or ''}",
        path=resolved_path,
        user_email=user.email,
    )
    params = urlencode({
        "path": path,
        "project_id": project_id,
        "artifact_id": artifact_id,
        "signed_user": user.email,
        "expires": str(signed["expires"]),
        "signature": str(signed["signature"]),
    })
    return {"url": f"/api/v1/projects/workspace-file?{params}", "expires": signed["expires"]}


@router.get("/{project_id}/artifacts", response_model=ProjectArtifactListResponse)
def list_project_artifacts(project_id: str, user: auth_store.StoredUser = Depends(require_user)) -> ProjectArtifactListResponse:
    _require_project(user.email, project_id)
    return ProjectArtifactListResponse(items=artifact_repository.list_project_artifacts(project_id))


@router.get("/{project_id}/results/overview", response_model=ProjectResultsOverviewResponse)
def get_project_results_overview(project_id: str, user: auth_store.StoredUser = Depends(require_user)) -> ProjectResultsOverviewResponse:
    _require_project(user.email, project_id)
    artifacts = artifact_repository.list_project_artifacts(project_id)
    latest_job = next(iter(job_history.list_project_jobs(project_id, limit=1)), None)
    latest_script = artifact_repository.get_latest_project_artifact(project_id, "script")
    latest_highlights = artifact_repository.get_latest_project_artifact(project_id, "highlights")
    latest_highlight_segments = artifact_repository.get_latest_project_artifact(project_id, "highlight_narration_segments")
    latest_understanding_script = artifact_repository.get_latest_project_artifact(project_id, "understanding_script")
    latest_audit = artifact_repository.get_latest_project_artifact(project_id, "audit")
    audit_payload = artifact_repository.read_json_artifact_content(latest_audit, {})
    understanding_script = artifact_repository.read_json_artifact_content(latest_understanding_script, {})
    global_summary = {}
    segment_understandings = []
    if isinstance(audit_payload, dict):
        global_summary = dict(audit_payload.get("global_summary") or {})
    if isinstance(understanding_script, dict):
        global_summary = {
            **dict(understanding_script.get("global_story_understanding") or {}),
            **global_summary,
        }
        segment_understandings = list(understanding_script.get("segment_understandings") or [])
    return ProjectResultsOverviewResponse(
        project_id=project_id,
        latest_job=latest_job,
        artifacts=artifacts,
        script_items=artifact_repository.read_json_artifact_content(latest_script, []),
        highlights=artifact_repository.read_json_artifact_content(latest_highlights, []),
        highlight_narration_segments=artifact_repository.read_json_artifact_content(latest_highlight_segments, []),
        global_summary=global_summary,
        understanding_script=understanding_script if isinstance(understanding_script, dict) else {},
        segment_understandings=segment_understandings,
        audit=audit_payload if isinstance(audit_payload, dict) else {},
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, user: auth_store.StoredUser = Depends(require_user)) -> ProjectResponse:
    item = _require_project(user.email, project_id)
    return ProjectResponse(item=item)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, payload: ProjectUpdateRequest, user: auth_store.StoredUser = Depends(require_user)) -> ProjectResponse:
    item = project_repository.update_project(user.email, project_id, payload.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="project_not_found")
    return ProjectResponse(item=item)


@router.delete("/{project_id}", response_model=DeleteResponse)
def delete_project(project_id: str, user: auth_store.StoredUser = Depends(require_user)) -> DeleteResponse:
    if not project_repository.delete_project(user.email, project_id):
        raise HTTPException(status_code=404, detail="project_not_found")
    return DeleteResponse(success=True)
