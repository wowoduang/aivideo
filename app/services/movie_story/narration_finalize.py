from __future__ import annotations

"""Final narration gate for the movie-story production chain.

Stage F/G originally existed as bounded sample tools.  This module turns the
same quality concerns into a deterministic production finalizer: generated
script items are normalized, locked to their source semantic windows, checked
against the selected narration evidence, and annotated with validation metadata
before the legacy entry point writes the final script.

The finalizer deliberately avoids hidden LLM calls.  If an LLM rewrite stage is
added later, it should be an explicit dependency behind this module rather than
buried in ``subtitle_first_pipeline.py``.
"""

from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from loguru import logger

from app.services.movie_story.story_runtime import normalize_script_items_without_retiming
from app.services.script_fallback import ensure_script_shape

JsonDict = Dict[str, Any]


def _text(value: Any, max_chars: int = 0) -> str:
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (list, tuple, set)):
        text = "；".join(_text(x) for x in value if _text(x))
    elif isinstance(value, Mapping):
        text = "；".join(f"{k}:{_text(v)}" for k, v in value.items() if _text(v))
    else:
        text = str(value).strip()
    return text[:max_chars].rstrip() if max_chars and len(text) > max_chars else text


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _id_values(item: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("highlight_id", "scene_id", "segment_id", "candidate_id", "id"):
        value = item.get(key)
        if value:
            out.add(str(value))
    for key in ("source_scene_ids", "source_segment_ids", "scene_ids", "segment_ids", "evidence_ids"):
        values = item.get(key)
        if isinstance(values, (list, tuple, set)):
            out.update(str(x) for x in values if x)
    return out


def _window(item: Mapping[str, Any]) -> Tuple[float, float]:
    start = _as_float(item.get("semantic_start", item.get("start", item.get("video_start", 0.0))))
    end = _as_float(item.get("semantic_end", item.get("end", item.get("video_end", start))))
    if end <= start:
        end = start + max(_as_float(item.get("duration"), 1.0), 0.5)
    return round(start, 3), round(end, 3)


def _overlap_ratio(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    a0, a1 = _window(a)
    b0, b1 = _window(b)
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    base = max(0.001, min(a1 - a0, b1 - b0))
    return inter / base


def _find_evidence(item: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    ids = _id_values(item)
    best: tuple[float, Mapping[str, Any] | None] = (0.0, None)
    for ev in evidence or []:
        if not isinstance(ev, Mapping):
            continue
        if ids and ids & _id_values(ev):
            return ev
        ratio = _overlap_ratio(item, ev)
        if ratio > best[0]:
            best = (ratio, ev)
    return best[1] if best[1] is not None and best[0] >= 0.35 else {}


def _narration_text(item: Mapping[str, Any]) -> str:
    return _text(item.get("narration") or item.get("voiceover") or item.get("text") or item.get("commentary"), 2000)


def _source_text(evidence: Mapping[str, Any]) -> str:
    return _text(
        evidence.get("subtitle_text")
        or evidence.get("main_text_evidence")
        or evidence.get("source_text")
        or evidence.get("text"),
        2000,
    )


def _semantic_text(evidence: Mapping[str, Any]) -> str:
    local = evidence.get("local_understanding") if isinstance(evidence.get("local_understanding"), Mapping) else {}
    return _text(
        evidence.get("real_narrative_state")
        or evidence.get("surface_dialogue_meaning")
        or local.get("real_narrative_state")
        or local.get("core_event")
        or evidence.get("plot_function")
        or evidence.get("selected_reason"),
        1200,
    )


def _similarity(a: str, b: str) -> float:
    a = "".join(str(a or "").split())
    b = "".join(str(b or "").split())
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a[:800], b[:800]).ratio()


def validate_narration_item(item: Mapping[str, Any], evidence: Mapping[str, Any]) -> JsonDict:
    """Deterministically validate one narration item against its evidence."""
    narration = _narration_text(item)
    source = _source_text(evidence)
    semantic = _semantic_text(evidence)
    issues: List[str] = []
    if not narration:
        issues.append("empty_narration")
    if not evidence:
        issues.append("missing_source_evidence")
    repeat_ratio = _similarity(narration, source)
    if repeat_ratio >= 0.82 and len(source) >= 20:
        issues.append("subtitle_verbatim_risk")
    if narration and len(narration) < 8:
        issues.append("too_short")
    if narration and len(narration) > 260:
        issues.append("too_long_for_tts")
    ev_start, ev_end = _window(evidence) if evidence else _window(item)
    it_start, it_end = _window(item)
    if evidence and (it_start < ev_start - 6.0 or it_end > ev_end + 6.0):
        issues.append("time_window_drift")
    status = "pass"
    if any(x in issues for x in ("empty_narration", "missing_source_evidence")):
        status = "reject"
    elif issues:
        status = "review"
    grounding_score = max(0.0, 1.0 - (0.28 * len(issues)))
    if repeat_ratio >= 0.82:
        grounding_score = min(grounding_score, 0.55)
    return {
        "status": status,
        "issues": issues,
        "grounding_score": round(grounding_score, 3),
        "subtitle_repeat_ratio": round(repeat_ratio, 3),
        "safe_rewrite_hint": semantic[:260] if status != "pass" and semantic else "",
        "evidence_notes": [semantic[:180]] if semantic else [],
    }


def _repair_blank_narration(item: JsonDict, evidence: Mapping[str, Any]) -> JsonDict:
    """Repair only hard-empty narration using grounded semantic evidence.

    Non-empty review items are not rewritten here to avoid hidden semantic drift.
    They are annotated for review/safe-rewrite by a later explicit LLM stage.
    """
    if _narration_text(item):
        return item
    semantic = _semantic_text(evidence)
    if semantic:
        item["narration"] = semantic[:180]
        item["movie_story_finalize_repaired"] = "blank_narration_from_grounded_semantic_evidence"
    return item


def filter_script_items_by_highlights(script_items: Sequence[Mapping[str, Any]], story_highlights: Sequence[Mapping[str, Any]] | None = None) -> List[JsonDict]:
    """Keep script items aligned to selected highlights without retiming.

    The old function was a no-op wrapper.  This implementation remains
    conservative: when ids or time overlap are clear, it filters to selected
    highlights; when filtering would drop everything, it returns the normalized
    input to preserve compatibility.
    """
    items = [dict(x) for x in (script_items or []) if isinstance(x, Mapping)]
    highlights = [dict(x) for x in (story_highlights or []) if isinstance(x, Mapping)]
    if not items or not highlights:
        return normalize_script_items_without_retiming(items)
    selected: List[JsonDict] = []
    for item in items:
        ids = _id_values(item)
        keep = False
        for h in highlights:
            if ids and ids & _id_values(h):
                keep = True
                break
            if _overlap_ratio(item, h) >= 0.25:
                keep = True
                break
        if keep:
            item = dict(item)
            item["highlight_filter_selected"] = True
            item.setdefault("highlight_filter_reason", "selected_highlight_overlap")
            selected.append(item)
    return normalize_script_items_without_retiming(selected or items)


def lock_narration_items_to_semantic_windows(script_items: Sequence[Mapping[str, Any]], *args: Any, **kwargs: Any) -> List[JsonDict]:
    """Compatibility lock: preserve source semantic windows and avoid retiming."""
    return normalize_script_items_without_retiming(script_items)


def _scene_intervals(cut_points: Sequence[float]) -> List[Tuple[float, float]]:
    points = sorted({round(_as_float(x), 3) for x in (cut_points or [])})
    return [(points[i], points[i + 1]) for i in range(len(points) - 1) if points[i + 1] > points[i]]


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return max(a0, b0) < min(a1, b1)


def align_script_items_to_scene_cuts(script_items: Sequence[Mapping[str, Any]], cut_points: Sequence[float] | None = None, *args: Any, **kwargs: Any) -> List[JsonDict]:
    """Align narration items to existing scene-cut groups without crossing story guards.

    ``subtitle_first_pipeline.py`` used to own this policy.  The behavior now
    lives here so narration finalization remains modular while old tests/callers
    keep the same private function name through an import alias.
    """
    intervals = _scene_intervals(cut_points or [])
    out: List[JsonDict] = []
    for raw in script_items or []:
        item = dict(raw) if isinstance(raw, Mapping) else {}
        semantic_start = _as_float(item.get("semantic_start", item.get("start", 0.0)))
        semantic_end = _as_float(item.get("semantic_end", item.get("end", semantic_start)))
        if semantic_end <= semantic_start:
            semantic_end = semantic_start + max(_as_float(item.get("duration"), 1.0), 0.5)

        floor = None
        if item.get("prologue_trimmed") or item.get("prologue_original_before_prologue_end"):
            floor = _as_float(item.get("prologue_end", semantic_start), semantic_start)
        ceiling = None
        if item.get("story_end_trimmed") or item.get("after_story_end"):
            ceiling = _as_float(item.get("story_end", semantic_end), semantic_end)

        ranges: List[List[float]] = []
        for left, right in intervals:
            if not _overlaps(left, right, semantic_start, semantic_end):
                continue
            clipped_left = max(left, floor) if floor is not None else left
            clipped_right = min(right, ceiling) if ceiling is not None else right
            if clipped_right > clipped_left:
                ranges.append([round(clipped_left, 3), round(clipped_right, 3)])

        if ranges:
            item["start"] = round(max(min(r[0] for r in ranges), floor) if floor is not None else min(r[0] for r in ranges), 3)
            item["end"] = round(min(max(r[1] for r in ranges), ceiling) if ceiling is not None else max(r[1] for r in ranges), 3)
            item["scene_group_ranges"] = ranges
            item["scene_group_count"] = len(ranges)
            item["scene_group_mode"] = "scene_group"
        else:
            start = max(semantic_start, floor) if floor is not None else semantic_start
            end = min(semantic_end, ceiling) if ceiling is not None else semantic_end
            if end <= start:
                end = start + 0.5
            item["start"] = round(start, 3)
            item["end"] = round(end, 3)
            item.setdefault("scene_group_ranges", [])
            item.setdefault("scene_group_count", 0)
            item.setdefault("scene_group_mode", "semantic_keep")
        out.append(item)
    return normalize_script_items_without_retiming(out)


def finalize_narration_script(
    script_items: Sequence[Mapping[str, Any]],
    *,
    narration_evidence: Sequence[Mapping[str, Any]],
    story_highlights: Sequence[Mapping[str, Any]] | None = None,
    scene_cut_points: Sequence[float] | None = None,
    clip_match_tolerance_seconds: float = 3.0,
) -> tuple[List[JsonDict], JsonDict]:
    """Normalize, validate, and annotate the final production script."""
    del scene_cut_points, clip_match_tolerance_seconds  # reserved for future explicit snap policy
    items = ensure_script_shape(list(script_items or []))
    items = align_script_items_to_scene_cuts(items)
    items = lock_narration_items_to_semantic_windows(items)
    items = filter_script_items_by_highlights(items, story_highlights)

    evidence_rows = [dict(x) for x in (narration_evidence or []) if isinstance(x, Mapping)]
    final_items: List[JsonDict] = []
    validation_rows: List[JsonDict] = []
    for idx, raw in enumerate(items, start=1):
        item = dict(raw)
        evidence = dict(_find_evidence(item, evidence_rows))
        item = _repair_blank_narration(item, evidence)
        validation = validate_narration_item(item, evidence)
        item["movie_story_validation"] = validation
        item.setdefault("narration_order", idx)
        item.setdefault("movie_order", idx)
        if evidence:
            item.setdefault("source_highlight_id", evidence.get("highlight_id") or evidence.get("scene_id") or evidence.get("segment_id"))
            item.setdefault("semantic_start", evidence.get("semantic_start", evidence.get("start")))
            item.setdefault("semantic_end", evidence.get("semantic_end", evidence.get("end")))
        validation_rows.append({
            "index": idx,
            "source_highlight_id": item.get("source_highlight_id"),
            **validation,
        })
        final_items.append(item)

    status_counts: JsonDict = {"pass": 0, "review": 0, "reject": 0}
    for row in validation_rows:
        status = str(row.get("status") or "review")
        status_counts[status] = int(status_counts.get(status, 0)) + 1
    report: JsonDict = {
        "stage": "07c_final_narration_validation",
        "policy": "deterministic_grounding_gate_no_hidden_llm_rewrite",
        "input_script_items": len(script_items or []),
        "final_script_items": len(final_items),
        "narration_evidence_count": len(evidence_rows),
        "status_counts": status_counts,
        "items": validation_rows,
        "passed": bool(final_items) and status_counts.get("reject", 0) == 0,
    }
    if status_counts.get("review") or status_counts.get("reject"):
        logger.warning("最终解说校验存在 review/reject: {}", status_counts)
    return final_items, report
