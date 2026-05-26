# -*- coding: utf-8 -*-
from __future__ import annotations

"""
timeline_runtime.py

Mode: audio_protected_timeline

原则：
1. 不再按版本号分叉 runtime；所有主流程只调用本模块的语义化入口。
2. 使用音频/字幕保护优先的稳定时间线算法。
3. shot 层保留视觉/字幕边界池；scene 层做边界保护后的合并。
4. 不使用 boundary_score；不做短片段后处理过滤。
5. 视觉边界（ffmpeg / PySceneDetect / 内部视觉切点）如果落在字幕内部：
   - 靠近字幕边缘则吸附到字幕边缘；
   - 落在一句话中间则丢弃，避免语音跨段。
6. subtitle_gap 比视觉镜头边界更强；视觉边界单独只代表画面切点。
7. 审计写入 _movie_story_pipeline_audit_clips 最新 run。
"""

import csv
import inspect
import json
import logging
import os
import re
import subprocess
from app.services.process_control import run_cancellable
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

_LAST_VIDEO_PATH = ""
_LAST_OUTPUT_PATH = ""


# =========================
# config
# =========================

def cfg(key: str, default=None):
    try:
        from app.config import config as app_config
        app = getattr(app_config, "app", None)
        if isinstance(app, dict) and key in app:
            return app.get(key)
        if app is not None and hasattr(app, key):
            return getattr(app, key)
        if isinstance(app_config, dict):
            if key in app_config:
                return app_config.get(key)
            if isinstance(app_config.get("app"), dict):
                return app_config["app"].get(key, default)
    except Exception as _e:
        logger.debug("配置字段读取失败，返回 default: {}", _e)
    return default


def cfg_bool(key: str, default: bool = False) -> bool:
    return str(cfg(key, default)).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def cfg_float(key: str, default: float) -> float:
    try:
        return float(cfg(key, default))
    except Exception:
        return float(default)


def cfg_int(key: str, default: int) -> int:
    try:
        return int(cfg(key, default))
    except Exception:
        return int(default)


def selectivity(fallback: str = "balanced") -> str:
    value = (
        os.environ.get("AIVIDEO_HIGHLIGHT_SELECTIVITY")
        or os.environ.get("MOVIE_STORY_HIGHLIGHT_SELECTIVITY")
        or str(cfg("movie_story_highlight_selectivity", "") or "")
        or fallback
    )
    value = str(value or "balanced").strip().lower()
    aliases = {
        "宽松": "loose",
        "较宽松": "loose",
        "很宽松": "very_loose",
        "严格": "strict",
        "均衡": "balanced",
        "默认": "balanced",
        "normal": "balanced",
        "medium": "balanced",
    }
    value = aliases.get(value, value)
    return value if value in {"strict", "balanced", "loose", "very_loose"} else "balanced"


# =========================
# utils
# =========================

