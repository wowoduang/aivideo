# -*- coding: utf-8 -*-
from __future__ import annotations

"""
scene_boundary_context.py

scene_boundary_context FastAPI router。

本 router 不做 fallback：
- 入参格式错误：422
- 服务层 ValueError：422
- 服务层 RuntimeError：500
- 其它异常：继续抛出，由全局错误处理处理
"""

__CONTEXT__ = {
    "layer": "api",
    "domain": "movie_story.scene_boundary_context_router",
    "entry_points": ["router", "preview_scene_boundary_context"],
    "called_by": ["FastAPI app include_router"],
    "decisions": [
        "2026-05: route 只负责 HTTP 入参/出参，不做 fallback。",
        "2026-05: 服务层明确失败时转换为 HTTPException，错误直接暴露给前端。",
    ],
    "pending": [
        "接入 app/api/main.py。",
        "接入前端预览按钮。",
    ],
    "ai_constraints": [
        "禁止新增 fallback。",
        "禁止静默降级。",
        "禁止把空 scene_boundary_context 当成功。",
    ],
}

from fastapi import APIRouter, HTTPException

from app.api.schemas.scene_boundary_context import SceneBoundaryContextPreviewRequest
from app.api.schemas.scene_boundary_context import SceneBoundaryContextPreviewResponse
from app.services.movie_story.scene_boundary_context_api_adapter import (
    build_scene_boundary_context_preview_payload,
)

router = APIRouter(prefix="/scene-boundary-context", tags=["scene-boundary-context"])


@router.post("/preview", response_model=SceneBoundaryContextPreviewResponse)
def preview_scene_boundary_context(
    request: SceneBoundaryContextPreviewRequest,
) -> SceneBoundaryContextPreviewResponse:
    """生成 scene_boundary_context 预览。"""
    try:
        payload = build_scene_boundary_context_preview_payload(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SceneBoundaryContextPreviewResponse(**payload)
