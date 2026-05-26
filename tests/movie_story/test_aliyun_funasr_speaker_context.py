# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_aliyun_funasr_speaker_context.py

测试阿里云 Fun-ASR/Paraformer speaker_id 结果生成 {speaker_context}。
"""

import unittest

from app.services.movie_story.aliyun_funasr_speaker_context import build_speaker_context_text_from_aliyun_result
from app.services.movie_story.aliyun_funasr_speaker_context import build_speaker_context_text_from_aliyun_segments
from app.services.movie_story.aliyun_funasr_speaker_context import normalize_aliyun_transcription_result


class TestAliyunFunasrSpeakerContext(unittest.TestCase):
    """阿里云 Fun-ASR speaker_context 测试。"""

    def test_normalize_aliyun_transcription_result(self) -> None:
        """能从 transcripts.sentences 中提取 speaker_id 时间段。"""
        result = {
            "transcripts": [
                {
                    "sentences": [
                        {
                            "begin_time": 284000,
                            "end_time": 288000,
                            "text": "我要天天吃大饼",
                            "speaker_id": 0,
                        }
                    ]
                }
            ]
        }

        segments = normalize_aliyun_transcription_result(result)

        self.assertEqual(segments[0]["speaker_id"], "SPEAKER_00")
        self.assertEqual(segments[0]["start"], 284.0)
        self.assertEqual(segments[0]["end"], 288.0)

    def test_build_context_without_role_map_outputs_speaker_id(self) -> None:
        """无角色映射时输出 SPEAKER_ID，不猜角色名。"""
        subtitles = [{"start": 284.0, "end": 288.0, "text": "朱重八：我要天天吃大饼"}]
        aliyun_segments = [{"start": 284.0, "end": 288.0, "speaker_id": "SPEAKER_00", "confidence": 0.86}]

        text = build_speaker_context_text_from_aliyun_segments(subtitles, aliyun_segments)

        self.assertEqual(text, "00:04:44~00:04:48 | SPEAKER_00 | 0.86 | diarized")
        self.assertNotIn("朱重八 | 0.98", text)

    def test_build_context_with_role_map_outputs_role_name(self) -> None:
        """有人工映射时输出角色名。"""
        subtitles = [{"start": 284.0, "end": 288.0, "text": "我要天天吃大饼"}]
        aliyun_segments = [{"start": 284.0, "end": 288.0, "speaker_id": "SPEAKER_00", "confidence": 0.86}]

        text = build_speaker_context_text_from_aliyun_segments(
            subtitles,
            aliyun_segments,
            speaker_role_map={"SPEAKER_00": "朱重八"},
            speaker_confidence_map={"SPEAKER_00": 0.90},
        )

        self.assertEqual(text, "00:04:44~00:04:48 | 朱重八 | 0.90 | confirmed")

    def test_low_confidence_role_map_outputs_uncertain_candidate(self) -> None:
        """低置信度角色映射必须标存疑。"""
        subtitles = [{"start": 472.0, "end": 480.0, "text": "测试台词"}]
        aliyun_segments = [{"start": 472.0, "end": 480.0, "speaker_id": "SPEAKER_02", "confidence": 0.86}]

        text = build_speaker_context_text_from_aliyun_segments(
            subtitles,
            aliyun_segments,
            speaker_role_map={"SPEAKER_02": "母亲"},
            speaker_confidence_map={"SPEAKER_02": 0.65},
        )

        self.assertEqual(text, "00:07:52~00:08:00 | 母亲 | 0.65 | candidate（存疑）")

    def test_empty_input_returns_no_data(self) -> None:
        """空输入返回无可靠结果。"""
        text = build_speaker_context_text_from_aliyun_segments([], [])

        self.assertEqual(text, "暂无可靠说话人识别结果。")

    def test_build_from_aliyun_result(self) -> None:
        """可直接从阿里云完整 JSON 结果生成文本。"""
        subtitles = [{"start": 284.0, "end": 288.0, "text": "台词"}]
        result = {
            "transcripts": [
                {
                    "sentences": [
                        {
                            "begin_time": 284000,
                            "end_time": 288000,
                            "text": "台词",
                            "speaker_id": 1,
                        }
                    ]
                }
            ]
        }

        text = build_speaker_context_text_from_aliyun_result(subtitles, result)

        self.assertEqual(text, "00:04:44~00:04:48 | SPEAKER_01 | 0.86 | diarized")


if __name__ == "__main__":
    unittest.main()
