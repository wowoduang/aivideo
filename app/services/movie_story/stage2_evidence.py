# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

from .schemas import EvidenceSegment, to_dict
from .stage1_segmentation import text_between, normalize_subtitle_segments

PLOT_RULES = [
    ("信息揭露", ["真相", "秘密", "原来", "知道", "发现", "告诉", "证据", "身份", "曝光"]),
    ("冲突升级", ["吵", "打", "杀", "滚", "威胁", "报仇", "报警", "冲突"]),
    ("人物转折", ["决定", "不再", "终于", "改变", "答应", "拒绝", "离开", "回来"]),
    ("关系变化", ["相信", "怀疑", "背叛", "原谅", "误会", "合作", "分开", "结婚", "离婚"]),
    ("关键决定", ["必须", "不能", "要去", "留下", "救", "走", "选择", "签字"]),
    ("情感爆发", ["哭", "流泪", "崩溃", "对不起", "委屈", "恨", "爱", "跪下"]),
    ("阴谋推进", ["计划", "安排", "利用", "陷害", "坐收渔利", "密令", "布局"]),
]

EMOTION_RULES = {
    "愤怒": ["滚", "恨", "混蛋", "闭嘴", "杀", "报仇"],
    "紧张": ["危险", "怎么办", "快走", "来不及", "害怕"],
    "悲伤": ["哭", "流泪", "对不起", "死", "离开"],
    "甜蜜": ["喜欢", "爱", "拥抱", "结婚"],
}
INFORMATION_KEYS = ["真相", "秘密", "身份", "计划", "证据", "误会", "背叛", "陷害", "遗嘱", "合同", "录音"]
CHARACTER_KEYS = ["男主", "女主", "反派", "母亲", "父亲", "妈妈", "爸爸", "哥哥", "妹妹", "老板", "经理", "警察", "医生", "律师"]


def guess_plot(text: str) -> str:
    for name, keys in PLOT_RULES:
        if any(k in text for k in keys):
            return name
    if len(text.strip()) < 12:
        return "弱过渡"
    if any(k in text for k in ["因为", "所以", "原来", "没想到", "终于"]):
        return "发展"
    return "铺垫"


def _subtitle_for_candidate(candidate: Dict[str, Any], subtitle_segments: Optional[List[Dict[str, Any]]]) -> tuple[str, Optional[float], Optional[float]]:
    text = str(candidate.get("subtitle_text") or "").strip()
    if text:
        return text, candidate.get("subtitle_start") or candidate.get("evidence_start"), candidate.get("subtitle_end") or candidate.get("evidence_end")
    units = normalize_subtitle_segments(subtitle_segments or [])
    start = float(candidate.get("video_start", candidate.get("start", 0.0)) or 0.0)
    end = float(candidate.get("video_end", candidate.get("end", start)) or start)
    return text_between(units, start, end)


def _character_trace(text: str, visual: Dict[str, Any]) -> Dict[str, Any]:
    trace: Dict[str, Any] = {}
    mentioned = [k for k in CHARACTER_KEYS if k in text]
    if mentioned:
        trace["mentioned_characters"] = mentioned
        trace["focus_character"] = mentioned[0]
    for k in ["characters", "actions", "emotion", "location", "important_visual_detail", "key_action", "motivation_hint"]:
        if k in visual and visual[k]:
            trace[k] = visual[k]
    if any(k in text for k in ["决定", "必须", "选择", "离开", "留下"]):
        trace["goal_change_hint"] = True
    if any(k in text for k in ["怀疑", "背叛", "原谅", "相信", "误会"]):
        trace["relationship_change_hint"] = True
    return trace


def _split_merge_suggestion(text: str, duration: float, candidate: Dict[str, Any]) -> Dict[str, Any]:
    if duration >= 150 and len(text) > 200:
        return {"decision": "split", "reason": "候选较长且字幕信息密集，建议第三阶段或人工复核时拆分"}
    if duration < 8 and not text.strip():
        return {"decision": "merge_with_neighbor", "reason": "无字幕短动作段，建议与相邻片段合并检查"}
    if candidate.get("nonstory_tag"):
        return {"decision": "keep_with_drop_suggestion", "reason": "疑似非正文片段，第二阶段只标记不删除"}
    return {"decision": "keep", "reason": "stage2_no_delete"}


