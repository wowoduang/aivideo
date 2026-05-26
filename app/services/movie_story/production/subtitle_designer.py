# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

KEYWORD_RULES = ["真相", "危险", "反转", "秘密", "证据", "背叛", "误会", "身份", "计划", "最后", "真正"]


def _split_text_for_screen(text: str, *, max_chars_per_line: int = 12, max_lines: int = 2) -> List[str]:
    clean = re.sub(r"\s+", "", str(text or ""))
    if not clean:
        return []
    parts: List[str] = []
    while clean and len(parts) < max_lines:
        if len(clean) <= max_chars_per_line:
            parts.append(clean); break
        cut = max_chars_per_line
        for p in ["，", "。", "？", "！", ",", ".", "?", "!"]:
            pos = clean.rfind(p, 0, max_chars_per_line + 1)
            if 4 <= pos <= max_chars_per_line:
                cut = pos + 1
                break
        parts.append(clean[:cut])
        clean = clean[cut:]
    if clean and parts:
        parts[-1] = (parts[-1] + clean)[:max_chars_per_line + 3]
    return parts


def design_subtitle_cues(script_items: Iterable[Dict[str, Any]], *, style: str = "suspense_yellow_black",
                         max_chars_per_line: int = 12, max_lines: int = 2) -> List[Dict[str, Any]]:
    """把旁白脚本转成短视频字幕提示。

    只输出结构化字幕设计建议，不直接改 CompositionPlan，避免把未完成的视觉层硬接主链路。
    """
    cues: List[Dict[str, Any]] = []
    for idx, item in enumerate(script_items or [], start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("narration") or item.get("script") or "").strip()
        start = item.get("video_start") or item.get("start")
        end = item.get("video_end") or item.get("end")
        lines = _split_text_for_screen(text, max_chars_per_line=max_chars_per_line, max_lines=max_lines)
        if not lines:
            continue
        highlight_words = [w for w in KEYWORD_RULES if w in text]
        cues.append({
            "cue_id": f"subtitle_{idx:04d}",
            "segment_id": item.get("segment_id") or item.get("highlight_id") or item.get("id"),
            "video_start": start,
            "video_end": end,
            "text": text,
            "lines": lines,
            "highlight_words": highlight_words[:3],
            "style": style,
            "safe_area": "bottom_center_no_face_overlap_preferred",
            "max_chars_per_line": max_chars_per_line,
            "max_lines": max_lines,
        })
    return cues
