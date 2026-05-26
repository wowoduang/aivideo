# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .schemas import EvidenceSegment, SelectedHighlight, item_duration, to_dict

# Stage 3 is the only stage allowed to select highlights. The goal is not just
# to pick the highest scoring fragments; it must also satisfy the requested
# story coverage when the candidate pool is sufficient.
CFG = {
    "strict": {
        "threshold": 0.72,
        "hard_min_ratio": 0.30,
        "preferred_min_ratio": 0.50,
        "preferred_max_ratio": 0.90,
        "keep_weak": False,
    },
    "balanced": {
        "threshold": 0.55,
        "hard_min_ratio": 0.45,
        "preferred_min_ratio": 0.75,
        "preferred_max_ratio": 1.12,
        "keep_weak": False,
    },
    "loose": {
        "threshold": 0.35,
        "hard_min_ratio": 0.60,
        "preferred_min_ratio": 0.85,
        "preferred_max_ratio": 1.20,
        "keep_weak": True,
    },
    "very_loose": {
        "threshold": 0.15,
        "hard_min_ratio": 0.75,
        "preferred_min_ratio": 0.95,
        "preferred_max_ratio": 1.35,
        "keep_weak": True,
    },
}

HARD_DROP_WORDS = (
    "片头", "片尾", "演职员", "字幕表", "credit", "credits", "广告", "预告",
    "黑场", "空白", "无效", "nonstory", "non_story", "opening", "ending",
)


def normalize_selectivity(v: str) -> str:
    aliases = {"严格": "strict", "均衡": "balanced", "默认": "balanced", "宽松": "loose", "很宽松": "very_loose"}
    x = aliases.get((v or "balanced").strip().lower(), (v or "balanced").strip().lower())
    return x if x in CFG else "balanced"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _start(d: Dict[str, Any]) -> float:
    return _safe_float(d.get("video_start", d.get("start", 0.0)))


def _end(d: Dict[str, Any]) -> float:
    return _safe_float(d.get("video_end", d.get("end", _start(d))))


def _candidate_id(d: Dict[str, Any], idx: int = 0) -> str:
    return str(d.get("candidate_id") or d.get("segment_id") or d.get("id") or f"candidate_{idx:04d}")


def _drop_reason_text(d: Dict[str, Any]) -> str:
    parts = [str(d.get("drop_reason") or ""), str(d.get("nonstory_tag") or ""), str(d.get("subtitle_text") or "")[:80]]
    return " ".join(parts).lower()


def _is_hard_drop(d: Dict[str, Any]) -> bool:
    if not d.get("drop_suggestion"):
        return False
    text = _drop_reason_text(d)
    return any(word.lower() in text for word in HARD_DROP_WORDS)


def _overlaps_any(row: Tuple[float, float, Dict[str, Any], Dict[str, float], List[str]], chosen: List[Tuple[float, float, Dict[str, Any], Dict[str, float], List[str]]]) -> bool:
    s1, e1 = _start(row[2]), _end(row[2])
    for other in chosen:
        s2, e2 = _start(other[2]), _end(other[2])
        overlap = max(0.0, min(e1, e2) - max(s1, s2))
        if overlap > 0.2 * max(1.0, min(e1 - s1, e2 - s2)):
            return True
    return False


