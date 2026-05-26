# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_scene_boundary_context_formatter.py

测试从旧 scene 时间轴格式化 scene_boundary_context。
"""

import unittest

from app.services.movie_story.scene_boundary_context_formatter import (
    build_scene_boundary_context_payload_from_scenes,
)


class TestSceneBoundaryContextFormatter(unittest.TestCase):
    """scene_boundary_context formatter 测试。"""

    def test_format_uses_old_scene_timeline_and_ordered_subtitles(self) -> None:
        """按旧 scene start/end 截字幕，并按时间顺序保留原文。"""
        payload = build_scene_boundary_context_payload_from_scenes(
            scene_segments=[
                {"scene_id": "scene_002", "start": 10, "end": 20, "keyframe_candidates": [12, 18]},
                {"scene_id": "scene_001", "start": 0, "end": 9, "keyframe_candidates": [4]},
            ],
            subtitle_segments=[
                {"start": "00:00:03.000", "end": "00:00:05.000", "text": "第一句 原文"},
                {"start": "00:00:12.000", "end": "00:00:15.000", "text": "第二句 原文"},
                {"start": "00:00:16.000", "end": "00:00:19.000", "text": "第三句 原文"},
            ],
            max_scene_count=10,
        )

        context = payload["scene_boundary_context"]
        self.assertEqual(payload["scene_count"], 2)
        self.assertIn("【场景边界】", context)
        self.assertIn("scene_001 | 00:00~00:09 | 9秒", context)
        self.assertIn("关键帧锚点：00:04", context)
        self.assertIn("00:03~00:05 第一句原文", context)
        self.assertIn("scene_002 | 00:10~00:20 | 10秒", context)
        self.assertIn("关键帧锚点：00:12, 00:18", context)
        self.assertIn("00:12~00:15 第二句原文", context)
        self.assertIn("00:16~00:19 第三句原文", context)
        self.assertNotIn("字幕关键词", context)
        self.assertNotIn("画面事实：未提供", context)

    def test_max_scene_count_limits_output_without_resorting(self) -> None:
        """输出上限只截断旧 scene 时间序列，不另写重点筛选算法。"""
        payload = build_scene_boundary_context_payload_from_scenes(
            scene_segments=[
                {"scene_id": "scene_001", "start": 0, "end": 5},
                {"scene_id": "scene_002", "start": 5, "end": 10},
            ],
            subtitle_segments=[
                {"start": 0, "end": 2, "text": "第一句"},
                {"start": 6, "end": 8, "text": "第二句"},
            ],
            max_scene_count=1,
        )

        self.assertEqual(payload["scene_count"], 1)
        self.assertIn("scene_001", payload["scene_boundary_context"])
        self.assertNotIn("scene_002", payload["scene_boundary_context"])


if __name__ == "__main__":
    unittest.main()
