from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.models.schema import VideoClipParams


class VideoJobCreateRequest(BaseModel):
    params: VideoClipParams
    task_id: str = Field(default="", description="Optional custom task id for local orchestration.")
    project_id: str = Field(default="", description="Optional project id for metadata indexing.")


class HighlightScriptRequest(BaseModel):
    video_path: str
    mode: str = "highlight_recut"
    target_duration_seconds: int = 480
    movie_title: str = ""
    highlight_profile: str = "auto"
    subtitle_path: str = ""
    narration_text: str = ""
    narration_audio_path: str = ""
    prefer_raw_audio: bool = True
    visual_mode: str = "auto"
    regenerate_subtitle: bool = False
    subtitle_backend: str = ""


class HighlightJobCreateRequest(BaseModel):
    request: HighlightScriptRequest
    task_id: str = Field(default="", description="Optional custom task id for local orchestration.")
    project_id: str = Field(default="", description="Optional project id for metadata indexing.")


class MovieStoryScriptRequest(BaseModel):
    video_path: str
    subtitle_path: str = ""
    video_theme: str = ""
    temperature: float = 0.7
    narration_style: str = "general"
    generation_mode: str = "balanced"
    movie_story_strategy: str = "two_round"
    # movie_story two-round feature mode.
    # two_round: text-only subtitle-first two-round chain.
    # two_round_visual: first-round multimodal chain.  Backend samples factual
    # scene frames and visual_focus_segments before the first prompt; these
    # focus segments are not AI-recommended highlights or final export clips.
    movie_story_mode: str = "two_round"
    movie_story_feature_mode: str = "two_round"
    movie_story_visual_focus_segments: List[Dict[str, Any]] = Field(default_factory=list)
    visual_mode: str = "auto"
    target_duration_minutes: int = 8
    narrative_strategy: str = "chronological"
    accuracy_priority: str = "high"
    highlight_only: bool = False
    highlight_selectivity: str = "balanced"
    asr_backend: str = ""
    cache_mode: str = "clear_and_regenerate"
    prologue_strategy: str = "speech_first"
    manual_prologue_end_time: str = ""
    skip_llm: bool = False


class MovieStoryJobCreateRequest(BaseModel):
    request: MovieStoryScriptRequest
    task_id: str = Field(default="", description="Optional custom task id for local orchestration.")
    project_id: str = Field(default="", description="Optional project id for metadata indexing.")


class SubtitleScriptRequest(BaseModel):
    video_path: str
    backend: str = ""
    model: str = ""


class SubtitleJobCreateRequest(BaseModel):
    request: SubtitleScriptRequest
    task_id: str = Field(default="", description="Optional custom task id for local orchestration.")
    project_id: str = Field(default="", description="Optional project id for metadata indexing.")


class JobAcceptedResponse(BaseModel):
    task_id: str
    job_type: str
    status: str
    progress: int
    task_dir: str


class JobCancelResponse(BaseModel):
    task_id: str
    status: str
    message: str = ""


class JobStatusResponse(BaseModel):
    task_id: str
    job_type: str
    status: str
    state: int
    progress: int
    message: str = ""
    error: str = ""
    task_dir: str
    videos: List[str] = Field(default_factory=list)
    combined_videos: List[str] = Field(default_factory=list)
    is_running: bool = False
    payload: Dict[str, Any] = Field(default_factory=dict)


class JobHistoryItem(BaseModel):
    task_id: str
    job_type: str
    status: str
    progress: int = 0
    message: str = ""
    error: str = ""
    task_dir: str = ""
    project_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    is_running: bool = False


class JobListResponse(BaseModel):
    items: List[JobHistoryItem] = Field(default_factory=list)


class JobEventItem(BaseModel):
    id: str
    task_id: str
    event_type: str
    status: str = ""
    progress: int = 0
    message: str = ""
    project_id: str = ""
    job_type: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class JobEventListResponse(BaseModel):
    items: List[JobEventItem] = Field(default_factory=list)


class JobWorkerStatusResponse(BaseModel):
    backend: str
    max_workers: int = 0
    tracked_jobs: int = 0
    queued: int = 0
    running: int = 0
    done: int = 0
    cancel_requested: int = 0
    active_processes: int = 0
    process_tasks: Dict[str, int] = Field(default_factory=dict)
    queue: str = ""
    redis_url: str = ""
    available: bool = True
    error: str = ""


class WorkspaceInfoResponse(BaseModel):
    project_root: str
    workspace_root: str
    config_file: str
    project_version: str
    layout: Dict[str, str]
    task_root: str
