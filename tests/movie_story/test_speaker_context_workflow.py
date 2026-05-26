# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_speaker_context_workflow.py

测试阿里云 Fun-ASR 说话人预览、角色绑定和最终 speaker_context 工作流。
"""

import unittest

from app.services.movie_story.speaker_context_workflow import (
    build_bound_speaker_context_payload,
    build_speaker_context_payload,
    build_speaker_preview_payload,
)


class TestSpeakerContextWorkflow(unittest.TestCase):
    """speaker_context 工作流测试。"""

    def test_build_speaker_preview_payload(self) -> None:
        """能从阿里云 JSON 生成 SPEAKER 预览。"""
        payload = build_speaker_preview_payload(_fake_aliyun_result())

        self.assertEqual(payload["provider"], "aliyun_funasr")
        self.assertEqual(payload["speaker_segments_count"], 3)
        self.assertEqual(payload["speaker_preview"]["speaker_count"], 2)

    def test_build_bound_speaker_context_payload(self) -> None:
        """前端绑定 SPEAKER_ID 后能生成角色名 speaker_context。"""
        payload = build_bound_speaker_context_payload(
            _fake_subtitles(),
            _fake_aliyun_result(),
            speaker_role_map={
                "SPEAKER_00": "朱重八",
                "SPEAKER_01": "官兵",
                "SPEAKER_99": "无效角色",
            },
            speaker_confidence_map={
                "SPEAKER_00": 0.90,
                "SPEAKER_01": 0.88,
            },
        )

        self.assertEqual(payload["speaker_role_map"], {"SPEAKER_00": "朱重八", "SPEAKER_01": "官兵"})
        self.assertIn("00:04:44~00:04:48 | 朱重八 | 0.90 | confirmed", payload["speaker_context"])
        self.assertIn("00:07:44~00:07:52 | 官兵 | 0.88 | confirmed", payload["speaker_context"])
        self.assertNotIn("无效角色", payload["speaker_context"])

    def test_build_speaker_context_payload_without_role_map_keeps_speaker_id(self) -> None:
        """没有角色绑定时保留 SPEAKER_ID，不猜角色名。"""
        payload = build_speaker_context_payload(_fake_subtitles(), _fake_aliyun_result())

        self.assertIn("00:04:44~00:04:48 | SPEAKER_00 | 0.86 | diarized", payload["speaker_context"])
        self.assertNotIn("朱重八 | 0.98", payload["speaker_context"])


def _fake_subtitles() -> list[dict]:
    """构造字幕段。"""
    return [
        {"start": 284.0, "end": 288.0, "text": "朱重八：我要天天吃大饼"},
        {"start": 288.0, "end": 292.0, "text": "还要让你们也天天吃"},
        {"start": 464.0, "end": 472.0, "text": "欠税不交"},
    ]


def _fake_aliyun_result() -> dict:
    """构造阿里云识别结果。"""
    return {
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
                        "begin_time": 288000,
                        "end_time": 292000,
                        "text": "还要让你们也天天吃",
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


if __name__ == "__main__":
    unittest.main()
