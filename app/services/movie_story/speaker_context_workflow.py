# -*- coding: utf-8 -*-
from __future__ import annotations

"""
speaker_context_workflow.py

把阿里云 Fun-ASR/Paraformer 结果、前端 SPEAKER_ID 预览、人工角色绑定、
最终 {speaker_context} 文本串成一个小工作流。

本模块不调用 LLM，不从字幕猜人名，不修改合成链。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.speaker_context_workflow",
    "entry_points": [
        "build_speaker_preview_payload",
        "build_bound_speaker_context_payload",
        "build_speaker_context_payload",
    ],
    "called_by": [
        "future api routes for aliyun funasr speaker workflow",
        "movie_story.raw_srt_context_builder",
    ],
    "decisions": [
        "2026-05: Fun-ASR 负责 SPEAKER_ID；角色名由前端绑定或后续声纹库绑定。",
        "2026-05: 预览阶段只展示 SPEAKER_ID、样例台词、总时长和片段数。",
        "2026-05: 绑定阶段才把 SPEAKER_ID 替换为角色名。",
    ],
    "pending": [
        "接入 API route。",
        "接入项目配置读写。",
        "接入前端绑定表。",
    ],
    "ai_constraints": [
        "禁止从字幕文本推断角色名。",
        "禁止把 candidate 或低置信度结果当 confirmed。",
        "禁止输出两套主时间轴。",
    ],
}

from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger

from app.services.movie_story.aliyun_funasr_speaker_context import (
    build_speaker_context_text_from_aliyun_result,
    build_speaker_context_text_from_aliyun_segments,
    normalize_aliyun_transcription_result,
)
from app.services.movie_story.speaker_role_binding import (
    build_speaker_preview,
    normalize_speaker_role_map,
)


def build_speaker_preview_payload(
    aliyun_result_json: Mapping[str, Any],
    *,
    max_examples_per_speaker: int = 5,
) -> dict[str, Any]:
    """
    从阿里云完整识别 JSON 生成前端 SPEAKER 绑定预览。

    输出用于前端展示：
        SPEAKER_00
        总时长
        出现次数
        样例台词
    """
    aliyun_segments = normalize_aliyun_transcription_result(aliyun_result_json)
    preview = build_speaker_preview(
        aliyun_segments,
        max_examples_per_speaker=max_examples_per_speaker,
    )
    logger.info(
        "speaker preview payload 构建完成: speakers={}",
        preview.get("speaker_count", 0),
    )
    return {
        "provider": "aliyun_funasr",
        "speaker_segments_count": len(aliyun_segments),
        "speaker_preview": preview,
    }


def build_bound_speaker_context_payload(
    subtitle_segments: Sequence[Mapping[str, Any]],
    aliyun_result_json: Mapping[str, Any],
    *,
    speaker_role_map: Mapping[str, Any] | None = None,
    speaker_confidence_map: Mapping[str, float] | None = None,
    max_lines: int = 260,
) -> dict[str, Any]:
    """
    使用前端提交的角色绑定结果生成最终 {speaker_context} 文本。

    subtitle_segments 只提供输出主时间轴。
    aliyun_result_json 只提供音频侧 SPEAKER_ID 证据。
    speaker_role_map 提供 SPEAKER_ID -> 角色名。
    """
    aliyun_segments = normalize_aliyun_transcription_result(aliyun_result_json)
    known_speaker_ids = _collect_known_speaker_ids(aliyun_segments)
    cleaned_role_map = normalize_speaker_role_map(
        speaker_role_map or {},
        known_speaker_ids=known_speaker_ids,
    )
    speaker_context = build_speaker_context_text_from_aliyun_segments(
        subtitle_segments,
        aliyun_segments,
        speaker_role_map=cleaned_role_map,
        speaker_confidence_map=speaker_confidence_map,
        max_lines=max_lines,
    )
    logger.info(
        "bound speaker_context payload 构建完成: mapped_speakers={}, chars={}",
        len(cleaned_role_map),
        len(speaker_context),
    )
    return {
        "provider": "aliyun_funasr",
        "speaker_role_map": cleaned_role_map,
        "speaker_context": speaker_context,
    }


def build_speaker_context_payload(
    subtitle_segments: Sequence[Mapping[str, Any]],
    aliyun_result_json: Mapping[str, Any],
    *,
    speaker_role_map: Mapping[str, Any] | None = None,
    speaker_confidence_map: Mapping[str, float] | None = None,
    max_examples_per_speaker: int = 5,
    max_lines: int = 260,
) -> dict[str, Any]:
    """
    一次性生成预览和最终 speaker_context。

    适合后端调试或已有 speaker_role_map 的场景。
    前端交互仍建议先调用预览，再保存绑定，再生成 speaker_context。
    """
    aliyun_segments = normalize_aliyun_transcription_result(aliyun_result_json)
    known_speaker_ids = _collect_known_speaker_ids(aliyun_segments)
    cleaned_role_map = normalize_speaker_role_map(
        speaker_role_map or {},
        known_speaker_ids=known_speaker_ids,
    )
    preview = build_speaker_preview(
        aliyun_segments,
        max_examples_per_speaker=max_examples_per_speaker,
    )
    speaker_context = build_speaker_context_text_from_aliyun_segments(
        subtitle_segments,
        aliyun_segments,
        speaker_role_map=cleaned_role_map,
        speaker_confidence_map=speaker_confidence_map,
        max_lines=max_lines,
    )
    return {
        "provider": "aliyun_funasr",
        "speaker_preview": preview,
        "speaker_role_map": cleaned_role_map,
        "speaker_context": speaker_context,
    }


def _collect_known_speaker_ids(aliyun_segments: Sequence[Mapping[str, Any]]) -> list[str]:
    """收集已识别到的 SPEAKER_ID。"""
    ids = sorted(
        {
            str(segment.get("speaker_id"))
            for segment in aliyun_segments
            if str(segment.get("speaker_id") or "").startswith("SPEAKER_")
        }
    )
    return ids
