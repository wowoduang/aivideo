# -*- coding: utf-8 -*-
"""Production narration engine for the movie-story pipeline.

Responsibility boundary:
- This module does NOT implement a new simplified narration prompt.
- This module standardizes selected highlights into the existing AIVideoGPT
  narration input contract and calls the existing full-plot narration generator.
- If the existing generator is unavailable, this module fails explicitly instead
  of copying subtitles into narration.
"""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

JsonDict = Dict[str, Any]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coalesce(*values: Any) -> str:
    for value in values:
        s = _text(value)
        if s:
            return s
    return ""


def _format_timestamp(seconds: Any) -> str:
    total_ms = int(round(max(_as_float(seconds), 0.0) * 1000.0))
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    sec = total_seconds % 60
    total_minutes = total_seconds // 60
    minute = total_minutes % 60
    hour = total_minutes // 60
    return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def _time_key(item: Mapping[str, Any]) -> Tuple[float, float, str]:
    start = _as_float(item.get("start", item.get("video_start", item.get("source_start", 0.0))))
    end = _as_float(item.get("end", item.get("video_end", item.get("source_end", start))))
    ident = _coalesce(item.get("highlight_id"), item.get("scene_id"), item.get("segment_id"), item.get("id"))
    return (start, end, ident)


def sort_timeline(records: Sequence[Mapping[str, Any]]) -> List[JsonDict]:
    """Return records sorted by movie time and annotated with narration order."""
    out: List[JsonDict] = [dict(x) for x in (records or []) if isinstance(x, Mapping)]
    out.sort(key=_time_key)
    for idx, item in enumerate(out, start=1):
        item["movie_order"] = idx
        item["narration_order"] = idx
        item.setdefault("timeline_order", idx)
    return out


