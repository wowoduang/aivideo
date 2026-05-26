# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from .style_profile import get_style_profile

TEMPLATE_REPLACEMENTS = [
    ("随后，", "但很快，"),
    ("随后", "接着"),
    ("与此同时，", "另一边，"),
    ("然而，", "可问题是，"),
    ("因此，", "所以，"),
    ("由此可见，", "到这里就很明显了，"),
    ("故事发生在", "一开始"),
    ("事情并不简单", "不对劲"),
]
FILLER_PATTERNS = [r"\b首先\b", r"\b其次\b", r"综上所述", r"总而言之"]


def _split_long_sentence(text: str, max_len: int) -> str:
    pieces: List[str] = []
    for raw in re.split(r"([。！？!?；;])", text):
        if not raw:
            continue
        if raw in "。！？!?；;" and pieces:
            pieces[-1] += raw
            continue
        chunk = raw.strip()
        while len(chunk) > max_len:
            cut_at = max(chunk.rfind("，", 0, max_len), chunk.rfind(",", 0, max_len))
            if cut_at < 8:
                cut_at = max_len
            pieces.append(chunk[:cut_at].strip("，, ") + "。")
            chunk = chunk[cut_at:].strip("，, ")
        if chunk:
            pieces.append(chunk)
    return "\n".join(p for p in pieces if p.strip())


def humanize_text(text: str, *, style_key: str | None = None, max_sentence_len: int | None = None) -> str:
    profile = get_style_profile(style_key)
    out = str(text or "").strip()
    for src, dst in TEMPLATE_REPLACEMENTS:
        out = out.replace(src, dst)
    for pat in FILLER_PATTERNS:
        out = re.sub(pat, "", out)
    for bad in profile.get("avoid_words") or []:
        out = out.replace(str(bad), "")
    out = re.sub(r"\s+", " ", out).strip()
    target_len = max_sentence_len or (18 if profile.get("sentence_length") == "short" else 26)
    out = _split_long_sentence(out, target_len)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    if profile.get("style_key") == "suspense" and out and not out.endswith(("？", "?", "。", "！", "!")):
        out += "。"
    return out


def humanize_script_items(script_items: Iterable[Dict[str, Any]], *, style_key: str | None = None,
                          plan_by_segment: Dict[str, Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    plan_by_segment = plan_by_segment or {}
    out: List[Dict[str, Any]] = []
    for item in script_items or []:
        if not isinstance(item, dict):
            continue
        seg_id = str(item.get("segment_id") or item.get("highlight_id") or item.get("id") or "")
        text = str(item.get("text") or item.get("narration") or item.get("script") or "")
        plan = plan_by_segment.get(seg_id) or {}
        humanized = humanize_text(text, style_key=plan.get("style_key") or style_key)
        next_hook = str(plan.get("hook_to_next") or "").strip()
        if next_hook and humanized and next_hook not in humanized and len(humanized) < 90:
            humanized = f"{humanized}\n{next_hook}"
        new_item = dict(item)
        new_item["original_text"] = text
        new_item["text"] = humanized
        new_item["humanized"] = humanized != text
        new_item["human_narration_plan"] = plan
        out.append(new_item)
    return out
