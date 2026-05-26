# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..schemas import to_dict
from .style_profile import get_style_profile


def _score(d: Dict[str, Any], key: str) -> float:
    scores = d.get("scores") or {}
    try:
        return float(scores.get(key, 0.0))
    except Exception:
        return 0.0


def _role_for_segment(d: Dict[str, Any], idx: int, total: int) -> str:
    plot = str(d.get("plot_function") or (d.get("source_segment") or {}).get("plot_function") or "")
    if idx == 0:
        return "hook_setup"
    if idx == total - 1:
        return "closing_reveal" if plot in {"信息揭露", "反转", "高潮"} else "closing_wrap"
    if plot in {"信息揭露", "反转"} or _score(d, "information_score") >= 0.75:
        return "reveal"
    if plot in {"冲突升级", "情感爆发", "高潮"} or _score(d, "emotion_score") >= 0.75:
        return "conflict_escalation"
    if plot in {"关键决定", "人物转折", "关系变化"} or _score(d, "character_score") >= 0.75:
        return "character_turn"
    if _score(d, "highlight_score") < 0.45:
        return "bridge_fast_pass"
    return "suspense_build"


ROLE_RULES: Dict[str, Dict[str, Any]] = {
    "hook_setup": {
        "tone": "紧张开场",
        "delivery": "先抛危机，不急着解释背景",
        "should_explain_subtext": False,
        "should_avoid_dialogue_rewrite": True,
    },
    "suspense_build": {
        "tone": "悬念递进",
        "delivery": "短句推进，结尾留一点疑问",
        "should_explain_subtext": True,
        "should_avoid_dialogue_rewrite": True,
    },
    "reveal": {
        "tone": "信息揭露",
        "delivery": "先给结论，再补原因，避免绕圈",
        "should_explain_subtext": True,
        "should_avoid_dialogue_rewrite": False,
    },
    "conflict_escalation": {
        "tone": "冲突升级",
        "delivery": "语速略快，动作用短句压出来",
        "should_explain_subtext": True,
        "should_avoid_dialogue_rewrite": True,
    },
    "character_turn": {
        "tone": "人物转折",
        "delivery": "讲人物为什么变，而不是复述他说了什么",
        "should_explain_subtext": True,
        "should_avoid_dialogue_rewrite": True,
    },
    "bridge_fast_pass": {
        "tone": "快速过渡",
        "delivery": "压缩讲，少停顿，服务下一段",
        "should_explain_subtext": False,
        "should_avoid_dialogue_rewrite": True,
    },
    "closing_reveal": {
        "tone": "收束反转",
        "delivery": "给出答案或风险，留下回味",
        "should_explain_subtext": True,
        "should_avoid_dialogue_rewrite": False,
    },
    "closing_wrap": {
        "tone": "结尾收束",
        "delivery": "总结人物代价或下一步悬念",
        "should_explain_subtext": True,
        "should_avoid_dialogue_rewrite": True,
    },
}


def _pace_for_role(role: str, style: Dict[str, Any]) -> Dict[str, Any]:
    if role in {"conflict_escalation", "bridge_fast_pass"}:
        pace = "fast"
        tts_speed = 1.08 if style.get("style_key") != "cinematic" else 1.0
        density = "high"
    elif role in {"reveal", "closing_reveal"}:
        pace = "hold"
        tts_speed = 0.94
        density = "medium"
    elif role == "hook_setup":
        pace = "fast_then_pause"
        tts_speed = 1.02
        density = "high"
    else:
        pace = "medium"
        tts_speed = 1.0
        density = "medium"
    return {"pace": pace, "tts_speed": round(tts_speed, 2), "narration_density": density}


def _hook_to_next(role: str, next_item: Dict[str, Any] | None) -> str:
    if not next_item:
        return ""
    next_plot = str(next_item.get("plot_function") or (next_item.get("source_segment") or {}).get("plot_function") or "")
    if next_plot in {"信息揭露", "反转"}:
        return "但真正的答案，还在后面。"
    if next_plot in {"冲突升级", "情感爆发"}:
        return "而这一下，才真正把局面推向失控。"
    return "可事情远没有这么简单。"


def direct_segments(highlights: Iterable[Any], *, style_key: str | None = None) -> List[Dict[str, Any]]:
    """为高光片段生成解说意图。

    这里不写最终文案，只决定“这一段怎么讲”。输出可直接用于脚本生成 prompt、人工审校或后续 TTS/CompositionPlan 扩展。
    """
    style = get_style_profile(style_key)
    items = [to_dict(x) for x in highlights if isinstance(to_dict(x), dict)]
    directed: List[Dict[str, Any]] = []
    for idx, d in enumerate(items):
        role = _role_for_segment(d, idx, len(items))
        rule = ROLE_RULES[role]
        next_item = items[idx + 1] if idx + 1 < len(items) else None
        directed.append({
            "segment_id": d.get("highlight_id") or d.get("candidate_id") or f"segment_{idx+1:03d}",
            "source_candidate_id": d.get("source_candidate_id") or d.get("candidate_id"),
            "video_start": d.get("video_start"),
            "video_end": d.get("video_end"),
            "narration_role": role,
            "tone": rule["tone"],
            "delivery": f"{style['delivery']}；{rule['delivery']}",
            "style_key": style["style_key"],
            "should_explain_subtext": bool(rule["should_explain_subtext"]),
            "should_avoid_dialogue_rewrite": bool(rule["should_avoid_dialogue_rewrite"]),
            "hook_to_next": _hook_to_next(role, next_item),
            "pacing": _pace_for_role(role, style),
            "source_plot_function": d.get("plot_function") or (d.get("source_segment") or {}).get("plot_function"),
            "source_scores": d.get("scores") or {},
            "character_trace": d.get("character_trace") or {},
        })
    return directed