def _id_set(item: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("scene_id", "segment_id", "candidate_id", "highlight_id", "id", "story_id", "parent_story_id"):
        v = item.get(key)
        if v:
            out.add(str(v))
    for key in ("scene_ids", "segment_ids", "evidence_ids"):
        vals = item.get(key)
        if isinstance(vals, (list, tuple, set)):
            out.update(str(x) for x in vals if x)
    return out


def _interval(item: Mapping[str, Any]) -> Tuple[float, float]:
    s = _as_float(item.get("start", item.get("video_start", item.get("source_start", 0.0))))
    e = _as_float(item.get("end", item.get("video_end", item.get("source_end", s))))
    if e <= s:
        e = s + max(_as_float(item.get("duration"), 1.0), 1.0)
    return s, e


def _overlap_ratio(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    a0, a1 = _interval(a)
    b0, b1 = _interval(b)
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    base = max(0.001, min(a1 - a0, b1 - b0))
    return inter / base


def _find_related(record: Mapping[str, Any], pool: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    ids = _id_set(record)
    best: tuple[float, Optional[Mapping[str, Any]]] = (0.0, None)
    for item in pool or []:
        if not isinstance(item, Mapping):
            continue
        if ids & _id_set(item):
            return item
        ov = _overlap_ratio(record, item)
        if ov > best[0]:
            best = (ov, item)
    return best[1] if best[0] >= 0.50 else None


def _subtitle_text(item: Mapping[str, Any], related_scene: Optional[Mapping[str, Any]] = None) -> str:
    related_scene = related_scene or {}
    return _coalesce(
        item.get("subtitle_text"),
        item.get("source_text"),
        item.get("text"),
        item.get("dialogue"),
        related_scene.get("subtitle_text"),
        related_scene.get("text"),
        item.get("evidence_text"),
    )


def _story_text(item: Mapping[str, Any], related_story: Optional[Mapping[str, Any]] = None) -> str:
    related_story = related_story or {}
    return _coalesce(
        item.get("parent_story_text"),
        item.get("story_text"),
        related_story.get("story_text"),
        related_story.get("text"),
        item.get("parent_story_summary"),
        related_story.get("summary"),
        item.get("context_text"),
    )


def _highlight_type(item: Mapping[str, Any]) -> str:
    vals = item.get("highlight_types")
    if isinstance(vals, list) and vals:
        return "、".join(_text(x) for x in vals if _text(x))
    return _coalesce(item.get("highlight_type"), item.get("plot_function"), "剧情推进")


def _build_local_understanding(item: Mapping[str, Any], subtitle: str, story_context: str) -> JsonDict:
    raw = item.get("local_understanding")
    local: JsonDict = dict(raw) if isinstance(raw, Mapping) else {}
    typ = _highlight_type(item)
    evidence = _coalesce(item.get("evidence_text"), item.get("main_text_evidence"), subtitle)
    reason = _coalesce(item.get("type_evidence"), item.get("selection_reason"), item.get("selected_reason"), item.get("reason"))
    real_parts: List[str] = []
    if typ:
        real_parts.append(f"叙事功能：{typ}。")
    if reason:
        real_parts.append(f"入选依据：{reason}。")
    if story_context:
        real_parts.append(f"所属故事上下文：{story_context[:520]}")
    elif evidence:
        real_parts.append(f"关键字幕证据：{evidence[:520]}")
    local.setdefault("core_event", _coalesce(item.get("summary"), item.get("narrative_state"), evidence)[:180])
    local.setdefault("plot_function", _coalesce(item.get("plot_function"), typ, "剧情推进"))
    local.setdefault("importance_level", item.get("importance_level") or _importance(item))
    local.setdefault("surface_dialogue_meaning", _coalesce(item.get("surface_dialogue_meaning"), subtitle, evidence)[:320])
    local.setdefault("real_narrative_state", "".join(real_parts)[:760])
    local.setdefault("highlight_type", typ)
    local.setdefault("narrative_risk_flags", item.get("narrative_risk_flags") or [])
    return local


def _importance(item: Mapping[str, Any]) -> str:
    existing = _text(item.get("importance_level"))
    if existing:
        return existing
    score = _as_float(item.get("highlight_score", item.get("score", 0.0)))
    if score >= 0.55:
        return "high"
    if score >= 0.36:
        return "medium"
    return "low"


def _default_global_context(timeline: Sequence[Mapping[str, Any]]) -> JsonDict:
    return {
        "main_storyline": "按电影时间顺序整理的高光片段，用于延续原有全片理解式解说链路。",
        "timeline_progression": [
            _coalesce(x.get("parent_story_text"), x.get("summary"), x.get("subtitle_text"), x.get("text"))[:100]
            for x in timeline[:16]
        ],
        "core_conflicts": [],
        "character_relations": [],
        "narrative_risk_flags": [],
    }


def build_scene_evidence(
    selected_highlights: Sequence[Mapping[str, Any]],
    *,
    scenes: Optional[Sequence[Mapping[str, Any]]] = None,
    stories: Optional[Sequence[Mapping[str, Any]]] = None,
    global_context: Optional[Mapping[str, Any]] = None,
) -> List[JsonDict]:
    """Convert selected highlights into the existing narration scene_evidence contract."""
    timeline = sort_timeline(selected_highlights)
    global_summary = dict(global_context or {}) or _default_global_context(timeline)
    evidence: List[JsonDict] = []
    for idx, item in enumerate(timeline, start=1):
        related_scene = _find_related(item, scenes or [])
        related_story = _find_related(item, stories or [])
        start, end = _interval(item)
        subtitle = _subtitle_text(item, related_scene)
        story_context = _story_text(item, related_story)
        local = _build_local_understanding(item, subtitle, story_context)
        raw_keep = bool(item.get("raw_voice_keep") or item.get("raw_voice_retain_suggestion"))
        if any(key in _highlight_type(item) for key in ("关键台词", "情绪爆发", "人物高光")):
            raw_keep = True
        row: JsonDict = {
            "segment_id": _coalesce(item.get("segment_id"), item.get("clip_id"), item.get("scene_id"), item.get("highlight_id"), f"selected_{idx:03d}"),
            "scene_id": _coalesce(item.get("scene_id"), item.get("clip_id"), item.get("id"), f"scene_{idx:03d}"),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(max(end - start, 0.001), 3),
            "timestamp": f"{_format_timestamp(start)}-{_format_timestamp(end)}",
            "subtitle_text": subtitle,
            "aligned_subtitle_text": subtitle,
            "main_text_evidence": _coalesce(item.get("evidence_text"), item.get("main_text_evidence"), subtitle),
            "surface_dialogue_meaning": local.get("surface_dialogue_meaning"),
            "real_narrative_state": local.get("real_narrative_state"),
            "local_understanding": local,
            "story_validation": dict(item.get("story_validation") or {"validator_status": "pass", "validator_hints": [], "raw_voice_keep": raw_keep}),
            "plot_function": _coalesce(item.get("plot_function"), item.get("highlight_type"), "剧情推进"),
            "plot_role": item.get("plot_role") or "highlight",
            "importance_level": local.get("importance_level"),
            "attraction_level": item.get("attraction_level") or item.get("type_confidence") or item.get("score"),
            "confidence": item.get("type_confidence") or item.get("score"),
            "highlight_type": item.get("highlight_type"),
            "highlight_types": item.get("highlight_types"),
            "type_details": item.get("type_details") or [],
            "type_evidence": item.get("type_evidence") or [],
            "selected_reason": item.get("selected_reason") or item.get("selection_reason") or item.get("reason"),
            "parent_story_id": item.get("parent_story_id") or item.get("story_id"),
            "parent_story_text": story_context,
            "visual_summary": item.get("visual_summary") or (related_scene or {}).get("visual_summary") or [],
            "representative_frames": item.get("representative_frames") or (related_scene or {}).get("representative_frames") or [],
            "speaker_names": item.get("speaker_names") or item.get("characters") or (related_scene or {}).get("speaker_names") or [],
            "speaker_turns": item.get("speaker_turns") or (related_scene or {}).get("speaker_turns") or [],
            "exchange_pairs": item.get("exchange_pairs") or (related_scene or {}).get("exchange_pairs") or [],
            "subtitle_ids": item.get("subtitle_ids") or item.get("evidence_refs") or [],
            "raw_voice_retain_suggestion": raw_keep,
            "need_visual_verify": bool(item.get("need_visual_verify", False)),
            "boundary_confidence": item.get("boundary_confidence") or "medium",
            "boundary_reasons": item.get("boundary_reasons") or [],
            "movie_order": idx,
            "narration_order": idx,
            "selection_rank": item.get("selection_rank"),
            "source_highlight_record": dict(item),
        }
        if idx == 1:
            row["_global_summary"] = global_summary
        evidence.append(row)
    return evidence


def _read_app_config(name: str) -> str:
    env = os.environ.get(name.upper()) or os.environ.get(name)
    if env:
        return str(env)
    try:
        from app.config import config as app_config  # type: ignore
        app = getattr(app_config, "app", None)
        if isinstance(app, dict) and name in app:
            return str(app.get(name) or "")
        if app is not None and hasattr(app, name):
            return str(getattr(app, name) or "")
        if isinstance(app_config, dict):
            if name in app_config:
                return str(app_config.get(name) or "")
            nested = app_config.get("app")
            if isinstance(nested, dict) and name in nested:
                return str(nested.get(name) or "")
    except Exception:
        pass
    return ""


def _resolve_options(options: Optional[Mapping[str, Any]] = None) -> JsonDict:
    options = dict(options or {})
    nested_keys = ("narration_options", "commentary_options", "voiceover_options", "style_options", "frontend_style", "frontend_options")
    merged: JsonDict = {}
    for key in nested_keys:
        value = options.get(key)
        if isinstance(value, Mapping):
            merged.update(value)
    merged.update(options)
    for key in ("api_key", "llm_api_key", "openai_api_key"):
        merged.setdefault(key, _read_app_config(key))
    for key in ("base_url", "llm_base_url", "openai_base_url"):
        merged.setdefault(key, _read_app_config(key))
    for key in ("model", "llm_model", "text_model"):
        merged.setdefault(key, _read_app_config(key))
    merged.setdefault("style", _coalesce(
        merged.get("style"), merged.get("narration_style"), merged.get("commentary_style"),
        merged.get("script_style"), merged.get("voiceover_style"), _read_app_config("movie_story_narration_style"), "general"
    ))
    return merged


def _resolve_generator() -> tuple[Any, str]:
    errors: List[str] = []
    candidates = (
        ("app.services.generate_narration_script_clean", "generate_narration_from_scene_evidence"),
        ("app.services.generate_narration_script_clean", "generate_narration_script_from_scene_evidence"),
        ("app.services.generate_narration_script", "generate_narration_from_scene_evidence"),
        ("app.services.generate_narration_script", "generate_narration_script_from_scene_evidence"),
    )
    for module_name, func_name in candidates:
        try:
            module = __import__(module_name, fromlist=[func_name])
            func = getattr(module, func_name, None)
            if callable(func):
                return func, f"{module_name}.{func_name}"
        except Exception as exc:
            errors.append(f"{module_name}.{func_name}: {exc}")
    raise RuntimeError("existing narration generator not found; " + " | ".join(errors))


def _call_generator(func: Any, scene_evidence: List[JsonDict], options: Mapping[str, Any]) -> Any:
    sig = inspect.signature(func)
    params = sig.parameters
    kwargs: JsonDict = {}
    alias_values = {
        "api_key": _coalesce(options.get("api_key"), options.get("llm_api_key"), options.get("openai_api_key")),
        "base_url": _coalesce(options.get("base_url"), options.get("llm_base_url"), options.get("openai_base_url")),
        "model": _coalesce(options.get("model"), options.get("llm_model"), options.get("text_model")),
        "style": options.get("style"),
        "style_config": options,
        "config": options,
        "options": options,
        "project_context": options.get("project_context") or options.get("global_context"),
        "global_summary_json": options.get("global_summary") or options.get("global_context"),
        "full_subtitle_summary": options.get("full_subtitle_summary"),
        "frontend_style": options.get("frontend_style") or options.get("style"),
    }
    accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    for key, value in alias_values.items():
        if accepts_kwargs or key in params:
            kwargs[key] = value
    # First positional argument is the scene-evidence list in the existing chain.
    return func(scene_evidence, **kwargs)


def _normalise_script_result(raw: Any) -> List[JsonDict]:
    if raw is None:
        return []
    if isinstance(raw, list):
        rows = [dict(x) for x in raw if isinstance(x, Mapping)]
    elif isinstance(raw, Mapping):
        for key in ("script_items", "items", "narration_items", "lines", "result"):
            value = raw.get(key)
            if isinstance(value, list):
                rows = [dict(x) for x in value if isinstance(x, Mapping)]
                break
        else:
            rows = [dict(raw)] if any(k in raw for k in ("start", "end", "narration", "text")) else []
    else:
        rows = []
    rows = sort_timeline(rows)
    for idx, item in enumerate(rows, start=1):
        item.setdefault("_id", idx)
        item["movie_order"] = idx
        item["narration_order"] = idx
    return rows


def generate_from_selected_highlights(
    selected_highlights: Sequence[Mapping[str, Any]],
    *,
    scenes: Optional[Sequence[Mapping[str, Any]]] = None,
    stories: Optional[Sequence[Mapping[str, Any]]] = None,
    options: Optional[Mapping[str, Any]] = None,
    global_context: Optional[Mapping[str, Any]] = None,
) -> JsonDict:
    """Generate final narration using the existing full-plot narration chain."""
    opts = _resolve_options(options)
    timeline = sort_timeline(selected_highlights)
    evidence = build_scene_evidence(timeline, scenes=scenes, stories=stories, global_context=global_context or opts.get("global_context") or opts.get("global_summary"))
    try:
        func, engine_name = _resolve_generator()
        raw = _call_generator(func, evidence, opts)
        script_items = _normalise_script_result(raw)
        return {
            "status": "ok",
            "engine": engine_name,
            "policy": "selected_highlights_to_existing_full_plot_narration_chain",
            "style": opts.get("style"),
            "selected_highlights": timeline,
            "scene_evidence": evidence,
            "script_items": script_items,
            "raw_result_type": type(raw).__name__,
            "metadata": {
                "status": "ok",
                "engine": engine_name,
                "input_order": "chronological_movie_time",
                "selected_count": len(timeline),
                "scene_evidence_count": len(evidence),
                "script_item_count": len(script_items),
            },
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "engine": "existing_full_plot_narration_chain",
            "policy": "fail_explicitly_no_subtitle_passthrough",
            "style": opts.get("style"),
            "selected_highlights": timeline,
            "scene_evidence": evidence,
            "script_items": [],
            "metadata": {
                "status": "failed",
                "error": str(exc),
                "input_order": "chronological_movie_time",
                "selected_count": len(timeline),
                "scene_evidence_count": len(evidence),
                "script_item_count": 0,
            },
        }


def write_outputs(result: Mapping[str, Any], output_dir: str | os.PathLike[str]) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payloads = {
        "05_selected_highlights_timeline.json": result.get("selected_highlights") or [],
        "06_scene_evidence_for_narration.json": result.get("scene_evidence") or [],
        "07_narration_script.json": result.get("script_items") or [],
        "narration_engine_manifest.json": {
            "status": result.get("status"),
            "engine": result.get("engine"),
            "policy": result.get("policy"),
            "style": result.get("style"),
            "error": result.get("error"),
            "metadata": result.get("metadata") or {},
        },
    }
    for name, data in payloads.items():
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# Compatibility names used by older call-sites.
def write_narration_script(selected_highlights: Sequence[Mapping[str, Any]], **kwargs: Any) -> JsonDict:
    return generate_from_selected_highlights(selected_highlights, **kwargs)


def generate_narration_script(selected_highlights: Sequence[Mapping[str, Any]], **kwargs: Any) -> JsonDict:
    return generate_from_selected_highlights(selected_highlights, **kwargs)


def build_narration_script(selected_highlights: Sequence[Mapping[str, Any]], **kwargs: Any) -> JsonDict:
    return generate_from_selected_highlights(selected_highlights, **kwargs)
