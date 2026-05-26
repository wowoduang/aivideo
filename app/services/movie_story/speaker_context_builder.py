# -*- coding: utf-8 -*-
from __future__ import annotations

"""
speaker_context_builder.py

基于原始 SRT 时间轴生成影视剧说话人标注上下文。
本模块只生成 speaker_context，不修改字幕时间轴，不负责 ASR、TTS 或视频合成。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.speaker_context",
    "entry_points": ["build_speaker_context"],
    "called_by": ["movie_story/raw_srt_context_builder.py", "movie_story/raw_srt_two_round.py"],
    "decisions": [
        "2026-05: 外部 SRT 存在时，原始 SRT 时间轴作为 canonical timeline。",
        "2026-05: VAD/diarization/voiceprint 结果只作为说话人证据，不能替换字幕时间轴。",
        "2026-05: 低置信度说话人必须标记为存疑，不允许强行写成确定角色。",
    ],
    "pending": ["接入真实 pyannote diarization 输出。", "接入角色声纹库 embedding 相似度结果。"],
    "ai_constraints": [
        "禁止在本模块里调用 LLM 猜说话人。",
        "禁止把 speech_start/speech_end 作为下游主时间轴。",
        "禁止输出没有 confidence/source/basis 的角色名。",
    ],
}

import re
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger


CONFIRMED_THRESHOLD = 0.85
CANDIDATE_THRESHOLD = 0.70
_EXPLICIT_SPEAKER_PATTERN = re.compile(
    r"^\s*(?:[-–—]\s*)?(?:[【\[](?P<bracket>[^】\]]{1,24})[】\]]|"
    r"(?P<colon>[\u4e00-\u9fffA-Za-z0-9_·・]{1,24})(?:[（(][^）)]{1,12}[）)])?\s*[:：])\s*"
    r"(?P<line>.+?)\s*$"
)


def build_speaker_context(
    subtitle_segments: Sequence[Mapping[str, Any]],
    *,
    manual_speaker_map: Mapping[str, str] | None = None,
    voiceprint_matches: Sequence[Mapping[str, Any]] | None = None,
    time_axis_source: str = "original_srt",
) -> dict[str, Any]:
    """
    基于字幕主时间轴生成 speaker_context。

    意图：
        raw_srt 第一轮需要知道每段字幕可能是谁说的，但不能让音频切片时间轴
        替代用户上传的 SRT 时间轴。本函数把 voiceprint/diarization 结果对齐回
        subtitle_segments，每个输出 unit 仍使用原始字幕 start/end。

    注意（AI 不得修改以下行为）：
        - start/end 使用 subtitle_segments 的时间。
        - voiceprint_matches 只作为 speaker 证据。
        - 低置信度必须输出 status="存疑"。
    """
    match_list = list(voiceprint_matches or [])
    manual_map = dict(manual_speaker_map or {})
    speaker_units = [
        _build_speaker_unit(segment, index=index, manual_speaker_map=manual_map, voiceprint_matches=match_list)
        for index, segment in enumerate(subtitle_segments)
    ]
    context = {
        "speaker_context_version": "v1",
        "time_axis_source": time_axis_source,
        "speaker_units": speaker_units,
        "role_voiceprint_map": _build_role_map(speaker_units),
        "uncertain_units": [item for item in speaker_units if item.get("status") == "存疑"],
    }
    logger.info("说话人上下文生成完成: units={}, uncertain={}", len(speaker_units), len(context["uncertain_units"]))
    return context


def parse_explicit_speaker_label(text: str) -> dict[str, str] | None:
    """解析字幕中显式存在的“角色名：台词”或“【角色名】台词”格式。"""
    normalized = (text or "").strip()
    if not normalized:
        return None
    match = _EXPLICIT_SPEAKER_PATTERN.match(normalized)
    if match is None:
        return None
    speaker = (match.group("bracket") or match.group("colon") or "").strip()
    line = (match.group("line") or "").strip()
    if not _is_plausible_speaker_name(speaker) or not line:
        return None
    return {"speaker": speaker, "text": line}


def align_voiceprint_to_subtitle(
    segment: Mapping[str, Any],
    voiceprint_matches: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """把 voiceprint/diarization 结果按最大重叠比例对齐到当前字幕段。"""
    start = _to_seconds(segment.get("start"))
    end = _to_seconds(segment.get("end"))
    if end <= start:
        return None
    best_match: dict[str, Any] | None = None
    best_ratio = 0.0
    for candidate in voiceprint_matches:
        ratio = _overlap_ratio(start, end, _to_seconds(candidate.get("start")), _to_seconds(candidate.get("end")))
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = dict(candidate)
    if best_match is None or best_ratio <= 0:
        return None
    best_match["overlap_ratio"] = round(best_ratio, 4)
    return best_match


def _build_speaker_unit(
    segment: Mapping[str, Any],
    *,
    index: int,
    manual_speaker_map: Mapping[str, str],
    voiceprint_matches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """构建单条字幕对应的说话人标注。"""
    original_text = str(segment.get("text") or segment.get("content") or "")
    explicit = parse_explicit_speaker_label(original_text)
    if explicit is not None:
        return _unit_from_explicit_label(segment, index=index, explicit=explicit)
    aligned = align_voiceprint_to_subtitle(segment, voiceprint_matches)
    if aligned is not None:
        return _unit_from_voiceprint(segment, index=index, aligned=aligned, manual_speaker_map=manual_speaker_map)
    return _unknown_unit(segment, index=index, text=original_text)


def _unit_from_explicit_label(
    segment: Mapping[str, Any],
    *,
    index: int,
    explicit: Mapping[str, str],
) -> dict[str, Any]:
    """基于显式字幕标签生成高置信 unit。"""
    return {
        "index": index,
        "start": _format_time(segment.get("start")),
        "end": _format_time(segment.get("end")),
        "text": explicit["text"],
        "speaker": explicit["speaker"],
        "speaker_id": None,
        "confidence": 0.98,
        "source": "subtitle_explicit_label",
        "basis": "字幕文本显式包含角色名标签。",
        "status": "confirmed",
    }


def _unit_from_voiceprint(
    segment: Mapping[str, Any],
    *,
    index: int,
    aligned: Mapping[str, Any],
    manual_speaker_map: Mapping[str, str],
) -> dict[str, Any]:
    """基于声纹或 diarization 对齐结果生成 unit。"""
    speaker_id = str(aligned.get("speaker_id") or aligned.get("speaker") or "unknown")
    role_name = str(aligned.get("role_name") or manual_speaker_map.get(speaker_id) or "unknown")
    confidence = _safe_float(aligned.get("confidence"), default=0.0)
    return {
        "index": index,
        "start": _format_time(segment.get("start")),
        "end": _format_time(segment.get("end")),
        "text": str(segment.get("text") or segment.get("content") or ""),
        "speaker": role_name if role_name != "unknown" else "",
        "speaker_id": speaker_id,
        "confidence": round(confidence, 4),
        "overlap_ratio": aligned.get("overlap_ratio", 0.0),
        "source": str(aligned.get("source") or "voiceprint_or_diarization"),
        "basis": _build_voiceprint_basis(aligned, role_name),
        "status": _status_from_confidence(confidence, role_name),
    }


def _unknown_unit(segment: Mapping[str, Any], *, index: int, text: str) -> dict[str, Any]:
    """生成未知说话人 unit。"""
    return {
        "index": index,
        "start": _format_time(segment.get("start")),
        "end": _format_time(segment.get("end")),
        "text": text,
        "speaker": "",
        "speaker_id": None,
        "confidence": 0.0,
        "source": "none",
        "basis": "字幕未显式标注说话人，且没有可对齐的声纹/diarization 证据。",
        "status": "存疑",
    }


def _build_role_map(speaker_units: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """从 unit 汇总角色映射。"""
    role_map: dict[str, dict[str, Any]] = {}
    for unit in speaker_units:
        speaker_id = unit.get("speaker_id")
        speaker = unit.get("speaker")
        confidence = _safe_float(unit.get("confidence"), default=0.0)
        if not speaker_id or not speaker:
            continue
        key = str(speaker_id)
        previous = role_map.get(key)
        if previous is None or _safe_float(previous.get("confidence"), default=0.0) < confidence:
            role_map[key] = {
                "speaker_id": key,
                "role_name": str(speaker),
                "confidence": round(confidence, 4),
                "source": unit.get("source", ""),
                "basis": unit.get("basis", ""),
                "status": unit.get("status", "存疑"),
            }
    return list(role_map.values())


def _status_from_confidence(confidence: float, role_name: str) -> str:
    """根据置信度和角色名生成状态。"""
    if not role_name or role_name == "unknown":
        return "存疑"
    if confidence >= CONFIRMED_THRESHOLD:
        return "confirmed"
    if confidence >= CANDIDATE_THRESHOLD:
        return "candidate"
    return "存疑"


def _build_voiceprint_basis(aligned: Mapping[str, Any], role_name: str) -> str:
    """生成声纹匹配依据说明。"""
    if role_name == "unknown":
        return "声纹或 diarization 可对齐，但缺少角色名映射。"
    return "声纹或人工映射匹配到角色，confidence={}。".format(aligned.get("confidence", 0.0))


def _is_plausible_speaker_name(value: str) -> bool:
    """过滤明显不是角色名的标签。"""
    if not value or len(value) > 24:
        return False
    return value not in {"字幕", "旁白字幕", "音乐", "音效", "注", "说明"}


def _overlap_ratio(start: float, end: float, other_start: float, other_end: float) -> float:
    """计算两个时间段相对于字幕段的重叠比例。"""
    if end <= start or other_end <= other_start:
        return 0.0
    overlap = max(0.0, min(end, other_end) - max(start, other_start))
    return overlap / max(end - start, 0.001)


def _to_seconds(value: Any) -> float:
    """把秒数或 SRT 时间字符串转为秒。"""
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


def _format_time(value: Any) -> str:
    """把时间值格式化为 HH:MM:SS,mmm。"""
    seconds = max(_to_seconds(value), 0.0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return "{:02d}:{:02d}:{:02d},{:03d}".format(hours, minutes, secs, millis)


def _safe_float(value: Any, *, default: float) -> float:
    """安全转 float。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
