from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ProjectStatus = Literal['draft', 'completed', 'exported', 'failed']
ProjectStep = Literal['upload', 'subtitle', 'config', 'generate']
InferenceMode = Literal['fast', 'deep', 'frame']


class ProjectPayload(BaseModel):
    id: str
    name: str
    status: ProjectStatus = 'draft'
    thumbnailUrl: Optional[str] = None
    videoUrl: Optional[str] = None
    videoFileName: Optional[str] = None
    videoDurationSec: Optional[float] = None
    createdAt: str
    updatedAt: str
    currentStep: ProjectStep = 'upload'
    inferenceMode: Optional[InferenceMode] = None
    uploadedVideoPath: Optional[str] = None
    uploadedSubtitlePath: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    # The editor can store normalized frontend rows, while the generation
    # pipeline stores richer backend script items such as
    # _id/timestamp/picture/narration/OST/evidence fields. Keep this payload
    # open so project hydration does not fail after script generation.
    scriptItems: Optional[list[dict[str, Any]]] = None


class ProjectListResponse(BaseModel):
    items: list[ProjectPayload]


class ProjectResponse(BaseModel):
    item: ProjectPayload


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    inferenceMode: Optional[InferenceMode] = 'fast'


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    status: Optional[ProjectStatus] = None
    thumbnailUrl: Optional[str] = None
    videoUrl: Optional[str] = None
    videoFileName: Optional[str] = None
    videoDurationSec: Optional[float] = None
    currentStep: Optional[ProjectStep] = None
    inferenceMode: Optional[InferenceMode] = None
    uploadedVideoPath: Optional[str] = None
    uploadedSubtitlePath: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    scriptItems: Optional[list[dict[str, Any]]] = None


class DeleteResponse(BaseModel):
    success: bool
