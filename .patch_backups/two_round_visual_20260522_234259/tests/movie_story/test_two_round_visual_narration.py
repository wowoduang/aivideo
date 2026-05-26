# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.movie_story import two_round_visual_narration as visual


SRT_TEXT = """1
00:00:01,000 --> 00:00:03,000
你为什么回来？

2
00:00:08,000 --> 00:00:12,000
我不是来找你的。
"""


def test_generate_two_round_visual_narration_items_uses_visual_first_round(tmp_path, monkeypatch) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    monkeypatch.setattr(
        visual,
        "sample_keyframes_for_scene_context",
        lambda *args, **kwargs: [{"frame_id": "scene_frame", "timestamp": 1.0, "sampling_stage": "scene_context_low_density", "frame_path": str(tmp_path / "scene.jpg")}],
    )
    monkeypatch.setattr(
        visual,
        "sample_keyframes_for_visual_focus_segments",
        lambda *args, **kwargs: [{"frame_id": "focus_frame", "timestamp": 2.0, "sampling_stage": "visual_focus_detail", "frame_path": str(tmp_path / "focus.jpg")}],
    )
    (tmp_path / "scene.jpg").write_bytes(b"image")
    (tmp_path / "focus.jpg").write_bytes(b"image")

    def fake_first_round(**kwargs: Any) -> str:
        assert kwargs["image_paths"]
        assert "visual_focus_segments 不是 AI 推荐高光" in kwargs["prompt"]
        return "结构分析：人物关系已经根据画面校正。"

    def fake_text(prompt: str, *, api_key: str, base_url: str, model: str, timeout: int) -> str:
        assert "结构分析" in prompt
        return "【正式文案】\n**开场**\n[00:01 ~ 01:05]\n这是一段正式解说。"

    monkeypatch.setattr(visual, "call_multimodal_first_round_strict", fake_first_round)
    monkeypatch.setattr(visual, "_call_chat_completion", fake_text)

    items, metadata = visual.generate_two_round_visual_narration_items(
        raw_srt_text=SRT_TEXT,
        request={"video_path": str(video_path), "vision_api_key": "vk", "vision_model": "gemini/gemini-test"},
        output_dir=tmp_path,
        text_api_key="tk",
        text_base_url="",
        text_model="tm",
        style="general",
    )

    assert items
    assert Path(metadata["visual_context_path"]).exists()
    assert Path(metadata["analysis_prompt_path"]).exists()
