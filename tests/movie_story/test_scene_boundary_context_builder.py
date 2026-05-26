# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_scene_boundary_context_builder.py

测试场景边界事实上下文构建。
"""

import unittest

from app.services.movie_story.scene_boundary_context_builder import build_scene_boundary_context


class TestSceneBoundaryContextBuilder(unittest.TestCase):
    """场景边界上下文测试。"""

    def test_interpretive_fields_are_removed(self) -> None:
        """解释性字段不得进入 scene_boundary_context。"""
        subtitles = [{"start": 0.0, "end": 10.0, "text": "欠税 稻种"}]
        candidates = [{
            "scene_id": "scene_001",
            "start": 0.0,
            "end": 10.0,
            "visible_facts": ["屋内多名人物发生争执。", "这揭示了阶层压迫。"],
            "plot_function": "冲突爆发",
            "real_narrative_state": "推动核心矛盾",
        }]
        context = build_scene_boundary_context(subtitles, scene_candidates=candidates)
        scene = context["scene_boundaries"][0]
        self.assertNotIn("plot_function", scene)
        self.assertNotIn("real_narrative_state", scene)
        self.assertEqual(scene["visible_facts"], ["屋内多名人物发生争执。"])

    def test_scene_contains_required_time_fields(self) -> None:
        """场景必须包含 start/end/duration。"""
        subtitles = [{"start": 1.0, "end": 5.0, "text": "测试字幕"}]
        context = build_scene_boundary_context(subtitles)
        scene = context["scene_boundaries"][0]
        self.assertIn("start", scene)
        self.assertIn("end", scene)
        self.assertIn("duration", scene)

    def test_speaker_candidates_are_collected_by_range(self) -> None:
        """场景范围内说话人候选会被汇总。"""
        subtitles = [{"start": 0.0, "end": 8.0, "text": "测试字幕"}]
        speaker_context = {"speaker_units": [{"start": "00:00:01,000", "end": "00:00:02,000", "speaker": "朱重八", "confidence": 0.9, "status": "confirmed"}]}
        context = build_scene_boundary_context(subtitles, speaker_context=speaker_context)
        self.assertEqual(context["scene_boundaries"][0]["speaker_candidates"][0]["speaker"], "朱重八")

    def test_empty_input_returns_no_scene_boundaries(self) -> None:
        """空输入不崩溃。"""
        context = build_scene_boundary_context([])
        self.assertEqual(context["scene_boundaries"], [])


if __name__ == "__main__":
    unittest.main()
