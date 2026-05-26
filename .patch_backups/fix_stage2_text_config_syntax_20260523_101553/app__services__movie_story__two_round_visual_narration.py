# -*- coding: utf-8 -*-
from __future__ import annotations

"""
two_round_visual_narration.py

two_round_visual 主链路：后端第一轮前用确定性视频时间轴能力准备视觉证据；
第一轮多模态模型理解全片；第二轮文本模型基于第一轮结构分析写文案和片段时间码。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "entry_points": ["generate_two_round_visual_narration_items"],
    "called_by": ["movie_story/two_round_feature_modes.py"],
    "decisions": [
        "two_round_visual 表示第一轮多模态增强，不表示 text-only 后置抽帧。",
        "visual_focus_segments 只是第一轮前详细抽帧区域，不是最终片段。",
        "2026-05: stage2 接入 shot/scene segmentation 和预算化抽帧。",
    ],
    "pending": [
        "继续调优 visual_focus_segments 选择策略与抽帧预算。",
        "后续补充 speaker_context / 角色名绑定以增强谁在说话判断。",
    ],
    "ai_constraints": [
        "禁止 fallback 到 _generate_raw_srt_narration_items。",
        "禁止调用 legacy/native 主流程。",
        "缺视频、视觉模型、抽帧结果或可解析文案时必须 raise。",
    ],
}

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Mapping

from loguru import logger

from app.services.generate_narration_script_clean import (
    _call_chat_completion,
    _raw_srt_build_items,
    _raw_srt_extract_rows,
)
from app.services.movie_story.scene_segmenter import build_scene_segments
from app.services.movie_story.shot_boundary_detector import detect_shot_boundaries
from app.services.movie_story.two_round_narration import (
    build_analysis_prompt,
    build_writer_prompt,
    extract_formal_script,
)
from app.services.movie_story.two_round_visual_input_packager import (
    build_two_round_visual_input_package,
)
from app.services.movie_story.visual_focus_segments import build_visual_focus_segments
from app.services.movie_story.visual_timeline_sampler import (
    sample_focus_segment_frames,
    sample_global_scene_frames,
)

__all__ = [
    "call_multimodal_first_round_strict",
    "generate_two_round_visual_narration_items",
]


MULTIMODAL_FIRST_ROUND_EXTRA_RULES = """\\
【two_round_visual 额外规则】
1. 视觉材料只作为事实证据，不是解说文案，不要直接复述画面事实。
2. visual_focus_segments 不是 AI 推荐高光，也不是最终剪辑片段，只是详细抽帧区域。
3. 你的第一轮输出仍按原第一轮结构分析提示词执行，不要输出正式文案正文。
4. 请重点利用图片和字幕判断谁在说话、谁是说话对象、谁在动作、场景中有谁。
5. 如果字幕与画面存在不确定关系，请在结构分析中标注“存疑”，不要强行编造。
"""


def generate_two_round_visual_narration_items(
    *,
    raw_srt_text: str,
    request: Mapping[str, Any],
    output_dir: str | Path,
    text_api_key: str,
    text_base_url: str,
    text_model: str,
    style: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate narration items through first-round multimodal understanding."""
    video_path = _required_video_path(request)
    vision_api_key, vision_base_url, vision_model = _resolve_vision_llm_settings(request)
    subtitles = _parse_srt_like_text(raw_srt_text=raw_srt_text)
    shot_boundaries = detect_shot_boundaries(video_path=video_path)
    scene_segments = build_scene_segments(
        shot_boundaries=shot_boundaries,
        subtitles=subtitles,
    )
    visual_focus_segments = build_visual_focus_segments(
        scene_segments=scene_segments,
        subtitles=subtitles,
        manual_segments=list(request.get("visual_focus_segments") or []),
        max_segments=int(request.get("two_round_visual_max_focus_segments", 6)),
    )
    frame_dir = Path(output_dir) / "two_round_visual_frames"
    low_density_keyframes = sample_keyframes_for_scene_context(
        video_path,
        scene_segments,
        frame_dir / "scene_context",
        max_frames=int(request.get("two_round_visual_max_global_frames", 12)),
    )
    focus_keyframes = sample_keyframes_for_visual_focus_segments(
        video_path,
        visual_focus_segments,
        frame_dir / "visual_focus",
        frames_per_segment=int(request.get("two_round_visual_focus_frames_per_segment", 2)),
    )
    package = build_two_round_visual_input_package(
        raw_srt_text=raw_srt_text,
        scene_segments=scene_segments,
        focus_segments=visual_focus_segments,
        global_frames=_normalize_frame_records(low_density_keyframes),
        focus_frames=_normalize_frame_records(focus_keyframes),
    )
    analysis_prompt = _build_visual_analysis_prompt(package["prompt_context"])
    analysis_text = call_multimodal_first_round_strict(
        image_paths=list(package["image_paths"]),
        prompt=analysis_prompt,
        api_key=vision_api_key,
        base_url=vision_base_url,
        model=vision_model,
    )
    writer_prompt = build_writer_prompt(analysis_text)
    second_api_key, second_base_url, second_model = _resolve_second_round_settings(
        request=request,
        text_api_key=text_api_key,
        text_base_url=text_base_url,
        text_model=text_model,
        vision_api_key=vision_api_key,
        vision_base_url=vision_base_url,
        vision_model=vision_model,
    )
    writer_text = _call_chat_completion(
        writer_prompt,
        api_key=second_api_key,
        base_url=second_base_url,
        model=second_model,
        timeout=180,
    )
    final_script = extract_formal_script(writer_text)
    rows = _raw_srt_extract_rows(final_script)
    if not rows:
        raise ValueError("two_round_visual second round returned no parseable timecoded narration rows")
    items = _raw_srt_build_items(rows, [], style=style)
    if not items:
        raise ValueError("two_round_visual parsed rows but built no executable script items")
    metadata = _write_visual_debug_outputs(
        Path(output_dir),
        scene_segments=scene_segments,
        shot_boundaries=shot_boundaries,
        visual_focus_segments=visual_focus_segments,
        low_density_keyframes=low_density_keyframes,
        focus_keyframes=focus_keyframes,
        package=package,
        analysis_prompt=analysis_prompt,
        analysis_text=analysis_text,
        writer_prompt=writer_prompt,
        writer_text=writer_text,
        second_round_model=second_model,
    )
    logger.info("two_round_visual narration generated: items={}, images={}", len(items), len(package["image_paths"]))
    return items, metadata


