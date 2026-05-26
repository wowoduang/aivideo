# -*- coding: utf-8 -*-
from __future__ import annotations

"""Real two_round_visual pipeline with shot/scene segmentation and focus sampling."""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "role": "first-round multimodal understanding with deterministic visual evidence prep",
    "called_by": ["app/services/movie_story/two_round_feature_modes.py"],
    "constraints": [
        "no fallback",
        "first-round focus segments are not final highlights",
        "second round should use two_round_visual text config or same vendor config",
    ],
}

from pathlib import Path
from typing import Any
import re

from loguru import logger

from app.services.movie_story.shot_boundary_detector import detect_shot_boundaries
from app.services.movie_story.scene_segmenter import build_scene_segments
from app.services.movie_story.two_round_visual_input_packager import build_two_round_visual_input_package
from app.services.movie_story.two_round_narration import build_analysis_prompt, build_writer_prompt, _call_chat_completion
from app.services.movie_story.visual_focus_segments import build_visual_focus_segments
from app.services.movie_story.visual_timeline_sampler import sample_focus_segment_frames, sample_global_scene_frames

ANALYSIS_SYSTEM_PROMPT = """你正在执行 two_round_visual 的第一轮多模态结构理解。
后端提供给你的图片、场景边界、字幕、视觉重点片段都只是事实证据。
请结合这些材料，重点解决：谁在说话、谁是说话对象、谁在动作、场景里有哪些人。
不要把后端提供的事实材料改写成解说文案。
严格按照第一轮结构分析任务完成输出。"""


def generate_two_round_visual_narration_items(
    *,
    request: dict[str, Any],
    project_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_srt_text = str(request.get("raw_srt_text") or "").strip()
    if not raw_srt_text:
        raise ValueError("two_round_visual requires raw_srt_text")
    video_path = Path(str(request.get("video_path") or "")).expanduser()
    if not video_path.exists():
        raise FileNotFoundError(f"two_round_visual requires video_path: {video_path}")
    output_dir = _build_output_dir(project_root=project_root, request=request)
    subtitles = _parse_srt_like_text(raw_srt_text=raw_srt_text)
    shots = detect_shot_boundaries(video_path=video_path)
    scenes = build_scene_segments(shot_boundaries=shots, subtitles=subtitles)
    manual_focus = list(request.get("visual_focus_segments") or [])
    focus_segments = build_visual_focus_segments(
        scene_segments=scenes,
        subtitles=subtitles,
        manual_segments=manual_focus,
        max_segments=int(request.get("two_round_visual_max_focus_segments", 6)),
    )
    logger.info("auto visual_focus_segments built: count={}", len(focus_segments))
    global_frames = sample_global_scene_frames(
        video_path=video_path,
        scene_segments=scenes,
        output_dir=output_dir,
        max_frames=int(request.get("two_round_visual_max_global_frames", 12)),
    )
    focus_frames = sample_focus_segment_frames(
        video_path=video_path,
        focus_segments=focus_segments,
        output_dir=output_dir,
        frames_per_segment=int(request.get("two_round_visual_focus_frames_per_segment", 2)),
    )
    package = build_two_round_visual_input_package(
        raw_srt_text=raw_srt_text,
        scene_segments=scenes,
        focus_segments=focus_segments,
        global_frames=global_frames,
        focus_frames=focus_frames,
    )
    analysis_text = _run_first_round_multimodal(
        request=request,
        package=package,
    )
    writer_prompt = build_writer_prompt(analysis_text)
    second_round_text = _run_second_round_text(request=request, writer_prompt=writer_prompt)
    items = _parse_timecoded_items(second_round_text)
    if not items:
        raise RuntimeError("two_round_visual second round returned no parseable timecoded narration rows")
    metadata = {
        "shot_boundaries": shots,
        "scene_segments": scenes,
        "visual_focus_segments": focus_segments,
        "global_frames": global_frames,
        "focus_frames": focus_frames,
        "first_round_analysis": analysis_text,
    }
    return items, metadata


def _build_output_dir(*, project_root: Path, request: dict[str, Any]) -> Path:
    project_id = str(request.get("project_id") or request.get("job_id") or "standalone")
    output_dir = project_root / "movie_story_visual" / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _parse_srt_like_text(*, raw_srt_text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?P<start>\d{2}:\d{2}:\d{2}(?:[\.,]\d{1,3})?)\s*-->\s*"
        r"(?P<end>\d{2}:\d{2}:\d{2}(?:[\.,]\d{1,3})?)\s*(?P<text>.*?)(?=\n\d+\n|\Z)",
        re.S,
    )
    segments: list[dict[str, Any]] = []
    for index, match in enumerate(pattern.finditer(raw_srt_text), start=1):
        segments.append(
            {
                "subtitle_id": f"sub_{index:04d}",
                "start": _parse_timestamp(match.group("start")),
                "end": _parse_timestamp(match.group("end")),
                "text": " ".join(match.group("text").split()),
            }
        )
    if segments:
        return segments
    fallback_lines = [line.strip() for line in raw_srt_text.splitlines() if line.strip()]
    window = 4.0
    for index, line in enumerate(fallback_lines, start=1):
        start = (index - 1) * window
        segments.append({"subtitle_id": f"sub_{index:04d}", "start": start, "end": start + window, "text": line})
    return segments


