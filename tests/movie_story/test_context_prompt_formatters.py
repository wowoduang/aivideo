# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_context_prompt_formatters.py

测试 speaker_context 和 scene_boundary_context 最终压缩输出格式。
"""

import unittest

from app.services.movie_story.context_prompt_formatters import build_context_prompt_sections
from app.services.movie_story.context_prompt_formatters import format_scene_boundary_context_for_prompt
from app.services.movie_story.context_prompt_formatters import format_speaker_context_for_prompt


class TestContextPromptFormatters(unittest.TestCase):
    """上下文压缩格式测试。"""

    def test_speaker_context_final_line_format(self) -> None:
        """说话人识别输出最终行格式。"""
        context = {
            "speaker_units": [
                {"start": 284.0, "end": 288.0, "speaker": "朱重八", "confidence": 0.95, "status": "confirmed"},
                {"start": 288.0, "end": 292.0, "speaker": "朱重八", "confidence": 0.84, "status": "candidate"},
            ]
        }

        text = format_speaker_context_for_prompt(context)

        self.assertIn("00:04:44~00:04:48 | 朱重八 | 0.95 | confirmed", text)
        self.assertIn("00:04:48~00:04:52 | 朱重八 | 0.84 | candidate", text)

    def test_low_confidence_candidate_is_marked_uncertain(self) -> None:
        """低于 0.7 的 candidate 输出 candidate（存疑）。"""
        context = {
            "speaker_units": [
                {"start": 472.0, "end": 480.0, "speaker": "母亲", "confidence": 0.65, "status": "candidate"}
            ]
        }

        text = format_speaker_context_for_prompt(context)

        self.assertIn("00:07:52~00:08:00 | 母亲 | 0.65 | candidate（存疑）", text)

    def test_scene_boundary_final_block_format(self) -> None:
        """场景边界输出最终块格式。"""
        context = {
            "scene_boundaries": [
                {
                    "scene_id": "scene_002",
                    "start": 464.0,
                    "end": 567.0,
                    "duration": 103,
                    "speaker_candidates": [
                        {"speaker": "官兵", "confidence": 0.86},
                        {"speaker": "母亲", "confidence": 0.78},
                        {"speaker": "朱重八", "confidence": 0.72},
                    ],
                    "visible_facts": ["官兵进入室内与屋内人物发生争执", "有袋装物被拿走"],
                    "visual_anchors": [{"time": 492.0, "fact": "官兵靠近屋内物品", "confidence": 0.76}],
                    "subtitle_keywords": ["欠税", "稻种", "喂马"],
                }
            ]
        }

        text = format_scene_boundary_context_for_prompt(context)

        self.assertIn("scene_002 | 00:07:44~00:09:27 | 103秒", text)
        self.assertIn("在场人物：官兵(0.86) 母亲(0.78) 朱重八(0.72)", text)
        self.assertIn("画面事实：官兵进入室内与屋内人物发生争执；有袋装物被拿走", text)
        self.assertIn("画面锚点：00:08:12 官兵靠近屋内物品(0.76)", text)
        self.assertIn("字幕关键词：欠税 稻种 喂马", text)

    def test_interpretive_scene_facts_are_filtered(self) -> None:
        """场景边界不得输出剧情解读句。"""
        context = {
            "scene_boundaries": [
                {
                    "scene_id": "scene_001",
                    "start": 0,
                    "end": 10,
                    "duration": 10,
                    "visible_facts": ["屋内多名人物争执", "这揭示了阶层压迫"],
                    "plot_function": "冲突爆发",
                }
            ]
        }

        text = format_scene_boundary_context_for_prompt(context)

        self.assertIn("屋内多名人物争执", text)
        self.assertNotIn("阶层压迫", text)
        self.assertNotIn("plot_function", text)

    def test_build_context_prompt_sections(self) -> None:
        """三段输入区按最终标题输出。"""
        text = build_context_prompt_sections(
            "原始字幕",
            speaker_context={"speaker_units": [{"start": 1, "end": 2, "speaker": "朱重八", "confidence": 0.95, "status": "confirmed"}]},
            scene_boundary_context={"scene_boundaries": []},
        )

        self.assertIn("【原始字幕】", text)
        self.assertIn("【说话人识别】", text)
        self.assertIn("【场景边界】", text)


if __name__ == "__main__":
    unittest.main()
