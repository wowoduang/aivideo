# -*- coding: utf-8 -*-
from __future__ import annotations

"""
context_prompt_formatters.py

把 speaker_context 和 scene_boundary_context 转成 raw_srt 第一轮提示词使用的压缩文本。
本模块只负责格式化，不负责生成声纹、不负责场景识别、不负责剧情解读。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.context_prompt_formatters",
    "entry_points": [
        "format_speaker_context_for_prompt",
        "format_scene_boundary_context_for_prompt",
        "build_context_prompt_sections",
    ],
    "called_by": [
        "movie_story/raw_srt_context_builder.py",
        "movie_story/two_round_narration.py",
    ],
    "decisions": [
        "2026-05: 第一轮提示词使用压缩文本，不直接塞完整 JSON。",
        "2026-05: 原始 SRT 时间轴是主时间轴，speaker_context 只输出 SRT 对齐后的起止时间。",
        "2026-05: scene_boundary_context 只输出事实字段，不输出剧情解读。",
    ],
    "pending": [
        "接入 raw_srt_context_builder.py。",
    ],
    "ai_constraints": [
        "禁止把低置信度或 candidate 说话人改成 confirmed。",
        "禁止输出 plot_function/deep_understanding/real_narrative_state 等解释字段。",
        "禁止输出 shot boundaries 原始列表。",
    ],
}

from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger


PROMPT_CERTAIN_THRESHOLD = 0.70
INTERPRETIVE_MARKERS = (
    "揭示",
    "说明",
    "体现",
    "象征",
    "适合",
    "主论点",
    "分论点",
    "阶层",
    "权力结构",
)
FORBIDDEN_KEYS = {
    "plot_function",
    "importance_level",
    "attraction_level",
    "deep_understanding",
    "real_narrative_state",
    "scene_function_hint",
    "support_type",
    "main_argument",
    "sub_argument",
    "historical_view",
    "recommended_usage",
    "narrative_strategy",
    "surface_dialogue_meaning",
}


def format_speaker_context_for_prompt(
    speaker_context: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | None,
    *,
    max_lines: int = 220,
) -> str:
    """
    输出第一轮提示词使用的说话人识别压缩文本。

    格式：
        起止时间 | 说话人 | 置信度 | 状态
    """
    if speaker_context is None:
        return "暂无可靠说话人识别结果。"
    if isinstance(speaker_context, str):
        return speaker_context.strip() or "暂无可靠说话人识别结果。"

    units = _extract_speaker_units(speaker_context)
    lines: list[str] = []
    for unit in units:
        line = _format_speaker_unit(unit)
        if line:
            lines.append(line)
        if len(lines) >= max_lines:
            lines.append("……（说话人识别结果过长，已截断）")
            break

    result = "\n".join(lines) if lines else "暂无可靠说话人识别结果。"
    logger.info("speaker_context 压缩完成: lines={}", len(lines))
    return result


def format_scene_boundary_context_for_prompt(
    scene_boundary_context: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | None,
    *,
    max_scenes: int = 45,
) -> str:
    """
    输出第一轮提示词使用的场景边界压缩文本。

    格式：
        scene_002 | 00:07:44~00:09:27 | 103秒
        在场人物：官兵(0.86) 母亲(0.78)
        画面事实：……
        画面锚点：00:08:12 官兵靠近屋内物品(0.76)
        字幕关键词：欠税 稻种 喂马
    """
    if scene_boundary_context is None:
        return "暂无可靠场景边界结果。"
    if isinstance(scene_boundary_context, str):
        return scene_boundary_context.strip() or "暂无可靠场景边界结果。"

    scenes = _extract_scene_boundaries(scene_boundary_context)
    blocks: list[str] = []
    for scene in scenes[:max_scenes]:
        block = _format_scene_block(scene)
        if block:
            blocks.append(block)
    if len(scenes) > max_scenes:
        blocks.append("……（场景边界结果过长，已截断）")

    result = "\n\n".join(blocks) if blocks else "暂无可靠场景边界结果。"
    logger.info("scene_boundary_context 压缩完成: scenes={}", len(blocks))
    return result


def build_context_prompt_sections(
    raw_srt_text: str,
    *,
    speaker_context: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | None = None,
    scene_boundary_context: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | None = None,
) -> str:
    """生成第一轮提示词的三段输入区。"""
    return "\n\n".join(
        [
            "【原始字幕】\n{}".format((raw_srt_text or "").strip()),
            "【说话人识别】\n{}".format(format_speaker_context_for_prompt(speaker_context)),
            "【场景边界】\n{}".format(format_scene_boundary_context_for_prompt(scene_boundary_context)),
        ]
    ).strip()


def _extract_speaker_units(value: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """提取 speaker units。"""
    if isinstance(value, Mapping):
        units = value.get("speaker_units") or value.get("subtitle_speaker_units") or []
        return [item for item in units if isinstance(item, Mapping)]
    return [item for item in value if isinstance(item, Mapping)]


def _format_speaker_unit(unit: Mapping[str, Any]) -> str:
    """格式化单条说话人识别结果。"""
    speaker = str(unit.get("speaker") or unit.get("role_name") or "").strip()
    if not speaker:
        return ""

    start = _format_time_compact(unit.get("start"))
    end = _format_time_compact(unit.get("end"))
    confidence = _safe_float(unit.get("confidence"), default=0.0)
    status = str(unit.get("status") or "存疑")

    if status == "candidate" and confidence < PROMPT_CERTAIN_THRESHOLD:
        status_text = "candidate（存疑）"
    elif status == "存疑" or confidence < PROMPT_CERTAIN_THRESHOLD:
        status_text = "存疑"
    else:
        status_text = status

    return "{}~{} | {} | {:.2f} | {}".format(start, end, speaker, confidence, status_text)


def _extract_scene_boundaries(value: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """提取 scene boundaries。"""
    if isinstance(value, Mapping):
        scenes = value.get("scene_boundaries") or value.get("scenes") or []
        return [item for item in scenes if isinstance(item, Mapping)]
    return [item for item in value if isinstance(item, Mapping)]


def _format_scene_block(scene: Mapping[str, Any]) -> str:
    """格式化单个场景边界块。"""
    clean_scene = _remove_forbidden_keys(scene)
    scene_id = str(clean_scene.get("scene_id") or "scene_unknown")
    start = _format_time_compact(clean_scene.get("start"))
    end = _format_time_compact(clean_scene.get("end"))
    duration = int(round(_safe_float(clean_scene.get("duration"), default=max(_to_seconds(clean_scene.get("end")) - _to_seconds(clean_scene.get("start")), 0.0))))

    return "\n".join(
        [
            "{} | {}~{} | {}秒".format(scene_id, start, end, duration),
            "在场人物：{}".format(_format_people(clean_scene.get("speaker_candidates") or clean_scene.get("people") or [])),
            "画面事实：{}".format(_format_facts(clean_scene.get("visible_facts") or clean_scene.get("facts") or [])),
            "画面锚点：{}".format(_format_anchors(clean_scene.get("visual_anchors") or clean_scene.get("anchors") or [])),
            "字幕关键词：{}".format(_format_keywords(clean_scene.get("subtitle_keywords") or [])),
        ]
    )


def _format_people(value: Any) -> str:
    """格式化在场人物。"""
    if not isinstance(value, list) or not value:
        return "无可靠人物候选"

    items: list[str] = []
    for person in value:
        if isinstance(person, str):
            items.append(person)
            continue
        if not isinstance(person, Mapping):
            continue
        speaker = str(person.get("speaker") or person.get("role_name") or person.get("name") or "").strip()
        if not speaker:
            continue
        confidence = _safe_float(person.get("confidence"), default=0.0)
        items.append("{}({:.2f})".format(speaker, confidence))
    return " ".join(items) if items else "无可靠人物候选"


def _format_facts(value: Any) -> str:
    """格式化画面事实。"""
    if isinstance(value, str):
        facts = [value]
    elif isinstance(value, list):
        facts = [str(item).strip() for item in value if str(item).strip()]
    else:
        facts = []
    clean = [item for item in facts if not _looks_interpretive(item)]
    return "；".join(clean) if clean else "无可靠画面事实"


def _format_anchors(value: Any) -> str:
    """格式化画面锚点。"""
    if not isinstance(value, list) or not value:
        return "无可靠画面锚点"

    items: list[str] = []
    for anchor in value:
        if not isinstance(anchor, Mapping):
            continue
        time_text = _format_time_compact(anchor.get("time"))
        fact = str(anchor.get("fact") or anchor.get("description") or "").strip()
        confidence = _safe_float(anchor.get("confidence"), default=0.0)
        if fact and not _looks_interpretive(fact):
            items.append("{} {}({:.2f})".format(time_text, fact, confidence))
    return "；".join(items) if items else "无可靠画面锚点"


def _format_keywords(value: Any) -> str:
    """格式化字幕关键词。"""
    if isinstance(value, str):
        return value.strip() or "无"
    if isinstance(value, list):
        return " ".join(str(item).strip() for item in value if str(item).strip()) or "无"
    return "无"


def _remove_forbidden_keys(value: Mapping[str, Any]) -> dict[str, Any]:
    """递归移除解释性字段。"""
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key in FORBIDDEN_KEYS:
            continue
        if isinstance(item, Mapping):
            clean[key] = _remove_forbidden_keys(item)
        elif isinstance(item, list):
            clean[key] = [_remove_forbidden_keys(child) if isinstance(child, Mapping) else child for child in item]
        else:
            clean[key] = item
    return clean


def _looks_interpretive(text: str) -> bool:
    """判断文本是否带有解读色彩。"""
    return any(marker in text for marker in INTERPRETIVE_MARKERS)


def _format_time_compact(value: Any) -> str:
    """格式化为 HH:MM:SS。"""
    seconds = max(_to_seconds(value), 0.0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, secs)


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


def _safe_float(value: Any, *, default: float) -> float:
    """安全转 float。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
