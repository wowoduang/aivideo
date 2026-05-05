# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .schemas import EvidenceSegment, SelectedHighlight, to_dict

CFG = {
    "strict": {"threshold": 0.72, "target_multiplier": 0.85, "keep_weak": False},
    "balanced": {"threshold": 0.55, "target_multiplier": 1.05, "keep_weak": False},
    "loose": {"threshold": 0.35, "target_multiplier": 1.50, "keep_weak": True},
    "very_loose": {"threshold": 0.15, "target_multiplier": 10.0, "keep_weak": True},
}


def normalize_selectivity(v: str) -> str:
    aliases = {"严格": "strict", "均衡": "balanced", "默认": "balanced", "宽松": "loose", "很宽松": "very_loose"}
    x = aliases.get((v or "balanced").strip().lower(), (v or "balanced").strip().lower())
    return x if x in CFG else "balanced"


def score_evidence_segment(seg: EvidenceSegment | Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    d = to_dict(seg)
    text = str(d.get("subtitle_text") or "")
    plot = str(d.get("plot_function") or "")
    importance = str(d.get("importance_level") or "medium").lower()
    visual = d.get("visual_evidence") or {}
    trace = d.get("character_trace") or {}
    emotions = d.get("emotion_tags") or []
    infos = d.get("information_tags") or []
    reasons = []
    story = 0.25
    if plot in {"冲突升级", "反转", "高潮", "结局收束"}:
        story = 0.95; reasons.append(f"强剧情功能:{plot}")
    elif plot in {"信息揭露", "阴谋推进", "关键决定", "人物转折", "关系变化"}:
        story = 0.82; reasons.append(f"剧情推进:{plot}")
    elif plot in {"发展", "铺垫"}:
        story = 0.48; reasons.append(f"主线铺垫:{plot}")
    character = 0.2 + (0.25 if trace else 0) + (0.25 if trace.get("key_action") or trace.get("important_visual_detail") else 0)
    if any(k in text for k in ["决定", "相信", "怀疑", "背叛", "原谅", "离开", "留下"]):
        character += 0.25; reasons.append("人物关系或目标变化")
    character = min(character, 1.0)
    information = 0.85 if infos else (0.70 if any(k in text for k in ["真相", "秘密", "计划", "身份", "证据"]) else 0.15)
    if infos: reasons.append("存在信息增量")
    emotion = 0.78 if emotions else (0.70 if any(k in text for k in ["哭", "流泪", "恨", "对不起", "怕", "崩溃"]) else 0.15)
    if emotions: reasons.append("存在情绪变化")
    visual_score = 0.80 if visual.get("important_visual_detail") or visual.get("key_action") or visual.get("actions") else (0.45 if visual else 0.10)
    audio = 0.35 if d.get("raw_voice_suggestion") else 0.05
    continuity = min(1.0, 0.45 + (0.25 if importance == "high" else 0.10 if importance == "medium" else 0))
    penalty = 0.35 if d.get("drop_suggestion") else 0.0
    highlight = max(0.0, min(1.0, 0.25*story + 0.20*character + 0.15*information + 0.15*emotion + 0.10*visual_score + 0.10*continuity + 0.05*audio - penalty))
    scores = {"story_score": round(story,3), "character_score": round(character,3), "information_score": round(information,3),
              "emotion_score": round(emotion,3), "visual_score": round(visual_score,3), "audio_score": round(audio,3),
              "continuity_score": round(continuity,3), "redundancy_penalty": round(penalty,3), "highlight_score": round(highlight,3)}
    return scores, reasons or ["基础剧情候选"]


def select_highlights(evidence_segments: Iterable[EvidenceSegment | Dict[str, Any]], *, target_minutes: int,
                      highlight_selectivity: str = "balanced", narrative_strategy: str = "mixed") -> List[SelectedHighlight]:
    mode = normalize_selectivity(highlight_selectivity)
    cfg = CFG[mode]
    target_seconds = max(60.0, float(target_minutes or 8) * 60.0 * cfg["target_multiplier"])
    scored = []
    for seg in evidence_segments or []:
        d = to_dict(seg)
        if not isinstance(d, dict): continue
        dur = float(d.get("video_end", 0.0)) - float(d.get("video_start", 0.0))
        if dur <= 0: continue
        scores, reasons = score_evidence_segment(d)
        scored.append((scores["highlight_score"], dur, d, scores, reasons))
    if mode == "very_loose":
        candidates = [x for x in scored if not x[2].get("drop_suggestion")]
        candidates.sort(key=lambda x: x[2].get("video_start", 0.0))
    else:
        candidates = [x for x in scored if x[0] >= cfg["threshold"] or (cfg["keep_weak"] and not x[2].get("drop_suggestion"))]
        candidates.sort(key=lambda x: (-x[0], x[2].get("video_start", 0.0)))
    chosen, total = [], 0.0
    for row in candidates:
        if mode != "very_loose" and total >= target_seconds: break
        chosen.append(row); total += row[1]
    chosen.sort(key=lambda x: x[2].get("video_start", 0.0))
    out = []
    for i, (_, _, d, scores, reasons) in enumerate(chosen, start=1):
        cid = str(d.get("candidate_id") or f"candidate_{i:04d}")
        out.append(SelectedHighlight(f"h_{i:04d}", cid, float(d.get("video_start", 0.0)), float(d.get("video_end", 0.0)),
                                     d.get("evidence_start"), d.get("evidence_end"), True, mode, scores, reasons,
                                     d.get("character_trace") or {}, bool(d.get("raw_voice_suggestion")), i, d))
    return out
