# -*- coding: utf-8 -*-
from __future__ import annotations

"""
scene_boundary_context.py

scene_boundary_context API schema。

只描述请求/响应结构，不做业务逻辑。
"""

from typing import Any

from pydantic import BaseModel, Field


class SceneBoundaryContextPreviewRequest(BaseModel):
    """场景边界预览请求。"""

    video_path: str = Field(..., description="本地视频文件路径。")
    subtitle_segments: list[dict[str, Any]] = Field(..., description="字幕片段列表，必须包含 start/end/text。")
    target_scene_count: int = Field(default=80, ge=1, le=300, description="输出到 context 的场景片段上限。")


class SceneBoundaryContextPreviewResponse(BaseModel):
    """场景边界预览响应。"""

    scene_count: int
    scene_source: dict[str, Any]
    scene_boundaries: list[dict[str, Any]]
    scene_boundary_context: str
