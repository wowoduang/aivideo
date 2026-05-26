# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_speaker_context_api_e2e.py

通过主 FastAPI app 测试 speaker_context 三个接口。
"""

import unittest

from fastapi.testclient import TestClient

from app.api.main import app


class TestSpeakerContextApiE2E(unittest.TestCase):
    """speaker_context API 端到端测试。"""

    def setUp(self) -> None:
        """创建测试客户端。"""
        self.client = TestClient(app)

    def test_preview_endpoint_under_api_v1(self) -> None:
        """preview endpoint 返回 SPEAKER 预览。"""
        response = self.client.post(
            "/api/v1/speaker-context/preview",
            json={
                "aliyun_result_json": _fake_aliyun_result(),
                "max_examples_per_speaker": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["speaker_preview"]["speaker_count"], 2)

    def test_bound_context_endpoint_under_api_v1(self) -> None:
        """bound-context endpoint 返回绑定后的 speaker_context。"""
        response = self.client.post(
            "/api/v1/speaker-context/bound-context",
            json={
                "subtitle_segments": _fake_subtitles(),
                "aliyun_result_json": _fake_aliyun_result(),
                "speaker_role_map": {
                    "SPEAKER_00": "朱重八",
                    "SPEAKER_01": "官兵",
                },
                "speaker_confidence_map": {
                    "SPEAKER_00": 0.90,
                    "SPEAKER_01": 0.88,
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        text = response.json()["data"]["speaker_context"]
        self.assertIn("00:04:44~00:04:48 | 朱重八 | 0.90 | confirmed", text)
        self.assertIn("00:07:44~00:07:52 | 官兵 | 0.88 | confirmed", text)

    def test_context_endpoint_without_role_map_keeps_speaker_id(self) -> None:
        """context endpoint 无角色映射时保留 SPEAKER_ID。"""
        response = self.client.post(
            "/api/v1/speaker-context/context",
            json={
                "subtitle_segments": _fake_subtitles(),
                "aliyun_result_json": _fake_aliyun_result(),
            },
        )

        self.assertEqual(response.status_code, 200)
        text = response.json()["data"]["speaker_context"]
        self.assertIn("SPEAKER_00 | 0.86 | diarized", text)
        self.assertNotIn("朱重八 | 0.98", text)


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