def _parse_timestamp(value: str) -> float:
    clean = value.replace(",", ".")
    hour, minute, second = clean.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(second)


def _run_first_round_multimodal(*, request: dict[str, Any], package: dict[str, Any]) -> str:
    analysis_prompt = build_analysis_prompt(package["prompt_context"])
    full_prompt = ANALYSIS_SYSTEM_PROMPT + "\n\n" + analysis_prompt
    return str(
        _call_chat_completion(
            prompt=full_prompt,
            image_paths=list(package["image_paths"]),
            model_name=str(request.get("vision_litellm_model_name") or request.get("vision_model_name") or ""),
            api_key=str(request.get("vision_litellm_api_key") or request.get("vision_api_key") or ""),
            base_url=str(request.get("vision_litellm_base_url") or request.get("vision_base_url") or ""),
            provider=str(request.get("vision_llm_provider") or request.get("vision_provider") or ""),
        )
    )


def _run_second_round_text(*, request: dict[str, Any], writer_prompt: str) -> str:
    model_name = str(
        request.get("two_round_visual_text_model_name")
        or request.get("vision_text_model_name")
        or request.get("vision_litellm_model_name")
        or ""
    )
    api_key = str(request.get("two_round_visual_text_api_key") or request.get("vision_litellm_api_key") or "")
    base_url = str(request.get("two_round_visual_text_base_url") or request.get("vision_litellm_base_url") or "")
    provider = str(request.get("two_round_visual_text_provider") or request.get("vision_llm_provider") or "")
    return str(
        _call_chat_completion(
            prompt=writer_prompt,
            image_paths=[],
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            provider=provider,
        )
    )


def _parse_timecoded_items(second_round_text: str) -> list[dict[str, Any]]:
    patterns = [
        re.compile(r"(?P<start>\d{2}:\d{2}:\d{2})\s*[-~至]\s*(?P<end>\d{2}:\d{2}:\d{2})\s*(?P<text>.+)"),
        re.compile(r"\[(?P<start>\d{2}:\d{2}:\d{2})\s*[-~至]\s*(?P<end>\d{2}:\d{2}:\d{2})\]\s*(?P<text>.+)"),
    ]
    items: list[dict[str, Any]] = []
    for line in second_round_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        matched = None
        for pattern in patterns:
            matched = pattern.match(stripped)
            if matched:
                break
        if not matched:
            continue
        start = _parse_timestamp(matched.group("start"))
        end = _parse_timestamp(matched.group("end"))
        items.append(
            {
                "start": start,
                "end": end,
                "start_time": matched.group("start"),
                "end_time": matched.group("end"),
                "text": matched.group("text").strip(),
            }
        )
    return items
