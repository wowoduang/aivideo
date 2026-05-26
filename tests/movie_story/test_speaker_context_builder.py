# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_speaker_context_builder.py

测试影视剧说话人标注上下文构建。
"""

import unittest

from app.services.movie_story.speaker_context_builder import build_speaker_context
from app.services.movie_story.speaker_context_builder import parse_explicit_speaker_label


class TestSpeakerContextBuilder(unittest.TestCase):
    """说话人上下文构建测试。"""

    def test_parse_explicit_colon_label(self) -> None:
        """显式“人物名：台词”可解析为高置信说话人。"""
        parsed = parse_explicit_speaker_label("朱重八：我要天天吃大饼")
        self.assertEqual(parsed, {"speaker": "朱重八", "text": "我要天天吃大饼"})

    def test_build_context_keeps_original_srt_time_axis(self) -> None:
        """voiceprint 时间只作证据，最终 unit 使用 SRT 时间。"""
        subtitles = [{"start": 284.0, "end": 288.0, "text": "我要天天吃大饼"}]
        matches = [{"start": 283.7, "end": 288.2, "speaker_id": "SPEAKER_00", "role_name": "朱重八", "confidence": 0.9}]
        context = build_speaker_context(subtitles, voiceprint_matches=matches)
        unit = context["speaker_units"][0]
        self.assertEqual(unit["start"], "00:04:44,000")
        self.assertEqual(unit["end"], "00:04:48,000")
        self.assertEqual(unit["speaker"], "朱重八")
        self.assertEqual(unit["status"], "confirmed")

    def test_low_confidence_role_is_uncertain(self) -> None:
        """低置信度匹配必须标记存疑。"""
        subtitles = [{"start": 10.0, "end": 12.0, "text": "测试台词"}]
        matches = [{"start": 10.0, "end": 12.0, "speaker_id": "SPEAKER_02", "role_name": "官兵", "confidence": 0.55}]
        context = build_speaker_context(subtitles, voiceprint_matches=matches)
        self.assertEqual(context["speaker_units"][0]["status"], "存疑")
        self.assertEqual(len(context["uncertain_units"]), 1)

    def test_empty_input_returns_empty_context(self) -> None:
        """空字幕输入不崩溃。"""
        context = build_speaker_context([])
        self.assertEqual(context["speaker_units"], [])
        self.assertEqual(context["uncertain_units"], [])


if __name__ == "__main__":
    unittest.main()
