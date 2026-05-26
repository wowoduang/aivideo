from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class NarrationScriptSegmentPayload(BaseModel):
    id: str
    index: int
    start: float
    end: float
    duration: float
    startTime: str
    endTime: str
    timestamp: str
    originalSubtitle: str = ""
    narration: str = ""
    role: str = "setup"
    role_label: str = "剧情段"
    emotion: str = "neutral"
    evidence_refs: list[str] = Field(default_factory=list)
    estimated_tts_duration_sec: float = 0
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NarrationEvidencePayload(BaseModel):
    id: str
    start: float
    end: float
    duration: float
    type: str
    content: str = ""
    characters: list[Any] = Field(default_factory=list)
    scene: str = ""
    confidence: float = 0.0
    raw_ref: str = ""


class NarrationQualitySegmentPayload(BaseModel):
    segment_id: str
    index: int
    start: float
    end: float
    role: str
    role_label: str
    emotion: str
    factuality_score: float
    humanlike_score: float
    tts_alignment_score: float
    estimated_tts_duration_sec: float
    target_duration_sec: float
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class NarrationQualityReportPayload(BaseModel):
    version: str
    created_at: str
    summary: dict[str, Any]
    unsupported_claims: list[dict[str, Any]] = Field(default_factory=list)
    segments: list[NarrationQualitySegmentPayload] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class NarrationTimelineBlockPayload(BaseModel):
    id: str
    start: float
    end: float
    duration: float
    label: str
    narration: str = ""
    emotion: str = "neutral"
    evidence_support_score: float = 0.0
    evidence_ids: list[Any] = Field(default_factory=list)
    estimated_tts_duration_sec: float = 0


class NarrationWorkbenchResponse(BaseModel):
    project_id: str
    script_segments: list[NarrationScriptSegmentPayload]
    evidence_pack: list[NarrationEvidencePayload]
    quality_report: NarrationQualityReportPayload
    timeline_blocks: list[NarrationTimelineBlockPayload]
    latest_artifacts: dict[str, Any] = Field(default_factory=dict)


class NarrationQualityRequest(BaseModel):
    script_items: Optional[list[dict[str, Any]]] = None
    evidence_pack: Optional[list[dict[str, Any]]] = None
    speed: float = 1.0
    save_report: bool = False


class NarrationHumanizeRequest(BaseModel):
    script_items: list[dict[str, Any]] = Field(default_factory=list)
    persona: str = "suspense"
    intensity: float = 0.65
    save_version: bool = False


class NarrationHumanizeResponse(BaseModel):
    persona: str
    persona_label: str
    intensity: float
    script_items: list[dict[str, Any]]
    changes: list[dict[str, Any]] = Field(default_factory=list)
    quality_report: NarrationQualityReportPayload
    artifact: Optional[dict[str, Any]] = None


class NarrationScriptVersionRequest(BaseModel):
    script_items: list[dict[str, Any]] = Field(default_factory=list)
    label: str = Field(default="手动脚本版本", min_length=1, max_length=120)
    note: str = Field(default="", max_length=800)
    quality_report: Optional[dict[str, Any]] = None


class NarrationScriptVersionResponse(BaseModel):
    artifact: dict[str, Any]
    quality_report: NarrationQualityReportPayload


class NarrationScriptVersionListResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class HighlightSelectionItemPayload(BaseModel):
    id: str
    source_id: str = ""
    index: int = 0
    rank: int = 0
    selected: bool = True
    locked: bool = False
    video_start: float = 0
    video_end: float = 0
    duration: float = 0
    title: str = ""
    summary: str = ""
    reason: str = ""
    selection_reasons: list[str] = Field(default_factory=list)
    scores: dict[str, Any] = Field(default_factory=dict)
    character_trace: dict[str, Any] = Field(default_factory=dict)
    source_type: str = "highlight"
    raw: dict[str, Any] = Field(default_factory=dict)


class HighlightSelectionResponse(BaseModel):
    project_id: str
    items: list[HighlightSelectionItemPayload] = Field(default_factory=list)
    selected_count: int = 0
    total_count: int = 0
    selected_duration_sec: float = 0
    latest_artifact: Optional[dict[str, Any]] = None
    source: str = "generated"


class HighlightSelectionSaveRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    note: str = Field(default="", max_length=800)


class HighlightSelectionSaveResponse(BaseModel):
    project_id: str
    artifact: dict[str, Any]
    selection: HighlightSelectionResponse
