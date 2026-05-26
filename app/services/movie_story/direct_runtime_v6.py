
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
movie_story direct_runtime_v6

经验记录：
- v4 约 455 个候选：0.45s 弱字幕边界 + ffmpeg scene threshold=0.30 + min=4s，结果过碎，且 loose 几乎全保留。
- v5 约 431 个候选：删除弱字幕边界、提高 min/max 和阈值后仍很多，说明边界主要来自 ffmpeg shot changes。
- 结论：431/455 更应命名为 shot_candidates，而不是最终 scene_candidates。
- v6 目标：先保留 shot 边界，再合并成 scene 段，另审计 draft story 段；高光选择运行在 scene 上。
"""

import csv
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from app.services.movie_story import direct_runtime_v5 as v5


def cfg(key: str, default=None):
    return v5.cfg(key, default)


def cfg_float(key: str, default: float) -> float:
    return v5.cfg_float(key, default)


def cfg_int(key: str, default: int) -> int:
    return v5.cfg_int(key, default)


def cfg_bool(key: str, default: bool = False) -> bool:
    return v5.cfg_bool(key, default)


def selectivity(fallback: str = "balanced") -> str:
    return v5.selectivity(fallback)


def fmt_time(seconds: float) -> str:
    return v5.fmt_time(seconds)


def safe_id(value: Any) -> str:
    return v5.safe_id(value)


def resolve_video_path(kwargs=None) -> str:
    return v5.resolve_video_path(kwargs or {})


def resolve_output_script_path(kwargs=None) -> str:
    return v5.resolve_output_script_path(kwargs or {})


def _text(item: Dict[str, Any]) -> str:
    return str(item.get("subtitle_text") or item.get("source_text") or item.get("main_text_evidence") or "")


def _boundary_reasons(item: Dict[str, Any]) -> List[str]:
    reasons = []
    for k in ("boundary_start_reason", "boundary_end_reason"):
        v = item.get(k) or []
        if isinstance(v, list):
            reasons.extend(v)
        elif v:
            reasons.append(str(v))
    return reasons


def _transition_word(text: str) -> bool:
    markers = ["第二天", "与此同时", "另一边", "回到", "几天后", "随后", "转眼", "第二日", "次日"]
    return any(m in text for m in markers)


def audit_stage(video_path: str, output_script_path: str, stage: str, items: List[Dict[str, Any]], metadata=None):
    """v6 审计：导出 JSON/CSV/可选 clips；评分表会展开各维度。"""
    try:
        root = Path(output_script_path).parent / "_movie_story_direct_v6_audit" if output_script_path else Path(".-workspace") / "debug" / "_movie_story_direct_v6_audit"
        run_id = os.environ.get("AIVIDEO_AUDIT_RUN_ID") or time.strftime("run_%Y%m%d_%H%M%S")
        os.environ["AIVIDEO_AUDIT_RUN_ID"] = run_id
        run_dir = root / run_id
        stage_dir = run_dir / ("".join(c if c.isalnum() or c in "._-" else "_" for c in stage)[:120])
        clips_dir = stage_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        keep = cfg_int("movie_story_audit_keep_runs", 2)
        if root.exists():
            runs = [p for p in root.glob("run_*") if p.is_dir()]
            runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for old in runs[keep:]:
                shutil.rmtree(old, ignore_errors=True)

        export = cfg_bool("movie_story_audit_export_clips", True)
        max_n = cfg_int("movie_story_audit_max_clips_per_stage", 180)
        rows = []
        exported = 0
        total = 0.0

        for idx, item in enumerate(items or [], start=1):
            s = float(item.get("video_start", item.get("start", 0.0)) or 0.0)
            e = float(item.get("video_end", item.get("end", s)) or s)
            dur = max(0.0, e - s)
            total += dur
            scores = item.get("scores") or {}
            children = item.get("children") or item.get("source_shot_ids") or item.get("source_scene_ids") or []
            row = {
                "idx": idx,
                "id": item.get("candidate_id") or item.get("highlight_id") or item.get("segment_id") or idx,
                "selected": item.get("selected"),
                "drop_reason": item.get("drop_reason"),
                "video_start": s,
                "video_end": e,
                "duration": round(dur, 3),
                "children_count": len(children),
                "plot_function": item.get("plot_function"),
                "story_score": scores.get("story_score", item.get("story_score")),
                "character_score": scores.get("character_score", item.get("character_score")),
                "information_score": scores.get("information_score", item.get("information_score")),
                "emotion_score": scores.get("emotion_score", item.get("emotion_score")),
                "visual_score": scores.get("visual_score", item.get("visual_score")),
                "audio_score": scores.get("audio_score", item.get("audio_score")),
                "continuity_score": scores.get("continuity_score", item.get("continuity_score")),
                "penalty": scores.get("penalty", item.get("penalty")),
                "highlight_score": scores.get("highlight_score", item.get("highlight_score")),
                "selection_reasons": json.dumps(item.get("selection_reasons") or item.get("highlight_reasons") or [], ensure_ascii=False),
                "text": _text(item)[:300],
            }

            if export and video_path and Path(video_path).exists() and idx <= max_n and e > s:
                clip = clips_dir / f"{idx:03d}_{safe_id(row['id'])}_{s:.3f}_{e:.3f}.mp4"
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{s:.3f}", "-i", video_path, "-t", f"{dur:.3f}",
                    "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "25", "-c:a", "aac",
                    "-b:a", "96k", "-movflags", "+faststart", str(clip),
                ]
                try:
                    import subprocess
                    ok = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=max(30, int(dur) + 30)).returncode == 0
                except Exception:
                    ok = False
                row["clip_path"] = str(clip)
                row["exported"] = ok
                exported += 1 if ok else 0
            rows.append(row)

        manifest = {"stage": stage, "count": len(items), "exported": exported, "total_duration": round(total, 3), "metadata": metadata or {}, "items": rows}
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if rows:
            with (stage_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

        index_path = run_dir / "_stage_index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        except Exception:
            index = []
        index.append({"stage": stage, "dir": str(stage_dir), "count": len(items), "exported": exported, "total_duration": round(total, 3)})
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning("movie_story v6 audit: stage=%s count=%s exported=%s dir=%s", stage, len(items), exported, stage_dir)
    except Exception as exc:
        logger.warning("movie_story v6 audit failed: stage=%s error=%s", stage, exc)


def _should_merge_shot(current: List[Dict[str, Any]], shot: Dict[str, Any]) -> bool:
    """shot -> scene：看时空连续性。ffmpeg_scene 只是镜头切换，通常允许合并。"""
    if not current:
        return True
    start = float(current[0].get("video_start", current[0].get("start", 0.0)) or 0.0)
    cur_end = float(current[-1].get("video_end", current[-1].get("end", start)) or start)
    shot_start = float(shot.get("video_start", shot.get("start", 0.0)) or 0.0)
    shot_end = float(shot.get("video_end", shot.get("end", shot_start)) or shot_start)

    cur_dur = max(0.0, cur_end - start)
    after_dur = max(0.0, shot_end - start)
    gap = max(0.0, shot_start - cur_end)

    min_scene = cfg_float("movie_story_scene_merge_min_seconds", 18.0)
    target_scene = cfg_float("movie_story_scene_merge_target_seconds", 35.0)
    max_scene = cfg_float("movie_story_scene_merge_max_seconds", 75.0)

    if after_dur > max_scene:
        return False
    if cur_dur < min_scene:
        return True

    reasons = _boundary_reasons(shot)
    text = _text(shot)

    # subtitle_gap / video_boundary 更像自然场景断点；ffmpeg_scene 只是 shot 边界，不单独断 scene。
    if ("subtitle_gap" in reasons or "video_boundary" in reasons) and cur_dur >= min_scene:
        return False
    if _transition_word(text) and cur_dur >= min_scene:
        return False
    if cur_dur >= target_scene:
        return False
    if gap > cfg_float("movie_story_scene_merge_max_gap", 2.0) and cur_dur >= min_scene:
        return False
    return True


def merge_shots_to_scene_candidates(shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scenes = []
    buf: List[Dict[str, Any]] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        idx = len(scenes) + 1
        s = float(buf[0].get("video_start", buf[0].get("start", 0.0)) or 0.0)
        e = float(buf[-1].get("video_end", buf[-1].get("end", s)) or s)
        text = " ".join(_text(x) for x in buf if _text(x)).strip()
        children = [x.get("candidate_id") or x.get("segment_id") for x in buf]
        scenes.append({
            "candidate_id": f"scene_{idx:04d}",
            "candidate_type": "scene",
            "video_start": round(s, 3),
            "video_end": round(e, 3),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e - s, 3),
            "subtitle_text": text,
            "source_text": text,
            "main_text_evidence": text,
            "source_shot_ids": children,
            "children": children,
            "boundary_start_reason": buf[0].get("boundary_start_reason") or [],
            "boundary_end_reason": buf[-1].get("boundary_end_reason") or [],
            "merge_policy": "shot_to_scene_v6_time_boundary_dialogue_continuity",
            "stage1_policy": "movie_story_direct_v6_scene_candidates_from_shots",
        })
        buf = []

    for shot in shots or []:
        if not buf:
            buf.append(shot)
        elif _should_merge_shot(buf, shot):
            buf.append(shot)
        else:
            flush()
            buf.append(shot)
    flush()
    return scenes


def _should_merge_scene_to_story(current: List[Dict[str, Any]], scene: Dict[str, Any]) -> bool:
    """scene -> story：看事件连续性。当前是草稿规则，主要用于审计，后续可接 LLM。"""
    if not current:
        return True
    start = float(current[0].get("video_start", 0.0) or 0.0)
    cur_end = float(current[-1].get("video_end", start) or start)
    scene_end = float(scene.get("video_end", cur_end) or cur_end)
    cur_dur = cur_end - start
    after_dur = scene_end - start
    if after_dur > cfg_float("movie_story_story_merge_max_seconds", 150.0):
        return False
    if cur_dur < cfg_float("movie_story_story_merge_min_seconds", 45.0):
        return True
    if _transition_word(_text(scene)):
        return False
    plot = v5.guess_plot(_text(scene)) if hasattr(v5, "guess_plot") else ""
    if plot in {"信息揭露", "冲突升级", "人物转折", "关键决定", "情感爆发", "阴谋推进"} and cur_dur >= 45:
        return False
    if cur_dur >= cfg_float("movie_story_story_merge_target_seconds", 90.0):
        return False
    return True


def merge_scenes_to_story_candidates(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stories = []
    buf: List[Dict[str, Any]] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        idx = len(stories) + 1
        s = float(buf[0].get("video_start", 0.0) or 0.0)
        e = float(buf[-1].get("video_end", s) or s)
        text = " ".join(_text(x) for x in buf if _text(x)).strip()
        children = [x.get("candidate_id") for x in buf]
        stories.append({
            "candidate_id": f"story_{idx:04d}",
            "candidate_type": "draft_story",
            "video_start": round(s, 3),
            "video_end": round(e, 3),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e - s, 3),
            "subtitle_text": text,
            "source_text": text,
            "main_text_evidence": text,
            "source_scene_ids": children,
            "children": children,
            "merge_policy": "scene_to_story_v6_event_continuity_draft_only",
        })
        buf = []

    for scene in scenes or []:
        if not buf:
            buf.append(scene)
        elif _should_merge_scene_to_story(buf, scene):
            buf.append(scene)
        else:
            flush()
            buf.append(scene)
    flush()
    return stories


def build_plot_chunks_v6(segments, *args, **kwargs):
    """返回 scene candidates 给旧后半段；shot/story 只用于审计。"""
    video_path = kwargs.get("video_path") or resolve_video_path(kwargs)
    output_script_path = kwargs.get("output_script_path") or resolve_output_script_path(kwargs)

    shot_candidates = v5.build_plot_chunks_v5(segments, *args, **kwargs)
    for idx, shot in enumerate(shot_candidates, start=1):
        shot["candidate_id"] = shot.get("candidate_id") or f"shot_{idx:04d}"
        shot["candidate_type"] = "shot"

    audit_stage(video_path, output_script_path, "01_shot_candidates_v6", shot_candidates, {
        "experience": "v4/v5 431-455 candidates are shot-level boundaries, not final scene segments"
    })

    scene_candidates = merge_shots_to_scene_candidates(shot_candidates)
    audit_stage(video_path, output_script_path, "02_scene_candidates_v6", scene_candidates, {
        "policy": "merge adjacent shots by temporal continuity, boundary reasons and duration limits"
    })

    story_candidates = merge_scenes_to_story_candidates(scene_candidates)
    audit_stage(video_path, output_script_path, "03_story_candidates_v6", story_candidates, {
        "policy": "draft story candidates for audit only; highlighter still uses scene candidates"
    })

    chunks = []
    for idx, item in enumerate(scene_candidates, start=1):
        s = float(item["video_start"])
        e = float(item["video_end"])
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
            "timestamp": f"{fmt_time(s)}-{fmt_time(e)}",
        })
        chunks.append(cur)

    logger.warning("movie_story direct v6 stage1: shots=%s scenes=%s stories=%s returned_chunks=%s", len(shot_candidates), len(scene_candidates), len(story_candidates), len(chunks))
    return chunks


def select_story_highlights_v6(scene_evidence, segments=None, video_path="", output_script_path="", target_minutes=8, highlight_selectivity="balanced"):
    video_path = video_path or resolve_video_path({})
    output_script_path = output_script_path or resolve_output_script_path({})
    mode = selectivity(highlight_selectivity)

    evidence = []
    for idx, item in enumerate(scene_evidence or [], start=1):
        cur = dict(item)
        cur.setdefault("candidate_id", cur.get("segment_id") or cur.get("scene_id") or f"candidate_{idx:04d}")
        cur.setdefault("video_start", cur.get("start", cur.get("semantic_start", 0.0)))
        cur.setdefault("video_end", cur.get("end", cur.get("semantic_end", cur.get("video_start", 0.0))))
        cur.setdefault("subtitle_text", cur.get("subtitle_text") or cur.get("source_text") or cur.get("main_text_evidence") or "")
        evidence.append(cur)

    scored_rows = []
    for item in evidence:
        s = float(item.get("video_start", 0.0) or 0.0)
        e = float(item.get("video_end", s) or s)
        if e <= s:
            continue
        scores, reasons = v5.score_item(item)
        row = dict(item)
        row["scores"] = scores
        row["highlight_score"] = scores["highlight_score"]
        row["selection_reasons"] = reasons
        row["selected"] = False
        row["drop_reason"] = ""
        scored_rows.append(row)

    if mode == "strict":
        threshold = cfg_float("movie_story_strict_threshold", 0.68)
        cap_count = cfg_int("movie_story_strict_max_keep_count", 35)
    elif mode == "balanced":
        threshold = cfg_float("movie_story_balanced_threshold", 0.48)
        cap_count = cfg_int("movie_story_balanced_max_keep_count", 60)
    elif mode == "loose":
        threshold = cfg_float("movie_story_loose_threshold", 0.34)
        cap_count = cfg_int("movie_story_loose_max_keep_count", 90)
    else:
        threshold = cfg_float("movie_story_very_loose_threshold", 0.18)
        cap_count = cfg_int("movie_story_very_loose_max_keep_count", 160)

    candidates = [x for x in scored_rows if float(x.get("highlight_score", 0.0) or 0.0) >= threshold]
    ranked_all = sorted(scored_rows, key=lambda x: (-float(x.get("highlight_score", 0.0) or 0.0), float(x.get("video_start", 0.0) or 0.0)))

    if mode == "loose":
        min_keep = min(cap_count, max(1, int(len(scored_rows) * cfg_float("movie_story_loose_min_keep_ratio", 0.35))))
        selected_map = {id(x): x for x in candidates}
        for row in ranked_all:
            if len(selected_map) >= min_keep:
                break
            selected_map[id(row)] = row
        candidates = list(selected_map.values())

    if len(candidates) > cap_count:
        candidates = sorted(candidates, key=lambda x: (-float(x.get("highlight_score", 0.0) or 0.0), float(x.get("video_start", 0.0) or 0.0)))[:cap_count]

    selected_ids = {id(x) for x in candidates}
    for row in scored_rows:
        if id(row) in selected_ids:
            row["selected"] = True
        else:
            row["drop_reason"] = f"score_below_{threshold}_or_over_cap_{cap_count}"

    audit_stage(video_path, output_script_path, "04a_scored_candidates_v6", scored_rows, {
        "mode": mode, "threshold": threshold, "cap_count": cap_count,
        "note": "score table exported for threshold maintenance"
    })

    candidates.sort(key=lambda x: float(x.get("video_start", 0.0)))
    highlights = []
    for idx, src in enumerate(candidates, start=1):
        s = float(src.get("video_start", 0.0) or 0.0)
        e = float(src.get("video_end", s) or s)
        seg_id = src.get("segment_id") or src.get("candidate_id") or f"plot_{idx:03d}"
        scores = src.get("scores") or {}
        reasons = src.get("selection_reasons") or []
        highlights.append({
            "highlight_id": f"highlight_{idx:03d}",
            "highlight_rank": idx,
            "scene_ids": [src.get("scene_id") or seg_id],
            "segment_ids": [seg_id],
            "evidence_ids": [seg_id],
            "plot_functions": [src.get("plot_function")] if src.get("plot_function") else [],
            "highlight_reasons": reasons,
            "highlight_score": scores.get("highlight_score", 0.0),
            "importance_level": src.get("importance_level", "medium"),
            "boundary_confidence": src.get("boundary_confidence", "medium"),
            "raw_voice_retain": src.get("plot_function") in {"情感爆发", "冲突升级"},
            "semantic_start": s,
            "semantic_end": e,
            "semantic_duration": round(e - s, 3),
            "semantic_timestamp": f"{fmt_time(s)}-{fmt_time(e)}",
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "duration": round(e - s, 3),
            "timestamp": f"{fmt_time(s)}-{fmt_time(e)}",
            "source_text": src.get("subtitle_text") or src.get("source_text") or "",
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
            "highlight_selectivity": mode,
            "scores": scores,
            "selected": True,
            "stage3_policy": "movie_story_direct_v6_scene_level_score_selection",
        })

    audit_stage(video_path, output_script_path, "05_selected_highlights_v6", highlights, {
        "mode": mode, "input": len(evidence), "selected": len(highlights), "threshold": threshold
    })
    logger.warning("movie_story direct v6 stage3: mode=%s input=%s selected=%s", mode, len(evidence), len(highlights))
    return highlights