def _drop_suggestion(text: str, candidate: Dict[str, Any]) -> tuple[bool, str]:
    tag = candidate.get("nonstory_tag")
    if tag in {"intro", "outro", "ad", "preview"}:
        return True, str(tag)
    normalized = text.strip()
    if normalized and len(normalized) <= 6 and any(k in normalized for k in ["嗯", "啊", "好", "是", "对"]):
        return True, "重复寒暄或低信息密度"
    return False, ""


def enrich_candidates_with_evidence(candidates: Iterable[Any], subtitle_segments: Optional[List[Dict[str, Any]]] = None,
                                    *, visual_cards: Optional[Dict[str, Dict[str, Any]]] = None,
                                    text_model_config: Optional[Dict[str, Any]] = None,
                                    visual_model_config: Optional[Dict[str, Any]] = None) -> List[EvidenceSegment]:
    """第二阶段：补证据、打标签、给建议，但绝不静默删除候选。"""
    visual_cards = visual_cards or {}
    items = list(candidates or [])
    out: List[EvidenceSegment] = []
    seen_texts: Counter[str] = Counter()
    for item in items:
        d = to_dict(item)
        if not isinstance(d, dict):
            continue
        cid = str(d.get("candidate_id") or f"candidate_{len(out)+1:04d}")
        start = float(d.get("video_start", d.get("start", 0.0)) or 0.0)
        end = float(d.get("video_end", d.get("end", start)) or start)
        if end <= start:
            continue
        text, sub_s, sub_e = _subtitle_for_candidate(d, subtitle_segments)
        visual = dict(visual_cards.get(cid) or d.get("visual_evidence") or {})
        plot = guess_plot(text)
        emotions = [name for name, keys in EMOTION_RULES.items() if any(k in text for k in keys)]
        info_tags = [k for k in INFORMATION_KEYS if k in text]
        trace = _character_trace(text, visual)
        duration = end - start
        drop, reason = _drop_suggestion(text, d)
        key = " ".join(text.split())[:80]
        if key:
            seen_texts[key] += 1
            if seen_texts[key] >= 3:
                drop = True
                reason = reason or "重复片段文本"
        importance = "high" if plot in {"信息揭露", "冲突升级", "人物转折", "关键决定", "情感爆发", "阴谋推进"} or visual.get("important_visual_detail") else "medium"
        if plot == "弱过渡" and not visual:
            importance = "low"
        warnings: List[str] = []
        if not text:
            warnings.append("no_subtitle_text")
        if not visual:
            warnings.append("no_visual_evidence")
        semantic_start = sub_s if sub_s is not None else start
        semantic_end = sub_e if sub_e is not None else end
        out.append(EvidenceSegment(
            candidate_id=cid,
            candidate_type=str(d.get("candidate_type") or "unknown"),
            video_start=round(start, 3),
            video_end=round(end, 3),
            evidence_start=round(float(sub_s), 3) if sub_s is not None else round(start, 3),
            evidence_end=round(float(sub_e), 3) if sub_e is not None else round(end, 3),
            semantic_start=round(float(semantic_start), 3),
            semantic_end=round(float(semantic_end), 3),
            subtitle_text=text,
            visual_evidence=visual,
            character_trace=trace,
            plot_function=plot,
            importance_level=importance,
            emotion_tags=emotions,
            information_tags=info_tags,
            raw_voice_suggestion=plot in {"情感爆发", "冲突升级"} or bool(visual.get("raw_voice_value")),
            drop_suggestion=bool(drop),
            drop_reason=reason,
            split_merge_suggestion=_split_merge_suggestion(text, duration, d),
            evidence_warnings=warnings,
            source_candidate=d,
        ))
    return out
