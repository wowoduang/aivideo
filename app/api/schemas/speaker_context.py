# -*- coding: utf-8 -*-
from __future__ import annotations

"""
speaker_context.py

说话人识别 API 的请求/响应 schema。
"""

__CONTEXT__ = {
    "layer": "api_schema",
    "domain": "movie_story.speaker_context",
    "entry_points": [
        "SpeakerPreviewRequest",
        "SpeakerBoundContextRequest",
        "SpeakerContextRequest",
        "SpeakerContextResponse",
    ],
    "called_by": ["app.api.routers.speaker_context"],
    "decisions": [
        "2026-05: 前端先请求 speaker preview，再提交 SPEAKER_ID -> 角色名映射。",
        "2026-05: aliyun_result_json 是阿里云 Fun-ASR/Paraformer transcription JSON。",
        "2026-05: subtitle_segments 只作为输出主时间轴，不用于猜角色名。",
    ],
    "pending": [
        "接入项目配置读写后，可增加 project_id 版本请求。",
    ],
    "ai_constraints": [
        "禁止 schema 层出现业务逻辑。",
        "禁止在 schema 层推断角色名。",
    ],
}

from typing import Any

from pydantic import BaseModel
from pydantic import Field


class SpeakerPreviewRequest(BaseModel):
    """生成 SPEAKER_ID 预览请求。"""

    aliyun_result_json: dict[str, Any]
    max_examples_per_speaker: int = Field(default=5, ge=1, le=20)


class SpeakerBoundContextRequest(BaseModel):
    """根据前端角色绑定生成最终 speaker_context 请求。"""

    subtitle_segments: list[dict[str, Any]]
    aliyun_result_json: dict[str, Any]
    speaker_role_map: dict[str, Any] = Field(default_factory=dict)
    speaker_confidence_map: dict[str, float] = Field(default_factory=dict)
    max_lines: int = Field(default=260, ge=1, le=2000)


class SpeakerContextRequest(BaseModel):
    """一次性生成 speaker_preview + speaker_context 请求。"""

    subtitle_segments: list[dict[str, Any]]
    aliyun_result_json: dict[str, Any]
    speaker_role_map: dict[str, Any] = Field(default_factory=dict)
    speaker_confidence_map: dict[str, float] = Field(default_factory=dict)
    max_examples_per_speaker: int = Field(default=5, ge=1, le=20)
    max_lines: int = Field(default=260, ge=1, le=2000)


class SpeakerContextResponse(BaseModel):
    """通用 speaker_context 响应。"""

    ok: bool
    data: dict[str, Any]

class FunasrSpeakerPreviewRequest(BaseModel):
    """复用现有百炼 OSS/filetrans 链路生成 SPEAKER 预览请求。"""

    audio_path: str
    max_examples_per_speaker: int = Field(default=5, ge=1, le=20)

