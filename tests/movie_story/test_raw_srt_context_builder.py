# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_raw_srt_context_builder.py

测试 raw_srt 第一轮输入区构建。
"""

import unittest

from app.services.movie_story.raw_srt_context_builder import build_first_round_input


class TestRawSrtContextBuilder(unittest.TestCase):
    """raw_srt 第一轮上下文测试。"""

    def test_prompt_contains_three_input_sections(self) -> None:
        """第一轮输入必须包含三个明确标题。"""
        text = build_first_round_input(
            "1\n00:00:01,000 --> 00:00:02,000\n测试字幕",
            speaker_context={"speaker_units": []},
            scene_boundary_context={"scene_boundaries": []},
        )
        self.assertIn("【原始字幕】", text)
        self.assertIn("【说话人标注】", text)
        self.assertIn("【场景边界】", text)

    def test_empty_contexts_are_explicitly_marked(self) -> None:
        """空辅助上下文必须显式标注暂无可靠数据。"""
        text = build_first_round_input("字幕", speaker_context=None, scene_boundary_context=None)
        self.assertIn("暂无可靠数据", text)

    def test_scene_boundary_is_not_described_as_interpretation(self) -> None:
        """输入规则必须说明场景边界不是剧情解读。"""
        text = build_first_round_input("字幕")
        self.assertIn("不是剧情解读", text)


if __name__ == "__main__":
    unittest.main()
