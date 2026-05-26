# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..schemas import to_dict
from .style_profile import get_style_profile


def _text_of(item: Dict[str, Any]) -> str:
    return str(item.get("subtitle_text") or (item.get("source_segment") or {}).get("subtitle_text") or "").strip()


def _main_character(items: List[Dict[str, Any]]) -> str:
    for d in items:
        trace = d.get("character_trace") or {}
        name = trace.get("focus_character")
        if name:
            return str(name)
        mentioned = trace.get("mentioned_characters") or []
        if mentioned:
            return str(mentioned[0])
    return "这个人"


def generate_opening_hooks(highlights: Iterable[Any], *, global_summary: str = "", style_key: str | None = None,
                           max_hooks: int = 5) -> List[Dict[str, Any]]:
    style = get_style_profile(style_key)
    items = [to_dict(x) for x in highlights if isinstance(to_dict(x), dict)]
    if not items:
        return []
    first = items[0]
    strongest = max(items, key=lambda d: float((d.get("scores") or {}).get("highlight_score", 0.0) or 0.0))
    character = _main_character(items)
    text = _text_of(strongest) or _text_of(first) or global_summary
    crisis = "真相" if any(k in text for k in ["真相", "秘密", "证据", "身份"]) else "危险"
    hooks = [
        {
            "hook_type": "suspense",
            "text": f"{character}只是做了一个选择，却把自己推向了更大的{crisis}。",
            "matched_segment_id": strongest.get("highlight_id") or strongest.get("candidate_id"),
            "style_key": style["style_key"],
        },
        {
            "hook_type": "question",
            "text": f"如果你发现身边最信任的人突然变了，你会继续相信他吗？",
            "matched_segment_id": first.get("highlight_id") or first.get("candidate_id"),
            "style_key": style["style_key"],
        },
        {
            "hook_type": "reversal",
            "text": f"所有人都以为事情已经结束，但真正的反转才刚刚开始。",
            "matched_segment_id": strongest.get("highlight_id") or strongest.get("candidate_id"),
            "style_key": style["style_key"],
        },
        {
            "hook_type": "character_dilemma",
            "text": f"{character}现在只有两个选择：说出真相，或者被所有人误会到底。",
            "matched_segment_id": first.get("highlight_id") or first.get("candidate_id"),
            "style_key": style["style_key"],
        },
        {
            "hook_type": "fast_short_video",
            "text": f"注意看，接下来这个细节，会直接改变整件事的走向。",
            "matched_segment_id": strongest.get("highlight_id") or strongest.get("candidate_id"),
            "style_key": style["style_key"],
        },
    ]
    if style["style_key"] == "commentary_funny":
        hooks.insert(0, {
            "hook_type": "funny_reversal",
            "text": f"他以为自己稳了，结果下一秒就被现实狠狠上了一课。",
            "matched_segment_id": strongest.get("highlight_id") or strongest.get("candidate_id"),
            "style_key": style["style_key"],
        })
    return hooks[:max(1, int(max_hooks))]