def parse_time(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        parts = text.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except Exception:
        return None


def fmt(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def safe(value: Any) -> str:
    return str(value or "segment").replace("/", "_").replace("\\", "_")[:60]


def caller_value(name: str, default=None):
    frame = inspect.currentframe()
    if frame is None:
        return default
    try:
        cur = frame.f_back
        for _ in range(12):
            if cur is None:
                break
            if name in cur.f_locals and cur.f_locals.get(name) is not None:
                return cur.f_locals.get(name)
            cur = cur.f_back
    finally:
        del frame
    return default


def resolve_video_path(kwargs=None) -> str:
    kwargs = kwargs or {}
    for key in ("video_path", "video_origin_path", "source_video_path"):
        if kwargs.get(key):
            return str(kwargs.get(key))
    for key in ("video_path", "video_origin_path", "source_video_path"):
        value = caller_value(key)
        if value:
            return str(value)
    params = caller_value("params")
    if params is not None:
        for key in ("video_path", "video_origin_path", "source_video_path"):
            value = getattr(params, key, None)
            if value:
                return str(value)
    return ""


def resolve_output_path(kwargs=None) -> str:
    kwargs = kwargs or {}
    for key in ("output_script_path", "script_path", "output_path"):
        if kwargs.get(key):
            return str(kwargs.get(key))
    for key in ("output_script_path", "script_path", "output_path"):
        value = caller_value(key)
        if value:
            return str(value)
    return ""


# =========================
# visible audit
# =========================

def audit_base(video_path: str = "", output_path: str = "") -> Path:
    """Resolve timeline_runtime audit root from explicit output path only.

    RUNTIME DIAGNOSTIC:
    This path is used only for timeline/runtime audit files such as shot,
    scene, evidence, and runtime highlight diagnostic snapshots.

    Producer:
    - timeline_runtime.audit_stage

    Consumer:
    - human audit review / debugging tools

    Failure policy:
    A frontend movie_story job must pass output_script_path/output_path from
    the task directory. Do not infer audit output from video_path.parent,
    because that writes into frontend_uploads/video and splits one job into
    multiple audit roots.
    """
    del video_path  # video_path is intentionally not a valid audit-root source.

    if output_path not in (None, ""):
        path = Path(str(output_path))
        if path.name == "_movie_story_pipeline_audit_clips":
            return path
        if path.suffix:
            return path.parent / "_movie_story_pipeline_audit_clips"
        return path / "_movie_story_pipeline_audit_clips"

    raise RuntimeError(
        "movie_story audit output requires output_script_path/output_path; "
        "refusing to infer from video_path"
    )

def run_dir(video_path: str = "", output_path: str = "") -> Path:
    rid = os.environ.get("AIVIDEO_PIPELINE_AUDIT_RUN_ID") or os.environ.get("AIVIDEO_AUDIT_RUN_ID")
    if not rid:
        rid = time.strftime("run_%Y%m%d_%H%M%S")
        os.environ["AIVIDEO_PIPELINE_AUDIT_RUN_ID"] = rid
        os.environ["AIVIDEO_AUDIT_RUN_ID"] = rid
    d = audit_base(video_path, output_path) / rid
    d.mkdir(parents=True, exist_ok=True)
    return d


def start_end(item: Dict[str, Any]) -> Tuple[float, float]:
    s = item.get("video_start", item.get("start", item.get("semantic_start", 0.0)))
    e = item.get("video_end", item.get("end", item.get("semantic_end", s)))
    try:
        s = float(s or 0.0)
        e = float(e or s)
    except Exception:
        s, e = 0.0, 0.0
    return s, e


def row_for(item: Dict[str, Any], idx: int) -> Dict[str, Any]:
    s, e = start_end(item)
    scores = item.get("scores") or {}
    hscore = item.get("highlight_score")
    if hscore is None:
        hscore = scores.get("highlight_score")
    if hscore is None:
        hscore = item.get("score")
    return {
        "idx": idx,
        "id": item.get("candidate_id") or item.get("highlight_id") or item.get("segment_id") or idx,
        "start": s,
        "end": e,
        "duration": round(max(0.0, e - s), 3),
        "timestamp": item.get("timestamp") or f"{fmt(s)}-{fmt(e)}",
        "candidate_type": item.get("candidate_type"),
        "selected": item.get("selected"),
        "drop_reason": item.get("drop_reason"),
        "plot_function": item.get("plot_function"),
        "score": hscore,
        "highlight_score": hscore,
        "story_score": scores.get("story_score", item.get("story_score")),
        "character_score": scores.get("character_score", item.get("character_score")),
        "information_score": scores.get("information_score", item.get("information_score")),
        "emotion_score": scores.get("emotion_score", item.get("emotion_score")),
        "visual_score": scores.get("visual_score", item.get("visual_score")),
        "audio_score": scores.get("audio_score", item.get("audio_score")),
        "continuity_score": scores.get("continuity_score", item.get("continuity_score")),
        "penalty": scores.get("penalty", item.get("penalty")),
        "children_count": len(item.get("children") or item.get("source_shot_ids") or item.get("source_scene_ids") or []),
        "boundary_start_reason": json.dumps(item.get("boundary_start_reason") or [], ensure_ascii=False),
        "boundary_end_reason": json.dumps(item.get("boundary_end_reason") or [], ensure_ascii=False),
        "reasons": json.dumps(item.get("selection_reasons") or item.get("highlight_reasons") or item.get("reasons") or [], ensure_ascii=False),
        "text": str(item.get("subtitle_text") or item.get("source_text") or item.get("text") or "")[:500],
        "subtitle_text": str(item.get("subtitle_text") or item.get("source_text") or item.get("text") or "")[:500],
        "surface_dialogue_meaning": str(item.get("surface_dialogue_meaning") or "")[:500],
        "real_narrative_state": str(item.get("real_narrative_state") or "")[:500],
        "conflict_summary": str(item.get("conflict_summary") or "")[:500],
        "character_motivation": str(item.get("character_motivation") or "")[:500],
        "story_function": str(item.get("story_function") or "")[:300],
        "importance_level": item.get("importance_level"),
        "narration_intent": json.dumps(item.get("narration_intent") or {}, ensure_ascii=False)[:800],
        "_global_summary": json.dumps(item.get("_global_summary") or {}, ensure_ascii=False)[:1200],
    }


def _audit_stage_namespace_and_name(namespace: str, stage: str) -> tuple[str, str]:
    """Resolve audit output namespace and stage name.

    This is audit-output organization only. It does not change runtime data,
    scene boundaries, highlight selection, or script output.

    PRODUCER namespaces:
    - runtime: timeline_runtime low-level diagnostics, such as shots/scenes/evidence.
    - story_audit: story_runtime audit-only story grouping windows.

    FORMALITY:
    - runtime outputs are RUNTIME DIAGNOSTIC.
    - story_audit outputs are AUDIT ONLY.
    """
    raw_namespace = str(namespace or "runtime").strip() or "runtime"
    raw_stage = str(stage or "unknown_stage").strip() or "unknown_stage"

    namespace_map = {
        "runtime": {
            "03_story_candidates": "03_runtime_story_candidates",
            "04_global_story_context": "04_runtime_story_context",
            "05_selected_highlights": "05_runtime_selected_highlight_candidates",
            "06_scene_evidence_for_narration": "06_runtime_scene_evidence_for_narration",
            "06a_evidence_completeness": "06a_runtime_evidence_completeness",
        },
        "story_audit": {
            "03_story_candidates": "03_story_windows_audit_only",
            "04_global_story_context": "04_story_audit_global_context",
            "05_selected_highlights": "05_story_audit_selected_highlights",
            "06_scene_evidence_for_narration": "06_story_audit_scene_evidence_for_narration",
            "06a_evidence_completeness": "06a_story_audit_evidence_completeness",
        },
    }

    mapped_stage = namespace_map.get(raw_namespace, {}).get(raw_stage, raw_stage)
    safe_namespace = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw_namespace)[:80]
    safe_stage = "".join(c if c.isalnum() or c in "._-" else "_" for c in mapped_stage)[:120]
    return safe_namespace, safe_stage


def audit_stage(stage: str, items: List[Dict[str, Any]], video_path: str = "", output_path: str = "", metadata=None, export_clips: Optional[bool] = None, namespace: str = "runtime"):

    # ===== reduced audit output guard BEGIN =====
    # This guard only controls debug/audit output. It does not affect pipeline data.





    # ===== production movie-story audit policy BEGIN =====
    try:
        from pathlib import Path as _AuditPath
        from app.services.movie_story.audit_policy import should_skip_stage as _ms_should_skip_stage, should_export_clips as _ms_should_export_clips
        _ms_stage_name = str(stage or "")
        if _ms_should_skip_stage(_ms_stage_name):
            return _AuditPath("_skipped")
        if not _ms_should_export_clips(_ms_stage_name):
            export_clips = False
    except Exception as _e:
        logger.warning("操作失败（已捕获）: {}", _e)
    # ===== production movie-story audit policy END =====
    default_keep = (
        "00_active_movie_story_runtime,"
        "00c_boundary_summary,"
        "01_shot_candidates,"
        "02_scene_candidates,"
        "03_story_candidates,"
        "04_global_story_context,"
        "04_typed_highlight_candidates,"
        "05_selected_highlights,"
        "06_scene_evidence_for_narration,"
        "06a_evidence_completeness,"
        "07_narration_script"
    )
    default_clip = (
        "01_shot_candidates,"
        "02_scene_candidates,"
        "05_selected_highlights,"
        "01a_shot_boundary_video_samples,"
        "03a_evidence_video_samples,"
        "04b_highlight_pre_selection_video_pool,"
        "05a_selected_highlight_videos,"
        "06b_rejected_near_miss_videos,"
        "10a_script_review_videos"
    )

    keep_raw = str(cfg("movie_story_audit_keep_stages", default_keep) or default_keep)
    keep_stages = {x.strip() for x in keep_raw.split(",") if x.strip()}
    try:
        from app.services.movie_story.audit_policy import (
            include_legacy_stages as _include_legacy_stages,
            required_keep_stages as _required_keep_stages,
        )
        keep_stages |= set(_required_keep_stages())
        if _include_legacy_stages():
            from app.services.movie_story.audit_policy import LEGACY_STAGES as _LEGACY_STAGES
            keep_stages |= set(_LEGACY_STAGES)
    except Exception:
        keep_stages |= {"04_global_story_context", "06_scene_evidence_for_narration", "06a_evidence_completeness"}

    # Empty keep_stages means keep all. Otherwise skip unlisted stages completely.
    if keep_stages and stage not in keep_stages:
        try:
            return audit_base(video_path, output_path) / "_skipped"
        except Exception:
            return Path("_skipped")

    clip_raw = str(cfg("movie_story_audit_clip_stages", default_clip) or default_clip)
    clip_stages = {x.strip() for x in clip_raw.split(",") if x.strip()}
    if clip_stages and stage not in clip_stages:
        export_clips = False
    # ===== reduced audit output guard END =====
    stage_namespace, stage_name = _audit_stage_namespace_and_name(namespace, stage)
    run = run_dir(video_path, output_path)
    stage_dir = run / stage_namespace / stage_name
    stage_index_name = f"{stage_namespace}/{stage_name}"
    clips_dir = stage_dir / "clips"
    stage_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    rows = [row_for(item, idx) for idx, item in enumerate(items or [], start=1)]
    total = round(sum(float(r.get("duration") or 0.0) for r in rows), 3)

    manifest = {
        "stage": stage,
        "count": len(items or []),
        "exported": 0,
        "total_duration": total,
        "metadata": metadata or {},
        "items": rows,
    }

    (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep the full, unflattened records for migration verification.  manifest.json
    # intentionally contains brief CSV-friendly rows; Stage-A needs the rich
    # scene_evidence fields such as real_narrative_state and _global_summary.
    (stage_dir / "items_full.json").write_text(json.dumps(items or [], ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        with (stage_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    idx_path = run / "_stage_index.json"
    try:
        index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
    except Exception:
        index = []
    index.append({"stage": stage_index_name, "source_stage": stage, "producer": stage_namespace, "dir": str(stage_dir), "count": len(items or []), "exported": 0, "total_duration": total})
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    if export_clips is None:
        export_clips = cfg_bool("movie_story_audit_export_clips", False)
    if stage.startswith("00"):
        export_clips = False
    if stage.startswith("04a_scored"):
        export_clips = cfg_bool("movie_story_audit_export_scored_clips", False)

    if not export_clips or not video_path or not Path(video_path).exists():
        logger.warning("movie_story timeline_runtime audit manifest only: %s count=%s dir=%s", stage, len(items or []), stage_dir)
        return stage_dir

    max_clips = cfg_int("movie_story_audit_max_clips_per_stage", 560)
    exported = 0
    for idx, (item, r) in enumerate(zip(items or [], rows), start=1):
        if idx > max_clips:
            break
        s, e = start_end(item)
        dur = max(0.0, e - s)
        if dur < 0.5:
            continue
        clip = clips_dir / f"{idx:03d}_{safe(r['id'])}_{s:.3f}_{e:.3f}.mp4"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{s:.3f}", "-i", video_path, "-t", f"{dur:.3f}",
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "25", "-c:a", "aac",
            "-b:a", "96k", "-movflags", "+faststart", str(clip),
        ]
        try:
            ok = run_cancellable(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=max(30, int(dur) + 30)).returncode == 0
        except Exception:
            ok = False
        if ok:
            exported += 1

    manifest["exported"] = exported
    (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
        if index:
            index[-1]["exported"] = exported
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # 清理操作，忽略异常

    logger.warning("movie_story timeline_runtime audit: %s count=%s exported=%s dir=%s", stage, len(items or []), exported, stage_dir)
    return stage_dir



# =========================
# stage 1/2/3 closure audit bridge
# =========================


# =========================
# stage 1/2/3 + human narration full closure bridge
# =========================

def _target_minutes_from_runtime_kwargs(kwargs: Dict[str, Any]) -> int:
    for key in ("target_duration_minutes", "target_minutes", "movie_story_target_minutes"):
        value = kwargs.get(key)
        if value is not None and str(value).strip() != "":
            try:
                return max(1, int(round(float(value))))
            except Exception as _e:
                logger.debug("数值转换失败，跳过: {}", _e)
    try:
        return max(1, int(round(float(cfg("movie_story_target_minutes", 8) or 8))))
    except Exception:
        return 8


def _split_merge_rows_for_audit(evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in evidence_items or []:
        try:
            s = item.get("video_start")
            e = item.get("video_end")
            duration = round(float(e or 0.0) - float(s or 0.0), 3) if s is not None and e is not None else item.get("duration")
        except Exception:
            duration = item.get("duration")
        rows.append({
            "candidate_id": item.get("candidate_id"),
            "candidate_type": item.get("candidate_type"),
            "video_start": item.get("video_start"),
            "video_end": item.get("video_end"),
            "start": item.get("video_start"),
            "end": item.get("video_end"),
            "duration": duration,
            "split_merge_suggestion": item.get("split_merge_suggestion") or {},
            "drop_suggestion": item.get("drop_suggestion"),
            "drop_reason": item.get("drop_reason"),
            "subtitle_text": item.get("subtitle_text") or item.get("source_text") or item.get("text") or "",
            "stage2_policy": "suggest_only_no_delete",
        })
    return rows


def _selected_rows_for_audit(selected_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for idx, item in enumerate(selected_items or [], start=1):
        src = item.get("source_segment") or item.get("source_candidate") or {}
        s = item.get("video_start", src.get("video_start", src.get("start", 0.0)))
        e = item.get("video_end", src.get("video_end", src.get("end", s)))
        try:
            s = float(s or 0.0); e = float(e or s)
        except Exception:
            s, e = 0.0, 0.0
        text = item.get("subtitle_text") or item.get("source_text") or src.get("subtitle_text") or src.get("source_text") or src.get("text") or ""
        scores = item.get("scores") or {}
        seg_id = item.get("highlight_id") or item.get("segment_id") or item.get("candidate_id") or f"h_{idx:04d}"
        rows.append({
            **item,
            "candidate_type": "highlight",
            "segment_id": seg_id,
            "highlight_id": item.get("highlight_id") or seg_id,
            "highlight_rank": item.get("highlight_rank") or idx,
            "source_candidate_id": item.get("source_candidate_id") or src.get("candidate_id"),
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "semantic_start": item.get("evidence_start") or src.get("semantic_start") or s,
            "semantic_end": item.get("evidence_end") or src.get("semantic_end") or e,
            "duration": round(max(0.0, e - s), 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
            "subtitle_text": text,
            "source_text": text,
            "selected": True,
            "score": scores.get("highlight_score", item.get("score", item.get("highlight_score"))),
            "highlight_score": scores.get("highlight_score", item.get("highlight_score", item.get("score"))),
            "highlight_reasons": item.get("selection_reasons") or item.get("highlight_reasons") or [],
            "selection_policy": "stage3_three_stage_closure",
            "time_policy": "video_start_video_end_authoritative_no_tts_retime",
        })
    return rows


def _audit_single_payload_stage(stage: str, payload: Dict[str, Any], video_path: str, output_path: str, metadata: Dict[str, Any] | None = None) -> None:
    audit_stage(stage, [{
        "candidate_id": stage,
        "candidate_type": "closure_payload",
        "video_start": 0.0,
        "video_end": 0.001,
        "duration": 0.001,
        "subtitle_text": json.dumps(payload, ensure_ascii=False)[:1000],
        "payload": payload,
    }], video_path, output_path, metadata or {}, export_clips=False)



# =========================
# success-judgement diagnostic video export
# =========================

def _diagnostic_score(item: Dict[str, Any]) -> float:
    scores = item.get("scores") if isinstance(item, dict) else None
    if isinstance(scores, dict):
        for key in ("highlight_score", "score", "story_score"):
            try:
                if scores.get(key) is not None:
                    return float(scores.get(key) or 0.0)
            except Exception as _e:
                logger.debug("数值转换失败，跳过: {}", _e)
    for key in ("highlight_score", "score", "final_story_score", "story_score"):
        try:
            if item.get(key) is not None:
                return float(item.get(key) or 0.0)
        except Exception as _e:
            logger.debug("数值转换失败，跳过: {}", _e)
    return 0.0


def _diagnostic_bounds_key(item: Dict[str, Any]) -> tuple[float, float, str]:
    try:
        s, e = start_end(item)
    except Exception:
        s = float(item.get("video_start") or item.get("start") or 0.0)
        e = float(item.get("video_end") or item.get("end") or s)
    return (round(float(s), 3), round(float(e), 3), str(item.get("candidate_id") or item.get("segment_id") or item.get("highlight_id") or ""))


def _dedupe_diagnostic_items(items: Iterable[Dict[str, Any]], max_count: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        key = _diagnostic_bounds_key(raw)
        if key in seen:
            continue
        seen.add(key)
        cur = dict(raw)
        try:
            s, e = start_end(cur)
            cur.setdefault("start", s)
            cur.setdefault("end", e)
            cur.setdefault("video_start", s)
            cur.setdefault("video_end", e)
            cur.setdefault("duration", round(max(0.0, float(e) - float(s)), 3))
        except Exception as _e:
            logger.debug("数值转换失败，跳过: {}", _e)
        out.append(cur)
        if len(out) >= max_count:
            break
    return out


def _diagnostic_representative_sample(items: Iterable[Dict[str, Any]], *, max_count: int = 20) -> List[Dict[str, Any]]:
    seq = [x for x in (items or []) if isinstance(x, dict)]
    if not seq:
        return []
    max_count = max(1, int(max_count or 20))
    selected: List[Dict[str, Any]] = []
    selected.extend(seq[: min(4, len(seq))])
    selected.extend(seq[-min(4, len(seq)) :])
    if len(seq) > 1:
        slots = max(1, max_count - len(selected))
        step = max(1, len(seq) // max(1, slots))
        selected.extend(seq[::step][:slots])
    selected.extend(sorted(seq, key=lambda x: float(x.get("duration") or 0.0), reverse=True)[: max(2, max_count // 4)])
    annotated = []
    for idx, item in enumerate(selected, start=1):
        cur = dict(item)
        cur.setdefault("diagnostic_role", "representative_boundary_sample")
        cur.setdefault("diagnostic_reason", "edge/even/longest sample for visual boundary review")
        cur["diagnostic_rank"] = idx
        annotated.append(cur)
    return _dedupe_diagnostic_items(annotated, max_count)


def _diagnostic_top_rejected(rejected: Iterable[Dict[str, Any]], *, max_count: int = 12) -> List[Dict[str, Any]]:
    rows = [x for x in (rejected or []) if isinstance(x, dict)]
    rows.sort(key=_diagnostic_score, reverse=True)
    out = []
    for idx, item in enumerate(rows[: max(1, int(max_count or 12))], start=1):
        cur = dict(item)
        cur["diagnostic_role"] = "near_miss_rejected_candidate"
        cur["diagnostic_reason"] = "high scoring rejected clip; review whether selection is too strict"
        cur["diagnostic_rank"] = idx
        out.append(cur)
    return out


def _diagnostic_pre_selection_pool(evidence: Iterable[Dict[str, Any]], selected: Iterable[Dict[str, Any]], rejected: Iterable[Dict[str, Any]], *, max_count: int = 24) -> List[Dict[str, Any]]:
    selected_ids = {str(x.get("source_candidate_id") or x.get("candidate_id") or "") for x in (selected or []) if isinstance(x, dict)}
    selected_ids |= {str(x.get("candidate_id") or "") for x in (selected or []) if isinstance(x, dict)}
    evidence_rows = [x for x in (evidence or []) if isinstance(x, dict)]
    chosen = []
    for item in evidence_rows:
        cid = str(item.get("candidate_id") or item.get("source_candidate_id") or "")
        if cid and cid in selected_ids:
            cur = dict(item)
            cur["diagnostic_role"] = "pre_selection_selected_source"
            cur["diagnostic_reason"] = "evidence segment before final highlight selection"
            chosen.append(cur)
    chosen.extend(_diagnostic_top_rejected(rejected, max_count=max(6, max_count // 2)))
    if len(chosen) < max(3, min(8, max_count)):
        for item in sorted(evidence_rows, key=_diagnostic_score, reverse=True)[:max_count]:
            cur = dict(item)
            cur.setdefault("diagnostic_role", "pre_selection_ranked_candidate")
            cur.setdefault("diagnostic_reason", "candidate pool sample before final highlight selection")
            chosen.append(cur)
    return _dedupe_diagnostic_items(chosen, max_count)


def _diagnostic_script_review_items(selected: Iterable[Dict[str, Any]], script_items: Iterable[Dict[str, Any]], *, max_count: int = 24) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for script in script_items or []:
        if not isinstance(script, dict):
            continue
        for key in (script.get("segment_id"), script.get("highlight_id"), script.get("source_candidate_id"), script.get("candidate_id")):
            if key:
                by_id[str(key)] = script
    out = []
    for idx, item in enumerate(selected or [], start=1):
        if not isinstance(item, dict):
            continue
        cur = dict(item)
        script = None
        for key in (cur.get("segment_id"), cur.get("highlight_id"), cur.get("source_candidate_id"), cur.get("candidate_id")):
            if key and str(key) in by_id:
                script = by_id[str(key)]
                break
        if script:
            cur["diagnostic_script_text"] = script.get("text") or script.get("script") or ""
            cur["subtitle_text"] = cur.get("subtitle_text") or script.get("text") or script.get("script") or ""
        cur["diagnostic_role"] = "selected_highlight_with_script_text"
        cur["diagnostic_reason"] = "review whether narration text matches the selected video clip"
        cur["diagnostic_rank"] = idx
        out.append(cur)
    return _dedupe_diagnostic_items(out, max_count)


def _audit_success_judgement_video_stage(stage: str, items: Iterable[Dict[str, Any]], video_path: str, output_path: str, metadata: Dict[str, Any] | None = None, *, max_count: int = 20) -> None:
    if not cfg_bool("movie_story_diagnostic_video_export", True):
        return
    try:
        sample = _dedupe_diagnostic_items(items or [], max_count=max_count)
        audit_stage(stage, sample, video_path, output_path, {
            **(metadata or {}),
            "diagnostic_video_export": True,
            "diagnostic_max_count": max_count,
            "purpose": "human_judgement_of_movie_story_success",
        }, export_clips=True)
    except Exception as exc:
        logger.warning("movie_story diagnostic video export skipped for %s: %s", stage, exc)


def _selection_coverage_gate_payload(selection_summary: Dict[str, Any], *, target_minutes: int) -> Dict[str, Any]:
    try:
        target_seconds = float(selection_summary.get("target_seconds_effective") or (float(target_minutes or 1) * 60.0))
    except Exception:
        target_seconds = float(max(1, int(target_minutes or 1)) * 60)
    try:
        selected_duration = float(selection_summary.get("selected_total_duration") or 0.0)
    except Exception:
        selected_duration = 0.0
    try:
        selected_count = int(selection_summary.get("selected_count") or 0)
    except Exception:
        selected_count = 0
    ratio = selected_duration / target_seconds if target_seconds > 0 else 0.0
    issues = []
    warnings = []
    if selected_count <= 0:
        issues.append("no_highlights_selected")
    if ratio < 0.35:
        issues.append(f"selected_duration_far_below_target:{selected_duration:.1f}s<{target_seconds * 0.35:.1f}s")
    elif ratio < 0.65:
        warnings.append(f"selected_duration_below_target:{selected_duration:.1f}s<{target_seconds * 0.65:.1f}s")
    return {
        "passed": not issues,
        "selected_count": selected_count,
        "selected_total_duration": round(selected_duration, 3),
        "target_seconds": round(target_seconds, 3),
        "coverage_ratio": round(ratio, 4),
        "issues": issues,
        "warnings": warnings,
        "policy": "selection_should_be_long_enough_for_requested_target_minutes",
    }

def _audit_three_stage_closure_after_scene_candidates(
    scenes: List[Dict[str, Any]],
    subtitle_segments: Iterable[Dict[str, Any]],
    video_path: str,
    output_path: str,
    *,
    target_minutes: int,
    highlight_selectivity: str,
    narrative_strategy: str,
) -> None:
    """Complete the real timeline runtime after 02_scene_candidates.

    This bridge closes the visible Movie Story flow for real runs:
    02 scene candidates -> 03 evidence -> 04 split/merge suggestions ->
    05 selected highlights -> 06 rejected candidates -> 07/08 human narration
    -> 09 subtitle design -> 10 production quality gate -> 11 summary.

    It is deliberately deterministic and local: it does not call LLM/TTS/render,
    and it never changes the chunks returned by build_authoritative_plot_chunks.
    """
    if not cfg_bool("movie_story_full_closure_audit", True):
        return

    closure_status: Dict[str, Any] = {
        "source": "timeline_runtime_after_02_scene_candidates",
        "input_scene_count": len(scenes or []),
        "target_minutes": target_minutes,
        "highlight_selectivity": highlight_selectivity,
        "narrative_strategy": narrative_strategy,
        "stages": {},
        "policy": {
            "stage1": "cut_full_do_not_select",
            "stage2": "enrich_and_suggest_do_not_delete",
            "stage3": "only_stage_allowed_to_select_highlights",
            "retiming": "script_tts_audio_must_not_modify_video_start_video_end",
        },
    }

    try:
        from app.services.movie_story.schemas import to_dict
        from app.services.movie_story.stage2_evidence import enrich_candidates_with_evidence
        from app.services.movie_story.stage3_highlight_selection import select_highlights_with_report
        from app.services.movie_story.human_narration.pipeline import build_human_narration_package
        from app.services.movie_story.production.subtitle_designer import design_subtitle_cues
        from app.services.movie_story.production.video_quality_gate import check_video_plan_quality

        evidence_objects = enrich_candidates_with_evidence(
            scenes,
            list(subtitle_segments or []),
            visual_cards=None,
        )
        evidence = to_dict(evidence_objects)
        if not isinstance(evidence, list):
            evidence = []
        for item in evidence:
            if isinstance(item, dict):
                item["stage2_policy"] = "enrich_and_suggest_no_delete"
                item["runtime_bridge"] = "timeline_runtime_after_02"
        closure_status["stages"]["03_evidence_segments"] = {"count": len(evidence)}
        audit_stage("03_evidence_segments", evidence, video_path, output_path, {
            "source": "timeline_runtime_after_02_scene_candidates",
            "policy": "stage2_enrich_no_delete",
            "input_scene_count": len(scenes or []),
            "output_evidence_count": len(evidence or []),
        }, export_clips=False)
        _audit_success_judgement_video_stage(
            "03a_evidence_video_samples",
            _diagnostic_representative_sample(evidence, max_count=cfg_int("movie_story_diagnostic_evidence_samples", 16)),
            video_path,
            output_path,
            {"source": "03_evidence_segments", "review_goal": "judge_evidence_alignment_before_highlight_selection"},
            max_count=cfg_int("movie_story_diagnostic_evidence_samples", 16),
        )

        split_merge = _split_merge_rows_for_audit(evidence)
        closure_status["stages"]["04_split_merge_suggestions"] = {"count": len(split_merge)}
        audit_stage("04_split_merge_suggestions", split_merge, video_path, output_path, {
            "source": "stage2_evidence_segments",
            "policy": "suggest_only_no_delete",
        }, export_clips=False)

        selection_report = select_highlights_with_report(
            evidence,
            target_minutes=target_minutes,
            highlight_selectivity=highlight_selectivity,
            narrative_strategy=narrative_strategy,
        )
        selected = _selected_rows_for_audit(to_dict(selection_report.get("selected_highlights") or []))
        rejected = to_dict(selection_report.get("rejected_candidates") or [])
        if not isinstance(rejected, list):
            rejected = []
        selection_summary = selection_report.get("summary") or {}
        coverage_gate_payload = selection_summary.get("coverage_gate") or {}
        fallback_payload = selection_summary.get("fallback_report") or {}
        if coverage_gate_payload:
            closure_status["stages"]["05b_selection_coverage_gate"] = coverage_gate_payload
            _audit_single_payload_stage("05b_selection_coverage_gate", coverage_gate_payload, video_path, output_path, {
                "source": "stage3_highlight_selection",
                "status": coverage_gate_payload.get("status"),
                "ok": coverage_gate_payload.get("ok"),
                "repair_action": coverage_gate_payload.get("repair_action"),
            })
        if fallback_payload:
            closure_status["stages"]["05c_coverage_fallback_selection"] = fallback_payload
            _audit_single_payload_stage("05c_coverage_fallback_selection", fallback_payload, video_path, output_path, {
                "source": "stage3_highlight_selection",
                "triggered": fallback_payload.get("triggered"),
                "fallback_added_count": fallback_payload.get("fallback_added_count"),
            })
        closure_status["stages"]["05_selected_highlights"] = {"count": len(selected), "summary": selection_summary}
        closure_status["stages"]["06_rejected_candidates"] = {"count": len(rejected)}
        pre_selection_pool = _diagnostic_pre_selection_pool(
            evidence,
            selected,
            rejected,
            max_count=cfg_int("movie_story_diagnostic_pre_selection_samples", 24),
        )
        _audit_success_judgement_video_stage(
            "04b_highlight_pre_selection_video_pool",
            pre_selection_pool,
            video_path,
            output_path,
            {"source": "03_evidence_segments_plus_stage3_scores", "review_goal": "judge_highlight_before_after_selection"},
            max_count=cfg_int("movie_story_diagnostic_pre_selection_samples", 24),
        )
        coverage_gate = _selection_coverage_gate_payload(selection_summary, target_minutes=target_minutes)
        closure_status["stages"]["05b_selection_coverage_gate"] = coverage_gate
        _audit_single_payload_stage("05b_selection_coverage_gate", coverage_gate, video_path, output_path, {
            "source": "stage3_selection_summary",
            "passed": coverage_gate.get("passed"),
            "coverage_ratio": coverage_gate.get("coverage_ratio"),
        })
        _audit_success_judgement_video_stage(
            "05a_selected_highlight_videos",
            selected,
            video_path,
            output_path,
            {"source": "05_selected_highlights", "review_goal": "judge_final_selected_highlight_clips"},
            max_count=cfg_int("movie_story_diagnostic_selected_max", 80),
        )
        _audit_success_judgement_video_stage(
            "06b_rejected_near_miss_videos",
            _diagnostic_top_rejected(rejected, max_count=cfg_int("movie_story_diagnostic_near_miss_samples", 16)),
            video_path,
            output_path,
            {"source": "06_rejected_candidates", "review_goal": "judge_whether_good_clips_were_rejected"},
            max_count=cfg_int("movie_story_diagnostic_near_miss_samples", 16),
        )
        audit_stage("05_selected_highlights", selected, video_path, output_path, {
            **selection_summary,
            "source": "stage3_three_stage_closure",
            "policy": "stage3_only_stage_allowed_to_select_highlights",
        })
        audit_stage("06_rejected_candidates", rejected, video_path, output_path, {
            "source": "stage3_three_stage_closure",
            "policy": "rejected_candidates_are_visible_and_explainable",
            "rejected_count": len(rejected or []),
        }, export_clips=False)

        audit_stage("06_scene_evidence_for_narration", selected, video_path, output_path, {
            "source": "stage3_three_stage_closure_selected_highlights",
            "policy": "narration_handoff_preview_no_retime",
            "selected_count": len(selected or []),
        }, export_clips=False)

        human_package = build_human_narration_package(
            selected,
            global_summary="",
            style_key=str(cfg("movie_story_narration_style", "suspense") or "suspense"),
        )
        directed = human_package.get("directed_segments") or []
        hooks = human_package.get("opening_hooks") or []
        transitions = human_package.get("transitions") or []
        script_items = human_package.get("script_items") or []
        quality_report = human_package.get("quality_report") or {}
        closure_status["stages"]["07_human_narration_director"] = {"count": len(directed)}
        closure_status["stages"]["08_opening_hooks"] = {"count": len(hooks)}
        closure_status["stages"]["09_transition_sentences"] = {"count": len(transitions)}
        closure_status["stages"]["10_humanized_script_items"] = {"count": len(script_items), "quality_report": quality_report}
        audit_stage("07_human_narration_director", directed, video_path, output_path, {
            "source": "human_narration_layer",
            "style": (human_package.get("style_profile") or {}).get("style_key"),
        }, export_clips=False)
        audit_stage("08_opening_hooks", hooks, video_path, output_path, {
            "source": "human_narration_layer",
            "policy": "opening_hook_candidates_for_editor",
        }, export_clips=False)
        audit_stage("09_transition_sentences", transitions, video_path, output_path, {
            "source": "human_narration_layer",
            "policy": "connect_selected_highlights",
        }, export_clips=False)
        audit_stage("10_humanized_script_items", script_items, video_path, output_path, {
            "source": "human_narration_layer",
            "quality_report": quality_report,
            "policy": "editor_ready_script_items_no_retime",
        }, export_clips=False)
        _audit_success_judgement_video_stage(
            "10a_script_review_videos",
            _diagnostic_script_review_items(selected, script_items, max_count=cfg_int("movie_story_diagnostic_script_review_samples", 24)),
            video_path,
            output_path,
            {"source": "10_humanized_script_items", "review_goal": "judge_whether_script_matches_video"},
            max_count=cfg_int("movie_story_diagnostic_script_review_samples", 24),
        )

        subtitle_cues = design_subtitle_cues(script_items)
        closure_status["stages"]["11_subtitle_design_cues"] = {"count": len(subtitle_cues)}
        audit_stage("11_subtitle_design_cues", subtitle_cues, video_path, output_path, {
            "source": "production_subtitle_designer",
            "policy": "subtitle_design_suggestions_only",
        }, export_clips=False)

        quality_gate = check_video_plan_quality(script_items, source_highlights=selected)
        closure_status["stages"]["12_production_quality_gate"] = quality_gate
        _audit_single_payload_stage("12_production_quality_gate", quality_gate, video_path, output_path, {
            "source": "production_video_quality_gate",
            "passed": quality_gate.get("passed"),
            "issue_count": quality_gate.get("issue_count"),
            "warning_count": quality_gate.get("warning_count"),
        })

        closure_status["ok"] = True
        _audit_single_payload_stage("13_movie_story_full_closure_summary", closure_status, video_path, output_path, {
            "source": "timeline_runtime_after_02_scene_candidates",
            "ok": True,
        })
    except Exception as exc:
        logger.exception("movie_story full closure audit failed after 02_scene_candidates: %s", exc)
        closure_status["ok"] = False
        closure_status["error"] = str(exc)
        audit_stage("03_evidence_segments_error", [{
            "candidate_id": "full_closure_error",
            "candidate_type": "error",
            "video_start": 0.0,
            "video_end": 0.001,
            "subtitle_text": str(exc),
            "error": str(exc),
            "source": "timeline_runtime_after_02_scene_candidates",
        }], video_path, output_path, export_clips=False)
        _audit_single_payload_stage("13_movie_story_full_closure_summary", closure_status, video_path, output_path, {
            "source": "timeline_runtime_after_02_scene_candidates",
            "ok": False,
        })

def _movie_story_chain_from_kwargs(kwargs: Dict[str, Any]) -> str:
    raw = str(
        kwargs.get("movie_story_strategy")
        or kwargs.get("chain_strategy")
        or kwargs.get("understanding_strategy")
        or "native_runtime"
    ).strip().lower().replace("-", "_")
    aliases = {
        "legacy": "legacy_understanding",
        "old": "legacy_understanding",
        "old_understanding": "legacy_understanding",
        "subtitle_first": "legacy_understanding",
        "deep_understanding": "legacy_understanding",
        "native": "native_runtime",
        "new": "native_runtime",
        "typed": "native_runtime",
        "runtime": "native_runtime",
    }
    return aliases.get(raw, raw)

# =========================
# subtitle + boundary
# =========================

def subtitle_units(segments: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    units = []
    for idx, seg in enumerate(segments or [], start=1):
        start = parse_time(seg.get("start") or seg.get("begin") or seg.get("from"))
        end = parse_time(seg.get("end") or seg.get("to") or seg.get("finish"))
        if (start is None or end is None) and seg.get("timestamp") and "-" in str(seg.get("timestamp")):
            left, right = str(seg.get("timestamp")).split("-", 1)
            start, end = parse_time(left), parse_time(right)
        if start is None or end is None:
            continue
        if end <= start:
            end = start + 0.3
        units.append({
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            "text": str(seg.get("text") or seg.get("content") or seg.get("subtitle") or "").strip(),
        })
    units.sort(key=lambda x: (x["start"], x["end"]))
    return units


def subtitle_gap_boundaries(units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    medium_gap = cfg_float("movie_story_subtitle_medium_gap", 1.8)
    strong_gap = cfg_float("movie_story_subtitle_strong_gap", 2.5)
    for prev, cur in zip(units, units[1:]):
        gap = cur["start"] - prev["end"]
        if gap >= medium_gap:
            out.append({
                "time": round((prev["end"] + cur["start"]) / 2, 3),
                "reason": ["subtitle_gap_strong" if gap >= strong_gap else "subtitle_gap"],
                "gap": round(gap, 3),
            })
    return out


_PYSCENEDETECT_CACHE = {}


def _detect_ffmpeg_scene_boundaries_legacy(video_path: str, story_start: float, story_end: float) -> List[Dict[str, Any]]:
    if not video_path or not Path(video_path).exists():
        return []
    if not cfg_bool("movie_story_ffmpeg_scene_detect", True):
        return []

    threshold = cfg_float("movie_story_scene_threshold", 0.32)
    min_gap = cfg_float("movie_story_scene_boundary_min_gap", 4.0)
    timeout = cfg_int("movie_story_scene_detect_timeout", 240)
    vf = f"select='gt(scene,{threshold})',showinfo"
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-i", video_path, "-vf", vf, "-an", "-f", "null", "-"]

    result = run_cancellable(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=timeout)
    text = (result.stderr or "") + "\n" + (result.stdout or "")
    out = []
    last = None
    for m in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", text):
        t = float(m.group(1))
        if story_start < t < story_end and (last is None or t - last >= min_gap):
            out.append({"time": round(t, 3), "reason": ["ffmpeg_scene"]})
            last = t
    return out


def _pyscenedetect_detector_config() -> Dict[str, Any]:
    return {
        "mode": str(cfg("movie_story_pyscenedetect_mode", "adaptive") or "adaptive").strip().lower(),
        "adaptive_threshold": cfg_float("movie_story_pyscenedetect_adaptive_threshold", 3.0),
        "content_threshold": cfg_float("movie_story_pyscenedetect_content_threshold", 27.0),
        "min_scene_len_seconds": cfg_float("movie_story_pyscenedetect_min_scene_len_seconds", 0.8),
        "min_gap": cfg_float("movie_story_scene_boundary_min_gap", 0.8),
    }


def _merge_boundary_times(times: List[float], min_gap: float) -> List[float]:
    out = []
    for t in sorted(float(x) for x in times):
        if not out or t - out[-1] >= min_gap:
            out.append(t)
        else:
            # close peaks: keep the later one when the detector repeatedly fires around a cut
            out[-1] = (out[-1] + t) / 2.0
    return out


def detect_pyscenedetect_scene_boundaries(video_path: str, story_start: float, story_end: float) -> List[Dict[str, Any]]:
    """
    PySceneDetect based visual shot boundary detector.

    Important:
    - This is a visual shot detector, not story/highlight selection.
    - It replaces ffmpeg scene detect as the bottom-level boundary source.
    - Subtitle gaps are still used later by audio_protected_timeline scene merging.
    """
    if not video_path or not Path(video_path).exists():
        return []
    if not cfg_bool("movie_story_pyscenedetect_enabled", True):
        return []

    c = _pyscenedetect_detector_config()
    key = (
        str(Path(video_path).resolve()),
        c["mode"],
        c["adaptive_threshold"],
        c["content_threshold"],
        c["min_scene_len_seconds"],
    )
    if key in _PYSCENEDETECT_CACHE:
        all_times = _PYSCENEDETECT_CACHE[key]
    else:
        try:
            import cv2
            from scenedetect import SceneManager, open_video
            from scenedetect.detectors import AdaptiveDetector, ContentDetector
        except Exception as exc:
            logger.warning("PySceneDetect unavailable, fallback to ffmpeg scene detect: %s", exc)
            return []

        # Estimate fps for min_scene_len frames. Fallback to 25 fps.
        fps = 25.0
        try:
            cap = cv2.VideoCapture(str(video_path))
            got_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            cap.release()
            if got_fps > 1:
                fps = got_fps
        except Exception as _e:
            logger.debug("数值转换失败，跳过: {}", _e)

        min_scene_len = max(1, int(round(float(c["min_scene_len_seconds"]) * fps)))

        scene_manager = SceneManager()
        mode = c["mode"]
        added = False

        if mode in {"adaptive", "adaptive_content", "both"}:
            try:
                scene_manager.add_detector(
                    AdaptiveDetector(
                        adaptive_threshold=float(c["adaptive_threshold"]),
                        min_scene_len=min_scene_len,
                    )
                )
                added = True
            except TypeError:
                # Compatible fallback for older PySceneDetect signatures.
                scene_manager.add_detector(AdaptiveDetector(float(c["adaptive_threshold"]), min_scene_len=min_scene_len))
                added = True

        if mode in {"content", "adaptive_content", "both"}:
            try:
                scene_manager.add_detector(
                    ContentDetector(
                        threshold=float(c["content_threshold"]),
                        min_scene_len=min_scene_len,
                    )
                )
                added = True
            except TypeError:
                scene_manager.add_detector(ContentDetector(float(c["content_threshold"]), min_scene_len=min_scene_len))
                added = True

        if not added:
            scene_manager.add_detector(
                AdaptiveDetector(
                    adaptive_threshold=float(c["adaptive_threshold"]),
                    min_scene_len=min_scene_len,
                )
            )

        video = open_video(str(video_path))
        scene_manager.detect_scenes(video=video, show_progress=False)
        scene_list = scene_manager.get_scene_list()

        # scene_list = [(start_tc, end_tc), ...]. Boundary is each scene start after first.
        times = []
        for idx, pair in enumerate(scene_list):
            if idx == 0:
                continue
            start_tc = pair[0]
            try:
                times.append(float(start_tc.get_seconds()))
            except Exception as _e:
                logger.debug("数值转换失败，跳过: {}", _e)

        all_times = _merge_boundary_times(times, float(c["min_gap"]))
        _PYSCENEDETECT_CACHE[key] = all_times

    out = []
    for t in all_times:
        if story_start < float(t) < story_end:
            out.append({
                "time": round(float(t), 3),
                "reason": [f"pyscenedetect_{c['mode']}"],
            })
    return out


def detect_ffmpeg_scene_boundaries(video_path: str, story_start: float, story_end: float) -> List[Dict[str, Any]]:
    """
    Dispatcher retained for compatibility with existing build_shots().

    movie_story_shot_detector:
      - pyscenedetect  default
      - ffmpeg         legacy ffmpeg scene detect
      - hybrid         pyscenedetect plus ffmpeg, merged
    """
    detector = str(cfg("movie_story_shot_detector", "pyscenedetect") or "pyscenedetect").strip().lower()

    if detector in {"pyscenedetect", "py", "scenedetect"}:
        py_bounds = detect_pyscenedetect_scene_boundaries(video_path, story_start, story_end)
        if py_bounds or not cfg_bool("movie_story_pyscenedetect_fallback_to_ffmpeg_when_empty", True):
            return py_bounds
        return _detect_ffmpeg_scene_boundaries_legacy(video_path, story_start, story_end)

    if detector in {"hybrid", "both"}:
        py_bounds = detect_pyscenedetect_scene_boundaries(video_path, story_start, story_end)
        ff_bounds = _detect_ffmpeg_scene_boundaries_legacy(video_path, story_start, story_end)
        merged = py_bounds + ff_bounds
        min_gap = cfg_float("movie_story_scene_boundary_min_gap", 0.8)
        times = _merge_boundary_times([float(x["time"]) for x in merged], min_gap)
        return [{"time": round(t, 3), "reason": ["hybrid_visual_scene"]} for t in times if story_start < t < story_end]

    return _detect_ffmpeg_scene_boundaries_legacy(video_path, story_start, story_end)



def active_subtitle_at(units: List[Dict[str, Any]], t: float):
    margin = cfg_float("movie_story_boundary_subtitle_inside_margin", 0.25)
    for u in units:
        if u["start"] + margin < t < u["end"] - margin:
            return u
    return None


def protect_visual_boundaries(boundaries: List[Dict[str, Any]], units: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    snap = cfg_float("movie_story_boundary_snap_to_subtitle_edge_seconds", 0.75)
    protected = []
    dropped = 0
    snapped = 0

    for b in boundaries:
        t = float(b["time"])
        reasons = list(b.get("reason") or [])
        if not _has_visual_boundary_reason(reasons):
            protected.append(b)
            continue

        u = active_subtitle_at(units, t)
        if not u:
            protected.append(b)
            continue

        ds = abs(t - float(u["start"]))
        de = abs(t - float(u["end"]))
        if min(ds, de) <= snap:
            nt = float(u["start"] if ds <= de else u["end"])
            nb = dict(b)
            nb["time"] = round(nt, 3)
            nb["reason"] = sorted(set(reasons + ["snapped_subtitle_edge"]))
            protected.append(nb)
            snapped += 1
        else:
            dropped += 1

    return protected, {"dropped_inside_subtitle": dropped, "snapped_to_subtitle_edge": snapped}


def fuse_boundaries(boundaries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    window = cfg_float("movie_story_boundary_fuse_window", 1.2)
    raw = sorted(boundaries, key=lambda x: float(x["time"]))
    fused = []
    cluster = []

    def flush():
        if not cluster:
            return
        times = [float(x["time"]) for x in cluster]
        reasons = []
        for x in cluster:
            reasons.extend(x.get("reason") or [])
        fused.append({"time": round(sum(times) / len(times), 3), "reason": sorted(set(reasons))})

    for b in raw:
        if not cluster or abs(float(b["time"]) - float(cluster[-1]["time"])) <= window:
            cluster.append(b)
        else:
            flush()
            cluster = [b]
    flush()
    return fused


def text_between(units: List[Dict[str, Any]], s: float, e: float) -> str:
    return " ".join(u["text"] for u in units if u["end"] > s and u["start"] < e and u["text"]).strip()


def build_shots(segments, video_path: str, output_path: str, visual_mode: str = "auto"):
    units = subtitle_units(segments)
    if not units:
        return [], {"subtitle_units": 0}

    story_start, story_end = units[0]["start"], units[-1]["end"]
    audit_stage("00b_start_shot_detection", [{
        "candidate_id": "start_shot_detection",
        "candidate_type": "runtime_marker",
        "video_start": story_start,
        "video_end": min(story_start + 0.001, story_end),
        "subtitle_text": "start building shot candidates in audio_protected_timeline",
        "score": 1.0,
        "highlight_score": 1.0,
    }], video_path, output_path, export_clips=False)

    visual_enabled = str(visual_mode or "auto").strip().lower() != "off"
    ff_boundaries = []
    if visual_enabled:
        try:
            ff_boundaries = detect_ffmpeg_scene_boundaries(video_path, story_start, story_end)
        except Exception as exc:
            logger.exception("movie_story visual scene detect failed: %s", exc)

    protected_ff, protect_stats = protect_visual_boundaries(ff_boundaries, units)
    sub_boundaries = subtitle_gap_boundaries(units)
    fused = fuse_boundaries([b for b in protected_ff + sub_boundaries if story_start < float(b["time"]) < story_end])
    if visual_enabled:
        fused, visual_refine_stats = refine_internal_visual_boundaries(video_path, fused, story_start, story_end, units)
    else:
        visual_refine_stats = {"internal_visual_cuts_added": 0, "visual_refine_disabled": True}

    audit_stage("00c_boundary_summary", [{
        "candidate_id": "boundary_summary",
        "candidate_type": "summary",
        "video_start": story_start,
        "video_end": min(story_start + 0.001, story_end),
        "subtitle_text": (
            f"ffmpeg_boundaries={len(ff_boundaries)}, protected_ffmpeg={len(protected_ff)}, "
            f"subtitle_gap_boundaries={len(sub_boundaries)}, fused_boundaries={len(fused)}, "
            f"dropped_inside_subtitle={protect_stats.get('dropped_inside_subtitle')}, "
            f"snapped_to_subtitle_edge={protect_stats.get('snapped_to_subtitle_edge')}, internal_visual_cuts_added={visual_refine_stats.get('internal_visual_cuts_added', 0)}"
        ),
        "score": 1.0,
        "highlight_score": 1.0,
    }], video_path, output_path, {
        "ffmpeg_boundaries": len(ff_boundaries),
        "protected_ffmpeg": len(protected_ff),
        "subtitle_gap_boundaries": len(sub_boundaries),
        "fused_boundaries": len(fused),
        **protect_stats,
        **visual_refine_stats,
        "scene_threshold": cfg_float("movie_story_scene_threshold", 0.32),
    }, export_clips=False)

    cuts = [{"time": story_start, "reason": ["story_start"]}] + fused + [{"time": story_end, "reason": ["story_end"]}]
    shots = []
    for i in range(len(cuts) - 1):
        s, e = float(cuts[i]["time"]), float(cuts[i + 1]["time"])
        if e <= s:
            continue
        txt = text_between(units, s, e)
        sid = f"shot_{len(shots)+1:04d}"
        shots.append({
            "candidate_id": sid,
            "candidate_type": "shot",
            "segment_id": f"plot_{len(shots)+1:03d}",
            "scene_id": f"plot_{len(shots)+1:03d}",
            "video_start": round(s, 3),
            "video_end": round(e, 3),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e - s, 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
            "subtitle_text": txt,
            "source_text": txt,
            "main_text_evidence": txt,
            "boundary_start_reason": cuts[i].get("reason") or [],
            "boundary_end_reason": cuts[i + 1].get("reason") or [],
            "boundary_confidence": "high",
        })

    return shots, {
        "subtitle_units": len(units),
        "ffmpeg_boundaries": len(ff_boundaries),
        "protected_ffmpeg": len(protected_ff),
        "subtitle_gap_boundaries": len(sub_boundaries),
        "fused_boundaries": len(fused),
        **protect_stats,
        **visual_refine_stats,
    }



def _visual_refine_read_frame(cap, t: float, size=(240, 135)):
    cv2 = __import__("cv2")
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(t)) * 1000.0)
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    return cv2.resize(frame, size)


def _visual_refine_features(frame):
    cv2 = __import__("cv2")
    np = __import__("numpy")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    return hist, gray, edges


def _visual_refine_score_pair(prev_feat, cur_feat):
    cv2 = __import__("cv2")
    np = __import__("numpy")
    prev_hist, prev_gray, prev_edges = prev_feat
    cur_hist, cur_gray, cur_edges = cur_feat
    hist_diff = float(cv2.compareHist(prev_hist, cur_hist, cv2.HISTCMP_BHATTACHARYYA))
    mean_abs_diff = float(np.mean(cv2.absdiff(prev_gray, cur_gray)) / 255.0)
    edge_diff = float(np.mean(cv2.absdiff(prev_edges, cur_edges) > 0))
    score = 0.45 * hist_diff + 0.35 * mean_abs_diff + 0.20 * edge_diff
    return float(score)


def _scan_internal_visual_cut(video_path: str, start: float, end: float, step: float = 0.2):
    """
    Scan one existing shot interval for a missed internal visual cut.

    Returns:
        None or {"time": abs_time, "score": score, "threshold": threshold}
    """
    try:
        cv2 = __import__("cv2")
        np = __import__("numpy")
    except Exception:
        return None

    duration = float(end) - float(start)
    if duration <= 0:
        return None

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    rows = []
    prev_feat = None
    prev_t = None

    max_samples = int(cfg_int("movie_story_internal_visual_max_samples_per_interval", 80))
    times = []
    t = float(start)
    while t <= float(end) + 1e-6 and len(times) < max_samples:
        times.append(t)
        t += step
    if times and times[-1] < float(end):
        times.append(float(end))

    for t in times:
        frame = _visual_refine_read_frame(cap, t)
        if frame is None:
            continue
        feat = _visual_refine_features(frame)
        if prev_feat is not None:
            score = _visual_refine_score_pair(prev_feat, feat)
            rows.append({"time": round(float(t), 3), "prev_time": round(float(prev_t), 3), "score": score})
        prev_feat = feat
        prev_t = t

    cap.release()

    if not rows:
        return None

    scores = np.array([r["score"] for r in rows], dtype=float)
    median = float(np.median(scores))
    p95 = float(np.percentile(scores, 95))
    threshold = max(
        p95,
        median * float(cfg_float("movie_story_internal_visual_median_multiplier", 1.75)),
        float(cfg_float("movie_story_internal_visual_min_score", 0.28)),
    )

    min_side = float(cfg_float("movie_story_internal_visual_min_side_seconds", 1.0))
    candidates = []
    for r in rows:
        t = float(r["time"])
        if t <= float(start) + min_side or t >= float(end) - min_side:
            continue
        if float(r["score"]) >= threshold:
            candidates.append(r)

    if not candidates:
        return None

    best = max(candidates, key=lambda x: float(x["score"]))
    return {
        "time": round(float(best["time"]), 3),
        "score": round(float(best["score"]), 6),
        "threshold": round(float(threshold), 6),
        "median": round(float(median), 6),
        "p95": round(float(p95), 6),
    }


def refine_internal_visual_boundaries(video_path: str, boundaries: List[Dict[str, Any]], story_start: float, story_end: float, units: List[Dict[str, Any]]):
    """
    Add missed visual cuts inside existing shot intervals.

    This is NOT a subtitle rule and NOT a highlight rule.
    It only checks whether a current interval visually contains a strong internal jump.
    """
    stats = {
        "internal_visual_refine_enabled": False,
        "intervals_checked": 0,
        "internal_visual_cuts_added": 0,
    }

    if not cfg_bool("movie_story_internal_visual_refine", True):
        return boundaries, stats
    if not video_path or not Path(video_path).exists():
        return boundaries, stats

    stats["internal_visual_refine_enabled"] = True

    min_interval = float(cfg_float("movie_story_internal_visual_min_interval_seconds", 4.0))
    max_interval = float(cfg_float("movie_story_internal_visual_max_interval_seconds", 15.0))
    step = float(cfg_float("movie_story_internal_visual_step_seconds", 0.2))

    cuts = [{"time": float(story_start), "reason": ["story_start"]}] + list(boundaries or []) + [{"time": float(story_end), "reason": ["story_end"]}]
    cuts = sorted(cuts, key=lambda x: float(x["time"]))

    extra = []
    for a, b in zip(cuts, cuts[1:]):
        s, e = float(a["time"]), float(b["time"])
        dur = e - s
        if dur < min_interval or dur > max_interval:
            continue

        stats["intervals_checked"] += 1
        hit = _scan_internal_visual_cut(video_path, s, e, step=step)
        if not hit:
            continue

        t = float(hit["time"])
        if any(abs(t - float(x["time"])) < 0.7 for x in cuts + extra):
            continue

        extra.append({
            "time": round(t, 3),
            "reason": ["internal_visual_cut"],
            "internal_visual_score": hit.get("score"),
            "internal_visual_threshold": hit.get("threshold"),
            "internal_visual_median": hit.get("median"),
            "internal_visual_p95": hit.get("p95"),
        })

    if extra:
        stats["internal_visual_cuts_added"] = len(extra)
        merged = sorted(list(boundaries or []) + extra, key=lambda x: float(x["time"]))
        return merged, stats

    return boundaries, stats


# =========================
# shot -> scene
# =========================

def item_text(item: Dict[str, Any]) -> str:
    return str(item.get("subtitle_text") or item.get("source_text") or item.get("main_text_evidence") or "")


def has_transition_word(text: str) -> bool:
    markers = ["第二天", "与此同时", "另一边", "回到", "几天后", "随后", "转眼", "晚上", "第二日", "次日", "另一头", "没过多久", "过了一会儿", "此时"]
    return any(m in text for m in markers)



def _is_visual_boundary_reason(reason: str) -> bool:
    r = str(reason or "")
    return (
        r == "ffmpeg_scene"
        or r.startswith("pyscenedetect")
        or r == "internal_visual_cut"
    )


def _has_visual_boundary_reason(reasons: List[str]) -> bool:
    return any(_is_visual_boundary_reason(r) for r in reasons)

def reasons_of_next_boundary(shot: Dict[str, Any]) -> List[str]:
    return list(shot.get("boundary_start_reason") or [])


def should_merge_scene(current: List[Dict[str, Any]], shot: Dict[str, Any]) -> bool:
    if not current:
        return True

    s0 = float(current[0]["video_start"])
    e0 = float(current[-1]["video_end"])
    ss = float(shot["video_start"])
    se = float(shot["video_end"])
    cur_dur = e0 - s0
    after_dur = se - s0
    gap = max(0.0, ss - e0)

    min_ffmpeg = cfg_float("movie_story_scene_boundary_min_seconds", 6.0)
    min_subtitle = cfg_float("movie_story_subtitle_boundary_min_seconds", 3.0)
    hard_max = cfg_float("movie_story_scene_hard_max_seconds", 90.0)
    max_gap = cfg_float("movie_story_scene_merge_max_gap", 2.0)

    reasons = reasons_of_next_boundary(shot)
    text = item_text(shot)

    if after_dur > hard_max:
        return False

    if has_transition_word(text) and cur_dur >= min_subtitle:
        return False

    if gap > max_gap and cur_dur >= min_subtitle:
        return False

    if any(r.startswith("subtitle_gap") for r in reasons) and cur_dur >= min_subtitle:
        return False

    if "snapped_subtitle_edge" in reasons and cur_dur >= min_subtitle:
        return False

    internal_min = cfg_float("movie_story_internal_visual_cut_min_scene_seconds", 3.0)

    if "internal_visual_cut" in reasons and cur_dur >= internal_min:
        return False

    if _has_visual_boundary_reason(reasons) and cur_dur >= min_ffmpeg:
        return False

    return True


def merge_shots_to_scenes(shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scenes, buf = [], []

    def flush():
        nonlocal buf
        if not buf:
            return
        idx = len(scenes) + 1
        s, e = float(buf[0]["video_start"]), float(buf[-1]["video_end"])
        txt = " ".join(item_text(x) for x in buf if item_text(x)).strip()
        scenes.append({
            "candidate_id": f"scene_{idx:04d}",
            "candidate_type": "scene",
            "video_start": round(s, 3),
            "video_end": round(e, 3),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e - s, 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
            "subtitle_text": txt,
            "source_text": txt,
            "main_text_evidence": txt,
            "source_shot_ids": [x.get("candidate_id") for x in buf],
            "children": [x.get("candidate_id") for x in buf],
            "boundary_start_reason": buf[0].get("boundary_start_reason") or [],
            "boundary_end_reason": buf[-1].get("boundary_end_reason") or [],
            "merge_policy": "audio_protected_timeline",
        })
        buf = []

    for shot in shots:
        if not buf:
            buf.append(shot)
        elif should_merge_scene(buf, shot):
            buf.append(shot)
        else:
            flush()
            buf.append(shot)
    flush()
    return scenes


# =========================
# scoring
# =========================

PLOT_RULES = [
    ("信息揭露", ["真相", "秘密", "原来", "知道", "发现", "告诉", "证据", "身份"]),
    ("冲突升级", ["吵", "打", "杀", "滚", "别逼", "你敢", "威胁", "报仇"]),
    ("人物转折", ["决定", "不再", "终于", "改变", "答应", "拒绝", "离开"]),
    ("关系变化", ["相信", "怀疑", "背叛", "原谅", "误会", "合作", "分开"]),
    ("关键决定", ["必须", "不能", "要去", "留下", "救", "走", "选择"]),
    ("情感爆发", ["哭", "流泪", "崩溃", "对不起", "委屈", "恨", "爱"]),
    ("阴谋推进", ["计划", "安排", "利用", "陷害", "坐收渔利", "密令"]),
]


def guess_plot(text: str) -> str:
    for name, keys in PLOT_RULES:
        if any(k in text for k in keys):
            return name
    return "弱过渡" if len(text) < 20 else "发展"


def score_item(item: Dict[str, Any]):
    text = item_text(item)
    s, e = start_end(item)
    duration = max(0.0, e - s)
    plot = item.get("plot_function") or guess_plot(text)
    item["plot_function"] = plot
    reasons = []

    if plot in {"冲突升级", "反转", "高潮", "结局收束"}:
        story = 0.95
        reasons.append(f"强剧情功能:{plot}")
    elif plot in {"信息揭露", "阴谋推进", "关键决定", "人物转折", "关系变化"}:
        story = 0.82
        reasons.append(f"剧情推进:{plot}")
    elif plot in {"发展", "铺垫"}:
        story = 0.48
        reasons.append(f"主线铺垫:{plot}")
    else:
        story = 0.18
        reasons.append("弱过渡或低信息片段")

    info_tags = [k for k in ["真相", "秘密", "身份", "计划", "证据", "误会", "背叛", "陷害"] if k in text]
    emotion_tags = [k for k in ["哭", "流泪", "恨", "对不起", "怕", "崩溃", "紧张"] if k in text]

    char = 0.10
    if re.findall(r"[\u4e00-\u9fa5]{2,4}", text[:160]):
        char += 0.20
        reasons.append("存在人物线索")
    if any(k in text for k in ["决定", "相信", "怀疑", "背叛", "原谅", "离开", "留下"]):
        char += 0.30
        reasons.append("人物关系或目标变化")
    char = min(char, 1.0)

    info = 0.85 if info_tags else 0.05
    emotion = 0.78 if emotion_tags else 0.05
    visual = 0.25 if item.get("boundary_confidence") == "high" else 0.08
    continuity = 0.70 if plot in {"信息揭露", "冲突升级", "人物转折", "关键决定", "情感爆发", "阴谋推进"} else 0.45
    audio = 0.35 if plot in {"情感爆发", "冲突升级"} else 0.05

    penalty = 0.0
    if plot == "弱过渡":
        penalty += 0.12
        reasons.append("弱过渡扣分")
    if duration < cfg_float("movie_story_short_segment_penalty_seconds", 7.0) and not info_tags and not emotion_tags and story < 0.8:
        penalty += 0.18
        reasons.append("短片段且缺少强信息/强情绪扣分")
    if len(text.strip()) < 12 and story < 0.8:
        penalty += 0.10
        reasons.append("文本信息过少扣分")

    score = max(0.0, min(1.0, 0.25 * story + 0.20 * char + 0.15 * info + 0.15 * emotion + 0.10 * visual + 0.10 * continuity + 0.05 * audio - penalty))
    if info_tags:
        reasons.append("存在信息增量:" + ",".join(info_tags[:4]))
    if emotion_tags:
        reasons.append("存在情绪变化:" + ",".join(emotion_tags[:4]))

    return {
        "story_score": round(story, 3),
        "character_score": round(char, 3),
        "information_score": round(info, 3),
        "emotion_score": round(emotion, 3),
        "visual_score": round(visual, 3),
        "audio_score": round(audio, 3),
        "continuity_score": round(continuity, 3),
        "penalty": round(penalty, 3),
        "highlight_score": round(score, 3),
    }, reasons


# =========================
# exposed functions
# =========================

def build_authoritative_plot_chunks(segments, *args, **kwargs):
    global _LAST_VIDEO_PATH, _LAST_OUTPUT_PATH

    video_path = kwargs.get("video_path") or resolve_video_path(kwargs)
    output_path = kwargs.get("output_script_path") or resolve_output_path(kwargs)
    movie_story_chain = _movie_story_chain_from_kwargs(kwargs)
    _LAST_VIDEO_PATH = video_path or _LAST_VIDEO_PATH
    _LAST_OUTPUT_PATH = output_path or _LAST_OUTPUT_PATH

    audit_stage("00_active_movie_story_runtime", [{
        "candidate_id": "active_runtime_audio_protected_timeline",
        "candidate_type": "runtime_marker",
        "video_start": 0.0,
        "video_end": 0.001,
        "subtitle_text": f"ACTIVE_RUNTIME=timeline_runtime; movie_story_chain={movie_story_chain}; audio/subtitle protected timeline; no boundary_score.",
        "movie_story_chain": movie_story_chain,
        "highlight_score": 1.0,
        "score": 1.0,
        "selected": True,
    }], video_path, output_path, export_clips=False)

    shots, meta = build_shots(segments, video_path, output_path, kwargs.get("visual_mode", "auto"))
    audit_stage("01_shot_candidates", shots, video_path, output_path, meta)
    _audit_success_judgement_video_stage(
        "01a_shot_boundary_video_samples",
        _diagnostic_representative_sample(shots, max_count=cfg_int("movie_story_diagnostic_01_samples", 20)),
        video_path,
        output_path,
        {"source": "01_shot_candidates", "review_goal": "judge_boundary_and_coverage_quality"},
        max_count=cfg_int("movie_story_diagnostic_01_samples", 20),
    )

    scenes = merge_shots_to_scenes(shots)
    audit_stage("02_scene_candidates", scenes, video_path, output_path, {"source": "audio_protected_timeline"})

    if movie_story_chain == "native_runtime":
        _audit_three_stage_closure_after_scene_candidates(
            scenes,
            segments,
            video_path,
            output_path,
            target_minutes=_target_minutes_from_runtime_kwargs(kwargs),
            highlight_selectivity=str(kwargs.get("highlight_selectivity") or selectivity("balanced")),
            narrative_strategy=str(kwargs.get("narrative_strategy") or "mixed"),
        )
    chunks = []
    for idx, item in enumerate(scenes, start=1):
        s, e = start_end(item)
        seg_id = f"plot_{idx:03d}"
        cur = dict(item)
        cur.update({
            "segment_id": seg_id,
            "scene_id": seg_id,
            "candidate_id": item.get("candidate_id") or seg_id,
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "duration": round(e - s, 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
        })
        chunks.append(cur)

    logger.warning("movie_story timeline_runtime: shots=%s scenes=%s returned=%s", len(shots), len(scenes), len(chunks))
    return chunks


def select_story_highlights(scene_evidence, segments=None, video_path="", output_script_path="", target_minutes=8, highlight_selectivity="balanced"):
    video_path = video_path or _LAST_VIDEO_PATH or resolve_video_path({})
    output_script_path = output_script_path or _LAST_OUTPUT_PATH or resolve_output_path({})
    mode = selectivity(highlight_selectivity)

    scored = []
    for idx, item in enumerate(scene_evidence or [], start=1):
        cur = dict(item)
        cur.setdefault("candidate_id", cur.get("segment_id") or cur.get("scene_id") or f"candidate_{idx:04d}")
        cur.setdefault("video_start", cur.get("start", cur.get("semantic_start", 0.0)))
        cur.setdefault("video_end", cur.get("end", cur.get("semantic_end", cur.get("video_start", 0.0))))
        cur.setdefault("subtitle_text", cur.get("subtitle_text") or cur.get("source_text") or cur.get("main_text_evidence") or "")
        s, e = start_end(cur)
        if e <= s:
            continue
        scores, reasons = score_item(cur)
        cur["scores"] = scores
        cur["highlight_score"] = scores.get("highlight_score")
        cur["score"] = scores.get("highlight_score")
        cur["selection_reasons"] = reasons
        cur["selected"] = False
        cur["drop_reason"] = ""
        scored.append(cur)

    if mode == "loose":
        threshold = cfg_float("movie_story_loose_threshold", 0.34)
        cap = cfg_int("movie_story_loose_max_keep_count", 500)
    elif mode == "strict":
        threshold = cfg_float("movie_story_strict_threshold", 0.68)
        cap = cfg_int("movie_story_strict_max_keep_count", 35)
    elif mode == "balanced":
        threshold = cfg_float("movie_story_balanced_threshold", 0.48)
        cap = cfg_int("movie_story_balanced_max_keep_count", 60)
    else:
        threshold = cfg_float("movie_story_very_loose_threshold", 0.18)
        cap = cfg_int("movie_story_very_loose_max_keep_count", 560)

    candidates = [x for x in scored if float(x.get("highlight_score") or 0.0) >= threshold]
    ranked = sorted(scored, key=lambda x: (-float(x.get("highlight_score") or 0.0), float(x.get("video_start") or 0.0)))

    if mode == "loose":
        min_keep = min(cap, max(1, int(len(scored) * cfg_float("movie_story_loose_min_keep_ratio", 0.35))))
        selected = {id(x): x for x in candidates}
        for row in ranked:
            if len(selected) >= min_keep:
                break
            selected[id(row)] = row
        candidates = list(selected.values())

    if len(candidates) > cap:
        candidates = sorted(candidates, key=lambda x: (-float(x.get("highlight_score") or 0.0), float(x.get("video_start") or 0.0)))[:cap]

    ids = {id(x) for x in candidates}
    for row in scored:
        if id(row) in ids:
            row["selected"] = True
        else:
            row["drop_reason"] = f"score_below_{threshold}_or_over_cap_{cap}"

    audit_stage("04a_scored_candidates", scored, video_path, output_script_path, {"mode": mode, "threshold": threshold, "cap": cap}, export_clips=False)

    candidates.sort(key=lambda x: float(x.get("video_start") or 0.0))
    highlights = []
    for idx, src in enumerate(candidates, start=1):
        s, e = start_end(src)
        seg_id = src.get("segment_id") or src.get("candidate_id") or f"plot_{idx:03d}"
        scores = src.get("scores") or {}
        highlights.append({
            "highlight_id": f"highlight_{idx:03d}",
            "highlight_rank": idx,
            "scene_ids": [src.get("scene_id") or seg_id],
            "segment_ids": [seg_id],
            "evidence_ids": [seg_id],
            "plot_functions": [src.get("plot_function")] if src.get("plot_function") else [],
            "highlight_reasons": src.get("selection_reasons") or [],
            "highlight_score": scores.get("highlight_score", 0.0),
            "score": scores.get("highlight_score", 0.0),
            "semantic_start": s,
            "semantic_end": e,
            "semantic_duration": round(e - s, 3),
            "semantic_timestamp": f"{fmt(s)}-{fmt(e)}",
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "duration": round(e - s, 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
            "source_text": src.get("subtitle_text") or src.get("source_text") or "",
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
            "highlight_selectivity": mode,
            "scores": scores,
            "selected": True,
            "stage3_policy": "direct_audio_protected_timeline",
        })

    audit_stage("05_selected_highlights", highlights, video_path, output_script_path, {"mode": mode, "selected": len(highlights)})
    return highlights
