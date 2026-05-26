# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_scene_boundary_context_router_registered.py

确认 scene_boundary_context router 已注册到主 FastAPI app。
"""


def test_scene_boundary_context_router_registered() -> None:
    """主 app 应包含 scene-boundary-context preview 路由。"""
    from app.api.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/scene-boundary-context/preview" in paths
