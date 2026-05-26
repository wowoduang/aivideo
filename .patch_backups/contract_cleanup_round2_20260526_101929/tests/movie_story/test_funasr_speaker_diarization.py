# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_funasr_speaker_diarization.py

测试正式 Fun-ASR speaker diarization 服务。
"""

import unittest
from typing import Any

from app.services.movie_story import funasr_speaker_diarization


class FakeBailianService:
    """模拟现有 asr_bailian 服务。"""

    def recognize_filetrans_audio(self, **kwargs: Any) -> dict:
        """返回带 speaker_id 的阿里 transcription JSON。"""
        assert kwargs["model"] == "fun-asr"
        assert kwargs["diarization_enabled"] is True
        return {
            "raw_result": {
                "transcripts": [
                    {
                        "sentences": [
                            {
                                "begin_time": 284000,
                                "end_time": 288000,
                                "text": "我要天天吃大饼",
                                "speaker_id": 0,
                            },
                            {
                                "begin_time": 464000,
                                "end_time": 472000,
                                "text": "欠税不交",
                                "speaker_id": 1,
                            },
                        ]
                    }
                ]
            }
        }


class TestFunasrSpeakerDiarization(unittest.TestCase):
    """正式 Fun-ASR speaker diarization 服务测试。"""

    def test_build_preview_from_audio(self) -> None:
        """能复用 asr_bailian 结果生成 speaker preview。"""
        original = funasr_speaker_diarization._create_bailian_asr_service
        funasr_speaker_diarization._create_bailian_asr_service = lambda: FakeBailianService()
        try:
            payload = funasr_speaker_diarization.build_funasr_speaker_preview_from_audio(
                "E:/aivideo-workspace/frontend_uploads/audio/test.wav"
            )
        finally:
            funasr_speaker_diarization._create_bailian_asr_service = original

        self.assertEqual(payload["provider"], "aliyun_funasr")
        self.assertEqual(payload["speaker_preview"]["speaker_count"], 2)
        self.assertEqual(payload["speaker_segments_count"], 2)


if __name__ == "__main__":
    unittest.main()