def score_evidence_segment(seg: EvidenceSegment | Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    d = to_dict(seg)
    text = str(d.get("subtitle_text") or "")
    plot = str(d.get("plot_function") or "")
    importance = str(d.get("importance_level") or "medium").lower()
    visual = d.get("visual_evidence") or {}
    trace = d.get("character_trace") or {}
    emotions = d.get("emotion_tags") or []
    infos = d.get("information_tags") or []
    reasons: List[str] = []

    story = 0.25
    if plot in {"冲突升级", "反转", "高潮", "结局收束"}:
        story = 0.95; reasons.append(f"强剧情功能:{plot}")
    elif plot in {"信息揭露", "阴谋推进", "关键决定", "人物转折", "关系变化"}:
        story = 0.82; reasons.append(f"剧情推进:{plot}")
    elif plot in {"发展", "铺垫"}:
        story = 0.48; reasons.append(f"主线铺垫:{plot}")
    elif any(k in text for k in ["真相", "秘密", "计划", "证据", "怀疑", "决定", "危险", "反派", "背叛", "救人", "身份"]):
        story = 0.62; reasons.append("字幕含剧情推进关键词")

    character = 0.20
    if trace:
        character += 0.25; reasons.append("有人物线索")
    if trace.get("goal_change_hint") or trace.get("relationship_change_hint") or trace.get("key_action") or trace.get("important_visual_detail"):
        character += 0.25; reasons.append("人物目标/关系/动作发生变化")
    if any(k in text for k in ["男主", "女主", "反派", "老板", "父亲", "母亲", "哥哥", "姐姐", "他", "她"]):
        character += 0.12
    if any(k in text for k in ["决定", "相信", "怀疑", "背叛", "原谅", "离开", "留下"]):
        character += 0.15
    character = min(character, 1.0)

    information = 0.85 if infos else (0.70 if any(k in text for k in ["真相", "秘密", "计划", "身份", "证据", "发现", "曝光"]) else 0.22)
    if infos:
        reasons.append("存在信息增量")
    emotion = 0.78 if emotions else (0.70 if any(k in text for k in ["哭", "流泪", "恨", "对不起", "怕", "崩溃", "危险", "紧张", "沉默"]) else 0.22)
    if emotions:
        reasons.append("存在情绪变化")
    visual_score = 0.80 if visual.get("important_visual_detail") or visual.get("key_action") or visual.get("actions") else (0.45 if visual else 0.12)
    audio = 0.35 if d.get("raw_voice_suggestion") else 0.08
    continuity = min(1.0, 0.45 + (0.25 if importance == "high" else 0.10 if importance == "medium" else 0.0))
    penalty = 0.60 if _is_hard_drop(d) else (0.25 if d.get("drop_suggestion") else 0.0)
    highlight = max(0.0, min(1.0, 0.25*story + 0.20*character + 0.15*information + 0.15*emotion + 0.10*visual_score + 0.10*continuity + 0.05*audio - penalty))
    scores = {
        "story_score": round(story, 3),
        "character_score": round(character, 3),
        "information_score": round(information, 3),
        "emotion_score": round(emotion, 3),
        "visual_score": round(visual_score, 3),
        "audio_score": round(audio, 3),
        "continuity_score": round(continuity, 3),
        "redundancy_penalty": round(penalty, 3),
        "highlight_score": round(highlight, 3),
    }
    return scores, reasons or ["基础剧情候选"]


def _select_until(rows: List[Tuple[float, float, Dict[str, Any], Dict[str, float], List[str]]], chosen: List[Tuple[float, float, Dict[str, Any], Dict[str, float], List[str]]], *, stop_seconds: float, max_seconds: float) -> List[Tuple[float, float, Dict[str, Any], Dict[str, float], List[str]]]:
    total = sum(x[1] for x in chosen)
    chosen_ids = {_candidate_id(x[2]) for x in chosen}
    for row in rows:
        cid = _candidate_id(row[2])
        if cid in chosen_ids:
            continue
        if _overlaps_any(row, chosen):
            continue
        if total >= stop_seconds:
            break
        if total + row[1] > max_seconds and total >= stop_seconds * 0.85:
            continue
        chosen.append(row)
        chosen_ids.add(cid)
        total += row[1]
    return chosen


def _reject_reason(d: Dict[str, Any], score: float, threshold: float, total: float, target_seconds: float) -> str:
    if _is_hard_drop(d):
        return f"hard_drop:{d.get('drop_reason') or d.get('nonstory_tag') or 'nonstory'}"
    if d.get("drop_suggestion"):
        return f"soft_drop_suggestion:{d.get('drop_reason') or 'weak_or_repetitive'}"
    if score < threshold:
        return f"score_below_threshold:{score:.3f}<{threshold:.3f}"
    if total >= target_seconds:
        return "target_duration_reached"
    return "not_selected_after_coverage_fill"


def _coverage_gate(*, target_seconds: float, hard_min: float, preferred_min: float, selected_duration: float, selectable_duration: float, fallback_added_count: int) -> Dict[str, Any]:
    issues: List[str] = []
    if selected_duration >= preferred_min:
        status = "passed"
    elif selected_duration >= hard_min:
        status = "warning"
        issues.append(f"selected_duration_below_preferred_min:{selected_duration:.1f}s<{preferred_min:.1f}s")
    else:
        status = "failed"
        issues.append(f"selected_duration_below_hard_min:{selected_duration:.1f}s<{hard_min:.1f}s")
        if selectable_duration < hard_min:
            issues.append(f"candidate_pool_insufficient:{selectable_duration:.1f}s<{hard_min:.1f}s")
    return {
        "stage": "05_highlight_selection_coverage",
        "ok": status in {"passed", "warning"},
        "status": status,
        "target_seconds": round(target_seconds, 3),
        "hard_min_seconds": round(hard_min, 3),
        "preferred_min_seconds": round(preferred_min, 3),
        "selected_duration_seconds": round(selected_duration, 3),
        "selectable_duration_seconds": round(selectable_duration, 3),
        "coverage_ratio": round(selected_duration / target_seconds, 4) if target_seconds > 0 else 0.0,
        "fallback_added_count": fallback_added_count,
        "issues": issues,
        "repair_action": "coverage_fallback_selection" if fallback_added_count else ("candidate_pool_insufficient" if status == "failed" else "none"),
    }


def _make_selected(chosen: List[Tuple[float, float, Dict[str, Any], Dict[str, float], List[str]]], fallback_ids: set[str], mode: str) -> List[SelectedHighlight]:
    chosen.sort(key=lambda x: _start(x[2]))
    selected: List[SelectedHighlight] = []
    for i, (_, _, d, scores, reasons) in enumerate(chosen, start=1):
        cid = _candidate_id(d, i)
        final_reasons = list(reasons or [])
        if cid in fallback_ids:
            final_reasons.append("coverage_fallback_selected")
        selected.append(SelectedHighlight(
            highlight_id=f"h_{i:04d}",
            source_candidate_id=cid,
            video_start=float(d.get("video_start", d.get("start", 0.0)) or 0.0),
            video_end=float(d.get("video_end", d.get("end", 0.0)) or 0.0),
            evidence_start=d.get("evidence_start"),
            evidence_end=d.get("evidence_end"),
            selected=True,
            selection_mode=mode,
            scores=scores,
            selection_reasons=final_reasons,
            character_trace=d.get("character_trace") or {},
            keep_original_audio=bool(d.get("raw_voice_suggestion")),
            highlight_rank=i,
            source_segment=d,
        ))
    return selected


def select_highlights_with_report(evidence_segments: Iterable[EvidenceSegment | Dict[str, Any]], *, target_minutes: int,
                                  highlight_selectivity: str = "balanced", narrative_strategy: str = "mixed") -> Dict[str, Any]:
    mode = normalize_selectivity(highlight_selectivity)
    cfg = CFG[mode]
    target_seconds = max(30.0, float(target_minutes or 8) * 60.0)
    hard_min = target_seconds * float(cfg["hard_min_ratio"])
    preferred_min = target_seconds * float(cfg["preferred_min_ratio"])
    preferred_max = target_seconds * float(cfg["preferred_max_ratio"])

    scored: List[Tuple[float, float, Dict[str, Any], Dict[str, float], List[str]]] = []
    for idx, seg in enumerate(evidence_segments or [], start=1):
        d = to_dict(seg)
        if not isinstance(d, dict):
            continue
        dur = item_duration(d)
        if dur <= 0:
            continue
        if not d.get("candidate_id"):
            d["candidate_id"] = _candidate_id(d, idx)
        scores, reasons = score_evidence_segment(d)
        scored.append((scores["highlight_score"], dur, d, scores, reasons))

    selectable = [x for x in scored if not _is_hard_drop(x[2])]
    selectable_duration = sum(x[1] for x in selectable)
    threshold = float(cfg["threshold"])

    # Initial pass: select the strongest story material. Loose modes preserve
    # chronology earlier; strict/balanced start from quality then are sorted back
    # to timeline order before output.
    if mode in {"loose", "very_loose"}:
        primary = [x for x in selectable if x[0] >= threshold or not x[2].get("drop_suggestion")]
        primary.sort(key=lambda x: (_start(x[2]), -x[0]))
    else:
        primary = [x for x in selectable if x[0] >= threshold and not x[2].get("drop_suggestion")]
        primary.sort(key=lambda x: (-x[0], _start(x[2])))

    chosen: List[Tuple[float, float, Dict[str, Any], Dict[str, float], List[str]]] = []
    chosen = _select_until(primary, chosen, stop_seconds=preferred_min, max_seconds=preferred_max)
    before_fallback_duration = sum(x[1] for x in chosen)

    # Coverage fallback is part of stage 3. If the first pass is too short, add
    # near-miss candidates in timeline order until the story has enough material
    # for narration. This is the key guard against producing a 20-second result
    # for an 8-minute target when hundreds of candidates exist.
    fallback_ids: set[str] = set()
    if before_fallback_duration < hard_min:
        fallback_pool = [
            x for x in selectable
            if _candidate_id(x[2]) not in {_candidate_id(y[2]) for y in chosen}
            and not x[2].get("drop_suggestion")
        ]
        fallback_pool.sort(key=lambda x: (_start(x[2]), -x[0]))
        before_ids = {_candidate_id(x[2]) for x in chosen}
        chosen = _select_until(fallback_pool, chosen, stop_seconds=preferred_min, max_seconds=preferred_max)
        after_ids = {_candidate_id(x[2]) for x in chosen}
        fallback_ids = after_ids - before_ids

    selected = _make_selected(chosen, fallback_ids, mode)
    chosen_ids = {h.source_candidate_id for h in selected}
    total_selected = sum(item_duration(x) for x in selected)
    fallback_report = {
        "stage": "05c_coverage_fallback_selection",
        "triggered": before_fallback_duration < hard_min,
        "target_seconds": round(target_seconds, 3),
        "hard_min_seconds": round(hard_min, 3),
        "preferred_min_seconds": round(preferred_min, 3),
        "before_selected_duration": round(before_fallback_duration, 3),
        "after_selected_duration": round(total_selected, 3),
        "fallback_added_count": len(fallback_ids),
        "added_candidate_ids": sorted(fallback_ids, key=lambda cid: next((_start(x[2]) for x in chosen if _candidate_id(x[2]) == cid), 0.0)),
        "fallback_reason": "selected_duration_below_hard_min" if before_fallback_duration < hard_min else "not_needed",
    }
    coverage = _coverage_gate(
        target_seconds=target_seconds,
        hard_min=hard_min,
        preferred_min=preferred_min,
        selected_duration=total_selected,
        selectable_duration=selectable_duration,
        fallback_added_count=len(fallback_ids),
    )

    rejected: List[Dict[str, Any]] = []
    for score, dur, d, scores, reasons in scored:
        cid = _candidate_id(d)
        if cid in chosen_ids:
            continue
        rejected.append({
            "candidate_id": cid,
            "candidate_type": d.get("candidate_type"),
            "video_start": d.get("video_start", d.get("start")),
            "video_end": d.get("video_end", d.get("end")),
            "duration": dur,
            "selected": False,
            "selection_mode": mode,
            "scores": scores,
            "selection_reasons": reasons,
            "rejected_reason": _reject_reason(d, score, threshold, total_selected, target_seconds),
            "drop_suggestion": bool(d.get("drop_suggestion")),
            "hard_drop": _is_hard_drop(d),
            "drop_reason": d.get("drop_reason") or "",
            "subtitle_text": str(d.get("subtitle_text") or "")[:500],
        })
    rejected.sort(key=lambda x: (float(x.get("video_start") or 0.0), str(x.get("candidate_id") or "")))

    flow_success_gates = [
        {
            "stage": "stage3_highlight_selection",
            "ok": bool(selected),
            "status": "passed" if selected else "failed",
            "target": "select_at_least_one_highlight",
            "actual": len(selected),
            "issues": [] if selected else ["no_highlights_selected"],
        },
        coverage,
        {
            "stage": "stage3_retention_policy",
            "ok": True,
            "status": "passed",
            "target": "stage3_is_the_only_stage_that_selects_highlights",
            "actual": "stage3_selection_complete",
            "issues": [],
        },
    ]
    overall_ok = all(g.get("ok") for g in flow_success_gates)

    return {
        "selected_highlights": selected,
        "rejected_candidates": rejected,
        "summary": {
            "selection_mode": mode,
            "narrative_strategy": narrative_strategy,
            "target_minutes": target_minutes,
            "target_seconds_requested": round(target_seconds, 3),
            "hard_min_seconds": round(hard_min, 3),
            "preferred_min_seconds": round(preferred_min, 3),
            "preferred_max_seconds": round(preferred_max, 3),
            "input_count": len(scored),
            "selectable_count": len(selectable),
            "selectable_duration": round(selectable_duration, 3),
            "selected_count": len(selected),
            "rejected_count": len(rejected),
            "selected_total_duration": round(total_selected, 3),
            "coverage_ratio": round(total_selected / target_seconds, 4) if target_seconds > 0 else 0.0,
            "threshold": threshold,
            "coverage_gate": coverage,
            "fallback_report": fallback_report,
            "flow_success_gates": flow_success_gates,
            "overall_ok": overall_ok,
            "policy": "stage3_is_the_only_stage_that_selects_highlights",
        },
    }


def select_highlights(evidence_segments: Iterable[EvidenceSegment | Dict[str, Any]], *, target_minutes: int,
                      highlight_selectivity: str = "balanced", narrative_strategy: str = "mixed") -> List[SelectedHighlight]:
    report = select_highlights_with_report(
        evidence_segments,
        target_minutes=target_minutes,
        highlight_selectivity=highlight_selectivity,
        narrative_strategy=narrative_strategy,
    )
    return list(report["selected_highlights"])
