# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_pyannote_speaker_context.py

测试基于 pyannote/diarization 结果生成 {speaker_context} 文本。
测试不依赖真实 pyannote 模型，只验证音频侧结果与 SRT 主时间轴的对齐和输出格式。
"""

import unittest

from app.services.movie_story.pyannote_speaker_context import build_speaker_context_text_from_segments


class TestPyannoteSpeakerContext(unittest.TestCase):
    """pyannote speaker_context 输出测试。"""

    def test_diarization_result_aligns_to_srt_timeline(self) -> None:
        """输出时间必须使用 SRT 时间轴，不使用 speech segment 时间。"""
        subtitles = [{"start": 284.0, "end": 288.0, "text": "测试台词"}]
        speeches = [{"start": 283.6, "end": 288.3, "speaker_id": "SPEAKER_00", "confidence": 0.88}]

        text = build_speaker_context_text_from_segments(subtitles, speech_segments=speeches)

        self.assertEqual(text, "00:04:44~00:04:48 | SPEAKER_00 | 0.88 | diarized")

    def test_manual_role_map_outputs_confirmed_role(self) -> None:
        """人工映射 SPEAKER_XX 后输出角色名。"""
        subtitles = [{"start": 284.0, "end": 288.0, "text": "测试台词"}]
        speeches = [{"start": 284.0, "end": 288.0, "speaker_id": "SPEAKER_00", "confidence": 0.96}]

        text = build_speaker_context_text_from_segments(
            subtitles,
            speech_segments=speeches,
            speaker_role_map={"SPEAKER_00": "朱重八"},
        )

        self.assertEqual(text, "00:04:44~00:04:48 | 朱重八 | 0.96 | confirmed")

    def test_low_confidence_mapping_is_uncertain_candidate(self) -> None:
        """低置信度角色映射必须标记 candidate（存疑）。"""
        subtitles = [{"start": 472.0, "end": 480.0, "text": "测试台词"}]
        speeches = [{"start": 472.0, "end": 480.0, "speaker_id": "SPEAKER_02", "confidence": 1.0}]
        role_map = {"SPEAKER_02": {"role_name": "母亲", "confidence": 0.65}}

        text = build_speaker_context_text_from_segments(
            subtitles,
            speech_segments=speeches,
            speaker_role_map=role_map,
        )

        self.assertEqual(text, "00:07:52~00:08:00 | 母亲 | 0.65 | candidate（存疑）")

    def test_subtitle_text_is_not_used_to_guess_role_name(self) -> None:
        """字幕中出现“朱重八：”也不能在没有音频证据时输出人名。"""
        subtitles = [{"start": 284.0, "end": 288.0, "text": "朱重八：我要天天吃大饼"}]

        text = build_speaker_context_text_from_segments(subtitles, speech_segments=[])

        self.assertEqual(text, "暂无可靠说话人识别结果。")

    def test_no_overlap_returns_no_reliable_result(self) -> None:
        """没有时间重叠时不输出说话人。"""
        subtitles = [{"start": 284.0, "end": 288.0, "text": "测试台词"}]
        speeches = [{"start": 100.0, "end": 102.0, "speaker_id": "SPEAKER_00", "confidence": 0.9}]

        text = build_speaker_context_text_from_segments(subtitles, speech_segments=speeches)

        self.assertEqual(text, "暂无可靠说话人识别结果。")


if __name__ == "__main__":
    unittest.main()
