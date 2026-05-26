# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..schemas import to_dict


def _plot(d: Dict[str, Any]) -> str:
    return str(d.get("plot_function") or (d.get("source_segment") or {}).get("plot_function") or "")


def generate_transitions(highlights: Iterable[Any]) -> List[Dict[str, Any]]:
    items = [to_dict(x) for x in highlights if isinstance(to_dict(x), dict)]
    transitions: List[Dict[str, Any]] = []
    for a, b in zip(items, items[1:]):
        pa, pb = _plot(a), _plot(b)
        if pb in {"信息揭露", "反转"}:
            ttype, text = "suspense", "但他还不知道，真正关键的线索，马上就要出现。"
        elif pb in {"冲突升级", "情感爆发", "高潮"}:
            ttype, text = "conflict", "而这一句话，直接把局面推向失控。"
        elif pa in {"铺垫", "发展"} and pb in {"关键决定", "人物转折"}:
            ttype, text = "causal", "前面的忍让，到这里终于变成了一个决定。"
        else:
            ttype, text = "continuity", "与此同时，另一条线也开始发生变化。"
        transitions.append({
            "from_segment": a.get("highlight_id") or a.get("candidate_id"),
            "to_segment": b.get("highlight_id") or b.get("candidate_id"),
            "transition_type": ttype,
            "text": text,
        })
    return transitions
