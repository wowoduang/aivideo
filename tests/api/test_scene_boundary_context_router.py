# -*- coding: utf-8 -*-
from __future__ import annotations

"""测试 scene_boundary_context router。"""

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.scene_boundary_context import router


class TestSceneBoundaryContextRouter(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        self.client = TestClient(app)

    def test_preview_success(self) -> None:
        with patch(
            "app.api.routers.scene_boundary_context.build_scene_boundary_context_preview_payload",
            return_value={
                "scene_count": 1,
                "scene_source": {"provider": "story_runtime.build_story_candidates"},
                "scene_boundaries": [{"scene_id": "story_0001"}],
                "scene_boundary_context": "story_0001 | 00:00~00:40 | 40秒",
            },
        ) as mocked:
            response = self.client.post(
                "/api/v1/scene-boundary-context/preview",
                json={
                    "video_path": "E:/aivideo-workspace/frontend_uploads/video/demo.mp4",
                    "subtitle_segments": [{"start": 0, "end": 10, "text": "测试"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scene_count"], 1)
        self.assertEqual(data["scene_source"]["provider"], "story_runtime.build_story_candidates")
        self.assertIn("story_0001", data["scene_boundary_context"])
        mocked.assert_called_once()

    def test_preview_value_error_returns_422(self) -> None:
        with patch(
            "app.api.routers.scene_boundary_context.build_scene_boundary_context_preview_payload",
            side_effect=ValueError("subtitle_segments 为空"),
        ):
            response = self.client.post(
                "/api/v1/scene-boundary-context/preview",
                json={"video_path": "demo.mp4", "subtitle_segments": [{"start": 0, "end": 1, "text": "x"}]},
            )
        self.assertEqual(response.status_code, 422)
        self.assertIn("subtitle_segments 为空", response.json()["detail"])

    def test_preview_runtime_error_returns_500(self) -> None:
        with patch(
            "app.api.routers.scene_boundary_context.build_scene_boundary_context_preview_payload",
            side_effect=RuntimeError("story_runtime.build_story_candidates 未返回任何 prompt 场景片段"),
        ):
            response = self.client.post(
                "/api/v1/scene-boundary-context/preview",
                json={"video_path": "demo.mp4", "subtitle_segments": [{"start": 0, "end": 1, "text": "x"}]},
            )
        self.assertEqual(response.status_code, 500)
        self.assertIn("story_runtime.build_story_candidates 未返回任何 prompt 场景片段", response.json()["detail"])

    def test_preview_schema_error_returns_422(self) -> None:
        response = self.client.post(
            "/api/v1/scene-boundary-context/preview",
            json={"video_path": "demo.mp4", "subtitle_segments": [], "target_scene_count": 0},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
