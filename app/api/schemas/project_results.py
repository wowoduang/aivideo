from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ArtifactPayload(BaseModel):
    id: str
    owner_email: Optional[str] = None
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    artifact_type: str
    label: str
    path: str
    created_at: str
    updated_at: str
    exists: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectJobPayload(BaseModel):
    task_id: str
    job_type: str
    status: str
    progress: int
    message: str = ""
    error: str = ""
    task_dir: str
    created_at: str
    updated_at: str
    project_id: Optional[str] = None


class ProjectResultsOverviewResponse(BaseModel):
    project_id: str
    latest_job: Optional[ProjectJobPayload] = None
    artifacts: list[ArtifactPayload] = Field(default_factory=list)
    script_items: list[dict[str, Any]] = Field(default_factory=list)
    highlights: list[dict[str, Any]] = Field(default_factory=list)
    highlight_narration_segments: list[dict[str, Any]] = Field(default_factory=list)
    global_summary: dict[str, Any] = Field(default_factory=dict)
    understanding_script: dict[str, Any] = Field(default_factory=dict)
    segment_understandings: list[dict[str, Any]] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class ProjectArtifactListResponse(BaseModel):
    items: list[ArtifactPayload]
