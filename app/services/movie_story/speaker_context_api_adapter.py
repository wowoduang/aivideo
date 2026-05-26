# -*- coding: utf-8 -*-
from __future__ import annotations

"""
speaker_context_api_adapter.py

为未来 FastAPI 路由提供稳定的说话人识别 API 适配层。

本模块不直接绑定具体路由，不读写数据库，不修改项目配置。
它只把前端请求体风格的数据转换为 speaker_context_workflow 的输入输出，
方便下一步接入真实 API route。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.speaker_context_api_adapter",
    "entry_points": [
        "build_preview_response",
        "build_bound_context_response",
        "build_context_response",
    ],
    "called_by": [
        "future FastAPI routes for speaker context",
    ],
    "decisions": [
        "2026-05: API 层请求数据先进入 adapter，再调用 workflow，避免路由里堆业务逻辑。",
        "2026-05: 前端先拿 speaker_preview，再提交 speaker_role_map，最后生成 speaker_context。",
        "2026-05: 字幕只作为主时间轴，Fun-ASR 结果只作为音频侧 speaker_id 证据。",
    ],
    "pending": [
        "接入真实 FastAPI router。",
        "接入项目配置保存 speaker_role_map。",
        "接入任务目录中的 Fun-ASR JSON 文件读取。",
    ],
    "ai_constraints": [
        "禁止在 API adapter 里从字幕文本猜角色名。",
        "禁止在 API adapter 里调用 LLM。",
        "禁止在 API adapter 里修改合成链。",
    ],
}

from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger

from app.services.movie_story.speaker_context_workflow import (
    build_bound_speaker_context_payload,
    build_speaker_context_payload,
    build_speaker_preview_payload,
)


def build_preview_response(request_payload: Mapping[str, Any]) -> dict[str, Any]:
    """
    构建“生成 SPEAKER 预览”响应。

    request_payload:
        {
            "aliyun_result_json": {...},
            "max_examples_per_speaker": 5
        }
    """
    aliyun_result_json = _require_mapping(request_payload, "aliyun_result_json")
    max_examples = _safe_int(request_payload.get("max_examples_per_speaker"), default=5)

    data = build_speaker_preview_payload(
        aliyun_result_json,
        max_examples_per_speaker=max_examples,
    )
    logger.info("speaker preview response 构建完成")
    return {"ok": True, "data": data}


def build_bound_context_response(request_payload: Mapping[str, Any]) -> dict[str, Any]:
    """
    构建“根据 SPEAKER 角色绑定生成 speaker_context”响应。

    request_payload:
        {
            "subtitle_segments": [...],
            "aliyun_result_json": {...},
            "speaker_role_map": {"SPEAKER_00": "朱重八"},
            "speaker_confidence_map": {"SPEAKER_00": 0.90}
        }
    """
    subtitle_segments = _require_sequence(request_payload, "subtitle_segments")
    aliyun_result_json = _require_mapping(request_payload, "aliyun_result_json")
    speaker_role_map = _optional_mapping(request_payload.get("speaker_role_map"))
    speaker_confidence_map = _optional_mapping(request_payload.get("speaker_confidence_map"))
    max_lines = _safe_int(request_payload.get("max_lines"), default=260)

    data = build_bound_speaker_context_payload(
        subtitle_segments,
        aliyun_result_json,
        speaker_role_map=speaker_role_map,
        speaker_confidence_map=speaker_confidence_map,
        max_lines=max_lines,
    )
    logger.info("bound speaker_context response 构建完成")
    return {"ok": True, "data": data}


def build_context_response(request_payload: Mapping[str, Any]) -> dict[str, Any]:
    """
    构建“一次性生成 speaker_preview + speaker_context”响应。

    适合调试或已保存 speaker_role_map 的项目。
    """
    subtitle_segments = _require_sequence(request_payload, "subtitle_segments")
    aliyun_result_json = _require_mapping(request_payload, "aliyun_result_json")
    speaker_role_map = _optional_mapping(request_payload.get("speaker_role_map"))
    speaker_confidence_map = _optional_mapping(request_payload.get("speaker_confidence_map"))
    max_examples = _safe_int(request_payload.get("max_examples_per_speaker"), default=5)
    max_lines = _safe_int(request_payload.get("max_lines"), default=260)

    data = build_speaker_context_payload(
        subtitle_segments,
        aliyun_result_json,
        speaker_role_map=speaker_role_map,
        speaker_confidence_map=speaker_confidence_map,
        max_examples_per_speaker=max_examples,
        max_lines=max_lines,
    )
    logger.info("speaker_context response 构建完成")
    return {"ok": True, "data": data}


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """读取必填 object 字段。"""
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError("缺少必填对象字段: {}".format(key))
    return value


def _require_sequence(payload: Mapping[str, Any], key: str) -> Sequence[Mapping[str, Any]]:
    """读取必填 list[object] 字段。"""
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError("缺少必填列表字段: {}".format(key))
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError("{}[{}] 必须是对象".format(key, index))
    return value


def _optional_mapping(value: Any) -> Mapping[str, Any]:
    """读取可选 object 字段。"""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("可选字段必须是对象")
    return value


def _safe_int(value: Any, *, default: int) -> int:
    """安全转 int。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
