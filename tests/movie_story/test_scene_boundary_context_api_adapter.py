# -*- coding: utf-8 -*-
from __future__ import annotations

"""测试 scene_boundary_context API adapter 使用 story candidates。"""

import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.movie_story.scene_boundary_context_api_adapter import (
    build_scene_boundary_context_preview_payload,
)


class TestSceneBoundaryContextApiAdapter(unittest.TestCase):
    def test_build_preview_payload_uses_story_candidates(self) -> None:
        video_path = Path("tests/tmp_scene_boundary_context_adapter.mp4")
        video_path.write_bytes(b"fake")
        plot_chunks = [
            {"scene_id": "plot_001", "segment_id": "plot_001", "start": 0, "end": 10, "subtitle_text": "测试字幕"},
            {"scene_id": "plot_002", "segment_id": "plot_002", "start": 10, "end": 20, "subtitle_text": "第二段"},
        ]
        story_candidates = [
            {"story_id": "story_0001", "scene_id": "story_0001", "start": 0, "end": 20, "subtitle_text": "测试字幕 第二段"},
        ]
        try:
            with patch(
                "app.services.movie_story.scene_boundary_context_api_adapter.build_authoritative_plot_chunks",
                return_value=plot_chunks,
            ) as mocked_plot, patch(
                "app.services.movie_story.scene_boundary_context_api_adapter.refresh_authoritative_plot_map",
                return_value=plot_chunks,
            ) as mocked_refresh, patch(
                "app.services.movie_story.scene_boundary_context_api_adapter.build_story_candidates",
                return_value=story_candidates,
            ) as mocked_story:
                payload = build_scene_boundary_context_preview_payload(
                    {
                        "video_path": str(video_path),
                        "subtitle_segments": [
                            {"start": "00:00:01.000", "end": "00:00:03.000", "text": "测试 字幕"},
                            {"start": "00:00:12.000", "end": "00:00:15.000", "text": "第二段"},
                        ],
                        "target_scene_count": 20,
                    }
                )

            self.assertEqual(payload["scene_count"], 1)
            self.assertEqual(payload["scene_source"]["provider"], "story_runtime.build_story_candidates")
            self.assertEqual(payload["scene_source"]["plot_chunk_count"], 2)
            self.assertIn("story_0001", payload["scene_boundary_context"])
            self.assertIn("00:01~00:03 测试字幕", payload["scene_boundary_context"])
            self.assertIn("00:12~00:15 第二段", payload["scene_boundary_context"])
            mocked_plot.assert_called_once()
            mocked_refresh.assert_called_once()
            mocked_story.assert_called_once_with(plot_chunks)
        finally:
            video_path.unlink(missing_ok=True)

    def test_missing_video_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_scene_boundary_context_preview_payload(
                {"subtitle_segments": [{"start": 0, "end": 1, "text": "x"}]}
            )

    def test_nonexistent_video_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            build_scene_boundary_context_preview_payload(
                {
                    "video_path": "tests/not_exists_scene_boundary_context.mp4",
                    "subtitle_segments": [{"start": 0, "end": 1, "text": "x"}],
                }
            )

    def test_empty_subtitle_segments_raises(self) -> None:
        video_path = Path("tests/tmp_scene_boundary_context_empty_subs.mp4")
        video_path.write_bytes(b"fake")
        try:
            with self.assertRaises(ValueError):
                build_scene_boundary_context_preview_payload(
                    {"video_path": str(video_path), "subtitle_segments": []}
                )
        finally:
            video_path.unlink(missing_ok=True)

    def test_authoritative_plot_chunks_empty_raises(self) -> None:
        video_path = Path("tests/tmp_scene_boundary_context_empty_plot.mp4")
        video_path.write_bytes(b"fake")
        try:
            with patch(
                "app.services.movie_story.scene_boundary_context_api_adapter.build_authoritative_plot_chunks",
                return_value=[],
            ):
                with self.assertRaises(RuntimeError):
                    build_scene_boundary_context_preview_payload(
                        {
                            "video_path": str(video_path),
                            "subtitle_segments": [{"start": 0, "end": 1, "text": "x"}],
                        }
                    )
        finally:
            video_path.unlink(missing_ok=True)

    def test_story_candidates_empty_raises(self) -> None:
        video_path = Path("tests/tmp_scene_boundary_context_empty_story.mp4")
        video_path.write_bytes(b"fake")
        try:
            with patch(
                "app.services.movie_story.scene_boundary_context_api_adapter.build_authoritative_plot_chunks",
                return_value=[{"scene_id": "plot_001", "start": 0, "end": 10}],
            ), patch(
                "app.services.movie_story.scene_boundary_context_api_adapter.refresh_authoritative_plot_map",
                return_value=[{"scene_id": "plot_001", "start": 0, "end": 10}],
            ), patch(
                "app.services.movie_story.scene_boundary_context_api_adapter.build_story_candidates",
                return_value=[],
            ):
                with self.assertRaises(RuntimeError):
                    build_scene_boundary_context_preview_payload(
                        {
                            "video_path": str(video_path),
                            "subtitle_segments": [{"start": 0, "end": 1, "text": "x"}],
                        }
                    )
        finally:
            video_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