def sample_keyframes_for_scene_context(
    video_path: str,
    scene_segments: list[dict[str, Any]],
    frame_dir: str | Path,
    *,
    max_frames: int = 12,
) -> list[dict[str, Any]]:
    """【two_round_visual 阶段 04】全片低密度抽帧。"""
    return sample_global_scene_frames(
        video_path=video_path,
        scene_segments=scene_segments,
        output_dir=frame_dir,
        max_frames=max_frames,
    )


def sample_keyframes_for_visual_focus_segments(
    video_path: str,
    visual_focus_segments: list[dict[str, Any]],
    frame_dir: str | Path,
    *,
    frames_per_segment: int = 2,
) -> list[dict[str, Any]]:
    """【two_round_visual 阶段 05】视觉重点片段详细抽帧。"""
    return sample_focus_segment_frames(
        video_path=video_path,
        focus_segments=visual_focus_segments,
        output_dir=frame_dir,
        frames_per_segment=frames_per_segment,
    )


def call_multimodal_first_round_strict(
    *,
    image_paths: list[str],
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    """Call the vision model for first-round analysis with strict failure handling."""
    if not image_paths:
        raise ValueError("two_round_visual requires at least one keyframe image")
    for path_text in image_paths:
        if not Path(path_text).exists():
            raise FileNotFoundError(path_text)
    from app.services.llm.litellm_provider import LiteLLMVisionProvider

    provider = LiteLLMVisionProvider(api_key=api_key, model_name=model, base_url=base_url or None)
    results = asyncio.run(provider.analyze_images(image_paths, prompt, batch_size=len(image_paths), temperature=0.25))
    if not results:
        raise RuntimeError("vision model returned no first-round analysis result")
    joined = "\n\n".join(str(result or "").strip() for result in results if str(result or "").strip())
    if not joined or "批次处理失败" in joined:
        raise RuntimeError(f"vision model first-round analysis failed: {joined[:200]}")
    return joined


def _resolve_vision_llm_settings(request: Mapping[str, Any]) -> tuple[str, str, str]:
    """Resolve strict vision LLM settings from request/config/env."""
    api_key = _first_value(request, ("vision_api_key", "vision_litellm_api_key", "movie_story_vision_api_key"))
    base_url = _first_value(request, ("vision_base_url", "vision_litellm_base_url", "movie_story_vision_base_url"))
    model = _first_value(request, ("vision_model", "vision_litellm_model_name", "movie_story_vision_model"))
    if not api_key or not model:
        from app.services.llm_config import get_vision_llm_config

        cfg = get_vision_llm_config()
        api_key = api_key or str(cfg.get("api_key") or "").strip()
        base_url = base_url or str(cfg.get("base_url") or "").strip()
        model = model or str(cfg.get("model") or "").strip()
    if not api_key:
        raise ValueError("vision_api_key is required for two_round_visual")
    if not model:
        raise ValueError("vision_model is required for two_round_visual")
    return api_key, base_url, model


def _resolve_second_round_settings(
    *,
    request: Mapping[str, Any],
    text_api_key: str,
    text_base_url: str,
    text_model: str,
    vision_api_key: str,
    vision_base_url: str,
    vision_model: str,
) -> tuple[str, str, str]:
    ""
    Resolve second-round text LLM settings using existing project config keys.

    Existing keys:
    - text_litellm_api_key
    - text_litellm_base_url
    - text_litellm_model_name
    - text_llm_provider

    Design:
    two_round_visual first round uses vision_litellm_*.
    two_round_visual second round uses text_litellm_* when configured.
    If text_litellm_* was not propagated into request, use text_api_key/text_base_url/text_model
    passed by the existing caller. This does not introduce new config names.
    ""
    api_key = _first_value(request, ("text_litellm_api_key", "text_api_key"))
    base_url = _first_value(request, ("text_litellm_base_url", "text_base_url"))
    model = _first_value(request, ("text_litellm_model_name", "text_model"))

    api_key = api_key or text_api_key
    base_url = base_url or text_base_url
    model = model or text_model

    if not api_key:
        raise ValueError("two_round_visual second round requires text_litellm_api_key")
    if not model:
        raise ValueError("two_round_visual second round requires text_litellm_model_name")
    return api_key, base_url, model


def _required_video_path(request: Mapping[str, Any]) -> str:
    """Read and validate the required video path."""
    video_path = str(request.get("video_path") or "").strip()
    if not video_path:
        raise ValueError("video_path is required for two_round_visual")
    if not Path(video_path).exists():
        raise FileNotFoundError(video_path)
    return video_path


def _first_value(request: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    """Return first non-empty request value."""
    for key in keys:
        value = str(request.get(key) or "").strip()
        if value:
            return value
    return ""


def _build_visual_analysis_prompt(visual_context: str) -> str:
    """Build first-round multimodal prompt by extending existing analysis prompt."""
    return "\n\n".join(
        [
            build_analysis_prompt(visual_context),
            MULTIMODAL_FIRST_ROUND_EXTRA_RULES.strip(),
        ]
    ).strip()


def _parse_srt_like_text(*, raw_srt_text: str) -> list[dict[str, Any]]:
    """Parse SRT-like text into subtitle segments."""
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
    lines = [line.strip() for line in raw_srt_text.splitlines() if line.strip()]
    for index, line in enumerate(lines, start=1):
        start = float(index - 1) * 4.0
        segments.append({"subtitle_id": f"sub_{index:04d}", "start": start, "end": start + 4.0, "text": line})
    return segments


def _parse_timestamp(value: str) -> float:
    """Convert SRT timestamp into seconds."""
    clean = value.replace(",", ".")
    hour, minute, second = clean.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(second)


def _normalize_frame_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize old and new frame metadata keys for the input packager."""
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        path_text = str(record.get("path") or record.get("frame_path") or "").strip()
        if not path_text:
            continue
        normalized.append(
            {
                **record,
                "frame_id": str(record.get("frame_id") or f"frame_{index:03d}"),
                "path": path_text,
                "timestamp": float(record.get("timestamp", 0.0)),
            }
        )
    return normalized


def _write_visual_debug_outputs(
    output_dir: Path,
    *,
    scene_segments: list[dict[str, Any]],
    shot_boundaries: list[dict[str, Any]],
    visual_focus_segments: list[dict[str, Any]],
    low_density_keyframes: list[dict[str, Any]],
    focus_keyframes: list[dict[str, Any]],
    package: dict[str, Any],
    analysis_prompt: str,
    analysis_text: str,
    writer_prompt: str,
    writer_text: str,
    second_round_model: str,
) -> dict[str, Any]:
    """Write trace files that explain the visual first-round input."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "shot_boundaries_path": output_dir / "two_round_visual_shot_boundaries.json",
        "scene_segments_path": output_dir / "two_round_visual_scene_segments.json",
        "visual_focus_segments_path": output_dir / "two_round_visual_focus_segments.json",
        "scene_keyframes_path": output_dir / "two_round_visual_scene_keyframes.json",
        "focus_keyframes_path": output_dir / "two_round_visual_focus_keyframes.json",
        "visual_context_path": output_dir / "two_round_visual_first_round_context.txt",
        "analysis_prompt_path": output_dir / "two_round_visual_first_round_prompt.txt",
        "analysis_response_path": output_dir / "two_round_visual_first_round_response.txt",
        "writer_prompt_path": output_dir / "two_round_visual_second_round_prompt.txt",
        "writer_response_path": output_dir / "two_round_visual_second_round_response.txt",
    }
    _write_json(paths["shot_boundaries_path"], shot_boundaries)
    _write_json(paths["scene_segments_path"], scene_segments)
    _write_json(paths["visual_focus_segments_path"], visual_focus_segments)
    _write_json(paths["scene_keyframes_path"], low_density_keyframes)
    _write_json(paths["focus_keyframes_path"], focus_keyframes)
    paths["visual_context_path"].write_text(str(package["prompt_context"]), encoding="utf-8", newline="\n")
    paths["analysis_prompt_path"].write_text(analysis_prompt, encoding="utf-8", newline="\n")
    paths["analysis_response_path"].write_text(analysis_text, encoding="utf-8", newline="\n")
    paths["writer_prompt_path"].write_text(writer_prompt, encoding="utf-8", newline="\n")
    paths["writer_response_path"].write_text(writer_text, encoding="utf-8", newline="\n")
    return {**{key: str(value) for key, value in paths.items()}, "second_round_model": second_round_model}


def _write_json(path: Path, data: Any) -> None:
    """Write JSON with LF newlines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
