# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from app.services.movie_story import two_round_feature_modes as modes


def test_two_round_feature_mode_writes_script_and_highlight_companions(tmp_path, monkeypatch) -> None:
    output_script = tmp_path / "movie_story_script.json"

    def fake_generate(scene_evidence, *, raw_srt_text, api_key, base_url, model, style):
        assert scene_evidence == []
        assert "hello" in raw_srt_text
        assert api_key == "k"
        assert model == "m"
        return [
            {
                "section_title": "测试片段",
                "narration": "这里是双轮链生成的解说。",
                "raw_srt_source_start": 1.0,
                "raw_srt_source_end": 9.0,
            }
        ]

    monkeypatch.setattr(modes, "_generate_raw_srt_narration_items", fake_generate)

    result = modes.run_movie_story_two_round_feature_mode(
        request={
            "raw_srt_text": "1\n00:00:01,000 --> 00:00:09,000\nhello",
            "text_api_key": "k",
            "text_model": "m",
            "video_path": "E:/video.mp4",
        },
        output_script_path=str(output_script),
        visual_enabled=True,
    )

    assert result["success"] is True
    assert result["movie_story_mode"] == "two_round_visual"
    assert result["visual_evidence_requested"] is True

    script_items = json.loads(output_script.read_text(encoding="utf-8"))
    highlights = json.loads(Path(str(output_script).replace(".json", "_highlights.json")).read_text(encoding="utf-8"))
    narration_segments = json.loads(
        Path(str(output_script).replace(".json", "_highlight_narration_segments.json")).read_text(encoding="utf-8")
    )

    assert script_items[0]["generation_mode"] == "raw_srt_two_round_narration"
    assert highlights[0]["highlight_id"] == "highlight_001"
    assert narration_segments[0]["highlight_id"] == "highlight_001"

def test_two_round_feature_mode_reads_text_llm_settings_from_environment(tmp_path, monkeypatch) -> None:
    output_script = tmp_path / "movie_story_script.json"

    monkeypatch.setenv("AIVIDEO_TEXT_API_KEY", "env-key")
    monkeypatch.setenv("AIVIDEO_TEXT_MODEL", "env-model")
    monkeypatch.setenv("AIVIDEO_TEXT_BASE_URL", "env-base")
    monkeypatch.setattr(modes, "_collect_project_config_strings", lambda: [])

    def fake_generate(scene_evidence, *, raw_srt_text, api_key, base_url, model, style):
        assert api_key == "env-key"
        assert base_url == "env-base"
        assert model == "env-model"
        return [
            {
                "section_title": "环境变量配置测试",
                "narration": "这里是双轮链生成的解说。",
                "raw_srt_source_start": 1.0,
                "raw_srt_source_end": 9.0,
            }
        ]

    monkeypatch.setattr(modes, "_generate_raw_srt_narration_items", fake_generate)

    result = modes.run_movie_story_two_round_feature_mode(
        request={
            "raw_srt_text": "1\n00:00:01,000 --> 00:00:09,000\nhello",
        },
        output_script_path=str(output_script),
        visual_enabled=False,
    )

    assert result["success"] is True
    assert result["movie_story_mode"] == "two_round"

def test_two_round_feature_mode_does_not_mix_deepseek_model_with_dashscope_config_base_url(tmp_path, monkeypatch) -> None:
    output_script = tmp_path / "movie_story_script.json"

    monkeypatch.delenv("AIVIDEO_TEXT_BASE_URL", raising=False)
    monkeypatch.delenv("TEXT_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.setattr(
        modes,
        "_collect_project_config_strings",
        lambda: [
            ("llm.text.api_key", "config-key"),
            ("llm.text.model", "deepseek/deepseek-chat"),
            ("dashscope.base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ],
    )

    def fake_generate(scene_evidence, *, raw_srt_text, api_key, base_url, model, style):
        assert api_key == "config-key"
        assert model == "deepseek/deepseek-chat"
        assert base_url == ""
        return [
            {
                "section_title": "配置隔离测试",
                "narration": "这里是双轮链生成的解说。",
                "raw_srt_source_start": 1.0,
                "raw_srt_source_end": 9.0,
            }
        ]

    monkeypatch.setattr(modes, "_generate_raw_srt_narration_items", fake_generate)

    result = modes.run_movie_story_two_round_feature_mode(
        request={
            "raw_srt_text": "1\n00:00:01,000 --> 00:00:09,000\nhello",
        },
        output_script_path=str(output_script),
        visual_enabled=False,
    )

    assert result["success"] is True
