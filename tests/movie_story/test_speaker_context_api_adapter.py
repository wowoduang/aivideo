# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_speaker_context_api_adapter.py

测试 speaker_context API 适配层。
"""

import unittest

from app.services.movie_story.speaker_context_api_adapter import (
    build_bound_context_response,
    build_context_response,
    build_preview_response,
)


class TestSpeakerContextApiAdapter(unittest.TestCase):
    """speaker_context API adapter 测试。"""

    def test_build_preview_response(self) -> None:
        """能构建 speaker preview 响应。"""
        response = build_preview_response(
            {
                "aliyun_result_json": _fake_aliyun_result(),
                "max_examples_per_speaker": 1,
            }
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["speaker_preview"]["speaker_count"], 2)

    def test_build_bound_context_response(self) -> None:
        """能根据角色绑定构建最终 speaker_context 响应。"""
        response = build_bound_context_response(
            {
                "subtitle_segments": _fake_subtitles(),
                "aliyun_result_json": _fake_aliyun_result(),
                "speaker_role_map": {"SPEAKER_00": "朱重八", "SPEAKER_01": "官兵"},
                "speaker_confidence_map": {"SPEAKER_00": 0.90, "SPEAKER_01": 0.88},
            }
        )

        self.assertTrue(response["ok"])
        self.assertIn("朱重八 | 0.90 | confirmed", response["data"]["speaker_context"])
        self.assertIn("官兵 | 0.88 | confirmed", response["data"]["speaker_context"])

    def test_build_context_response_without_role_map_keeps_speaker_id(self) -> None:
        """没有角色绑定时不猜角色名。"""
        response = build_context_response(
            {
                "subtitle_segments": _fake_subtitles(),
                "aliyun_result_json": _fake_aliyun_result(),
            }
        )

        self.assertTrue(response["ok"])
        self.assertIn("SPEAKER_00 | 0.86 | diarized", response["data"]["speaker_context"])

    def test_missing_required_field_raises_value_error(self) -> None:
        """缺少必填字段时抛出明确错误。"""
        with self.assertRaises(ValueError):
            build_preview_response({})


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
