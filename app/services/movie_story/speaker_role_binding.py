# -*- coding: utf-8 -*-
from __future__ import annotations

"""
speaker_role_binding.py

为前端生成 SPEAKER_ID 预览数据，并校验用户保存的 SPEAKER_ID → 角色名映射。

本模块不做说话人识别，不猜角色名。
输入必须来自 Fun-ASR / diarization 等音频侧结果。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.speaker_role_binding",
    "entry_points": [
        "build_speaker_preview",
        "normalize_speaker_role_map",
        "build_speaker_context_config",
    ],
    "called_by": [
        "movie_story.aliyun_funasr_speaker_context",
        "future api routes for speaker role binding",
    ],
    "decisions": [
        "2026-05: 前端绑定角色名前，后端先按 SPEAKER_ID 聚合样例片段。",
        "2026-05: speaker_role_map 只接受 SPEAKER_ID -> 非空角色名。",
        "2026-05: 未绑定角色时保留 SPEAKER_ID，不强行生成角色名。",
    ],
    "pending": [
        "接入项目配置保存与读取。",
        "接入前端绑定表 API。",
    ],
    "ai_constraints": [
        "禁止从字幕文本推断角色名。",
        "禁止把 SPEAKER_ID 映射结果写死在代码里。",
        "禁止输出无来源角色名。",
    ],
}

from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger


def build_speaker_preview(
    speech_segments: Sequence[Mapping[str, Any]],
    *,
    max_examples_per_speaker: int = 5,
) -> dict[str, Any]:
    """
    把 Fun-ASR / diarization 输出按 SPEAKER_ID 聚合成前端预览数据。

    输入 segment 约定：
        {
            "start": 284.0,
            "end": 288.0,
            "speaker_id": "SPEAKER_00",
            "text": "台词文本",
            "confidence": 0.86
        }
    """
    grouped: dict[str, dict[str, Any]] = {}
    for segment in speech_segments:
        speaker_id = _normalize_speaker_id(segment.get("speaker_id"))
        if not speaker_id:
            continue

        item = grouped.setdefault(
            speaker_id,
            {
                "speaker_id": speaker_id,
                "total_duration": 0.0,
                "segment_count": 0,
                "examples": [],
            },
        )
        start = _to_seconds(segment.get("start"))
        end = _to_seconds(segment.get("end"))
        duration = max(end - start, 0.0)

        item["total_duration"] = round(float(item["total_duration"]) + duration, 3)
        item["segment_count"] = int(item["segment_count"]) + 1

        if len(item["examples"]) < max_examples_per_speaker:
            item["examples"].append(
                {
                    "start": _format_time_compact(start),
                    "end": _format_time_compact(end),
                    "text": str(segment.get("text") or "").strip(),
                    "confidence": round(_safe_float(segment.get("confidence"), default=0.0), 4),
                }
            )

    speakers = sorted(
        grouped.values(),
        key=lambda value: (-float(value["total_duration"]), str(value["speaker_id"])),
    )
    logger.info("说话人预览生成完成: speakers={}", len(speakers))
    return {
        "provider": "aliyun_funasr",
        "speaker_count": len(speakers),
        "speakers": speakers,
    }


def normalize_speaker_role_map(
    speaker_role_map: Mapping[str, Any],
    *,
    known_speaker_ids: Sequence[str] | None = None,
) -> dict[str, str]:
    """
    清洗前端提交的 SPEAKER_ID -> 角色名映射。

    - 只保留 SPEAKER_ID 开头的键或可转为数字编号的键。
    - 角色名必须非空。
    - 如果传入 known_speaker_ids，则只保留已识别到的 SPEAKER_ID。
    """
    known = set(known_speaker_ids or [])
    cleaned: dict[str, str] = {}

    for raw_key, raw_value in speaker_role_map.items():
        speaker_id = _normalize_speaker_id(raw_key)
        role_name = str(raw_value or "").strip()
        if not speaker_id or not role_name:
            continue
        if known and speaker_id not in known:
            continue
        cleaned[speaker_id] = role_name

    return cleaned


def build_speaker_context_config(
    *,
    enabled: bool,
    speaker_role_map: Mapping[str, Any] | None = None,
    provider: str = "aliyun_funasr",
) -> dict[str, Any]:
    """构建可保存到项目配置里的 speaker_context_config。"""
    return {
        "speaker_context_config": {
            "provider": provider,
            "enabled": bool(enabled),
            "speaker_role_map": normalize_speaker_role_map(speaker_role_map or {}),
        }
    }


def _normalize_speaker_id(value: Any) -> str:
    """统一 SPEAKER_ID 格式。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("SPEAKER_"):
        return text
    try:
        return "SPEAKER_{:02d}".format(int(text))
    except ValueError:
        return ""


def _to_seconds(value: Any) -> float:
    """把秒数或时间字符串转成秒。"""
    if isinstance(value, int | float):
        return float(value)
    text = str(value or "").strip().replace(",", ".")
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except ValueError:
        return 0.0


def _format_time_compact(value: Any) -> str:
    """格式化秒数为 HH:MM:SS。"""
    seconds = max(_to_seconds(value), 0.0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, secs)


def _safe_float(value: Any, *, default: float) -> float:
    """安全转 float。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
