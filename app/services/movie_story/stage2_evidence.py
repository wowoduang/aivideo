# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .schemas import EvidenceSegment, to_dict

PLOT_RULES = [
    ("信息揭露", ["真相", "秘密", "原来", "知道", "发现", "告诉", "证据", "身份"]),
    ("冲突升级", ["吵", "打", "杀", "滚", "威胁", "报仇"]),
    ("人物转折", ["决定", "不再", "终于", "改变", "答应", "拒绝", "离开"]),
    ("关系变化", ["相信", "怀疑", "背叛", "原谅", "误会", "合作", "分开"]),
    ("关键决定", ["必须", "不能", "要去", "留下", "救", "走", "选择"]),
    ("情感爆发", ["哭", "流泪", "崩溃", "对不起", "委屈", "恨", "爱"]),
    ("阴谋推进", ["计划", "安排", "利用", "陷害", "坐收渔利", "密令"]),
]

EMOTION_RULES = {"愤怒": ["滚", "恨", "混蛋", "闭嘴", "杀"], "紧张": ["危险", "怎么办", "快走"], "悲伤": ["哭", "流泪", "对不起", "死"]}


def guess_plot(text: str) -> str:
    for name, keys in PLOT_RULES:
        if any(k in text for k in keys):
            return name
    return "弱过渡" if len(text) < 20 else "发展"


def enrich_candidates_with_evidence(candidates: Iterable[Any], subtitle_segments: Optional[List[Dict[str, Any]]] = None,
                                    *, visual_cards: Optional[Dict[str, Dict[str, Any]]] = None,
                                    text_model_config: Optional[Dict[str, Any]] = None,
                                    visual_model_config: Optional[Dict[str, Any]] = None) -> List[EvidenceSegment]:
    visual_cards = visual_cards or {}
    out: List[EvidenceSegment] = []
    for item in list(candidates or []):
        d = to_dict(item)
        if not isinstance(d, dict):
            continue
        cid = str(d.get("candidate_id") or f"candidate_{len(out)+1:04d}")
        start = float(d.get("video_start", d.get("start", 0.0)) or 0.0)
        end = float(d.get("video_end", d.get("end", start)) or start)
        if end <= start:
            continue
        text = str(d.get("subtitle_text") or "")
        visual = visual_cards.get(cid, {})
        plot = guess_plot(text)
        emotions = [name for name, keys in EMOTION_RULES.items() if any(k in text for k in keys)]
        info_tags = [k for k in ["真相", "秘密", "身份", "计划", "证据", "误会", "背叛", "陷害"] if k in text]
        importance = "high" if plot in {"信息揭露", "冲突升级", "人物转折", "关键决定", "情感爆发", "阴谋推进"} or visual.get("important_visual_detail") else "medium"
        trace = {k: visual[k] for k in ["characters", "actions", "emotion", "location", "important_visual_detail", "key_action"] if k in visual}
        drop_suggestion = d.get("nonstory_tag") in {"intro", "outro", "ad", "preview"}
        out.append(EvidenceSegment(
            candidate_id=cid, candidate_type=str(d.get("candidate_type") or "unknown"), video_start=start, video_end=end,
            evidence_start=d.get("subtitle_start") or start, evidence_end=d.get("subtitle_end") or end,
            subtitle_text=text, visual_evidence=visual, character_trace=trace, plot_function=plot,
            importance_level=importance, emotion_tags=emotions, information_tags=info_tags,
            raw_voice_suggestion=plot in {"情感爆发", "冲突升级"}, drop_suggestion=bool(drop_suggestion),
            drop_reason=str(d.get("nonstory_tag") or "") if drop_suggestion else "",
            split_merge_suggestion={"decision": "keep", "reason": "stage2_no_delete"}, source_candidate=d))
    return out
