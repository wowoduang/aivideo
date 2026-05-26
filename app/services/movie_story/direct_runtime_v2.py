
# -*- coding: utf-8 -*-
from __future__ import annotations
import csv, json, logging, os, re, shutil, subprocess, time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _cfg(key: str, default=None):
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


def selectivity_v2(fallback: str = "balanced") -> str:
    value = os.environ.get("AIVIDEO_HIGHLIGHT_SELECTIVITY") or os.environ.get("MOVIE_STORY_HIGHLIGHT_SELECTIVITY") or str(_cfg("movie_story_highlight_selectivity", "") or "") or fallback
    value = str(value or "balanced").strip().lower()
    aliases = {"宽松": "loose", "较宽松": "loose", "很宽松": "very_loose", "严格": "strict", "均衡": "balanced", "默认": "balanced", "normal": "balanced", "medium": "balanced"}
    value = aliases.get(value, value)
    return value if value in {"strict", "balanced", "loose", "very_loose"} else "balanced"


def _parse_time(value: Any) -> Optional[float]:
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


def _fmt(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def _safe_id(text: Any) -> str:
    return str(text or "segment").replace("/", "_").replace("\\", "_")[:50]


def _subtitle_units(segments: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    units = []
    for idx, seg in enumerate(segments or [], start=1):
        start = _parse_time(seg.get("start") or seg.get("begin") or seg.get("from"))
        end = _parse_time(seg.get("end") or seg.get("to") or seg.get("finish"))
        if (start is None or end is None) and seg.get("timestamp") and "-" in str(seg.get("timestamp")):
            left, right = str(seg.get("timestamp")).split("-", 1)
            start, end = _parse_time(left), _parse_time(right)
        if start is None or end is None:
            continue
        if end <= start:
            end = start + 0.3
        units.append({"unit_id": f"sub_{idx:05d}", "start": round(float(start), 3), "end": round(float(end), 3), "text": str(seg.get("text") or seg.get("content") or seg.get("subtitle") or "").strip()})
    units.sort(key=lambda x: (x["start"], x["end"]))
    cleaned = []
    for u in units:
        if cleaned and u["text"] and cleaned[-1]["text"] == u["text"] and u["start"] - cleaned[-1]["end"] <= 0.8:
            cleaned[-1]["end"] = max(cleaned[-1]["end"], u["end"])
        else:
            cleaned.append(u)
    return cleaned


def _subtitle_boundaries(units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for prev, cur in zip(units, units[1:]):
        gap = cur["start"] - prev["end"]
        if gap >= 2.5:
            strength = "strong"
        elif gap >= 1.2:
            strength = "medium"
        elif re.search(r"[。！？!?]$", prev.get("text") or "") and gap >= 0.5:
            strength = "weak"
        else:
            continue
        out.append({"time": round((prev["end"] + cur["start"]) / 2, 3), "strength": strength, "reason": ["subtitle_gap"], "gap": round(gap, 3)})
    return out


def _normalize_external_boundaries(items: Iterable[Any], reason: str) -> List[Dict[str, Any]]:
    out = []
    for item in items or []:
        if isinstance(item, dict):
            t = _parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
            strength = str(item.get("strength") or "medium")
            reasons = list(item.get("reason") or item.get("reasons") or [reason])
        else:
            t, strength, reasons = _parse_time(item), "medium", [reason]
        if t is not None:
            out.append({"time": round(t, 3), "strength": strength, "reason": reasons})
    return out


def _fuse_boundaries(subtitle_boundaries, video_boundaries, *, story_start: float, story_end: float) -> List[Dict[str, Any]]:
    raw = []
    raw.extend(subtitle_boundaries or [])
    raw.extend(_normalize_external_boundaries(video_boundaries or [], "video_boundary"))
    raw = [x for x in raw if story_start < float(x["time"]) < story_end]
    raw.sort(key=lambda x: float(x["time"]))
    fused, cluster = [], []
    def flush():
        if not cluster:
            return
        times = [float(x["time"]) for x in cluster]
        reasons, strength_score = [], 0
        for x in cluster:
            reasons.extend(x.get("reason") or [])
            strength_score += {"weak": 1, "medium": 2, "strong": 3}.get(str(x.get("strength") or "medium"), 2)
        fused.append({"time": round(sum(times) / len(times), 3), "strength": "strong" if strength_score >= 4 or len(cluster) >= 2 else "medium", "reason": sorted(set(reasons))})
    for b in raw:
        if not cluster or abs(float(b["time"]) - float(cluster[-1]["time"])) <= 1.0:
            cluster.append(b)
        else:
            flush(); cluster = [b]
    flush()
    return fused


def _text_between(units: List[Dict[str, Any]], start: float, end: float):
    chosen = [u for u in units if u["end"] > start and u["start"] < end]
    if not chosen:
        return "", None, None
    return " ".join(u["text"] for u in chosen if u["text"]).strip(), chosen[0]["start"], chosen[-1]["end"]


def _boundary_reason(boundaries, t: float):
    near = [b for b in boundaries if abs(float(b["time"]) - float(t)) <= 1.2]
    reasons = []
    for b in near:
        reasons.extend(b.get("reason") or [])
    return sorted(set(reasons)) or ["duration_limit"]


def _build_scene_candidates(units, boundaries, story_start: float, story_end: float):
    cuts = [story_start] + [float(b["time"]) for b in boundaries if story_start < float(b["time"]) < story_end] + [story_end]
    cuts = sorted(set(round(x, 3) for x in cuts))
    ranges = []
    for i in range(len(cuts) - 1):
        s, e = cuts[i], cuts[i + 1]
        if e > s:
            ranges.append((s, e, _boundary_reason(boundaries, s), _boundary_reason(boundaries, e)))
    normalized = []
    min_d, target_min, target_max, max_d = 8.0, 15.0, 45.0, 75.0
    for s, e, rs, re in ranges:
        if normalized and e - s < min_d:
            ps, pe, prs, pre = normalized.pop()
            normalized.append((ps, e, prs, re)); continue
        if e - s > max_d:
            current = s
            while e - current > max_d:
                cands = [float(b["time"]) for b in boundaries if current + target_min <= float(b["time"]) <= current + max_d]
                cut = min(cands, key=lambda x: abs(x - (current + target_max))) if cands else current + target_max
                normalized.append((current, cut, rs, ["long_segment_split"]))
                current = cut
            if e - current >= min_d:
                normalized.append((current, e, ["long_segment_split"], re))
            elif normalized:
                ps, pe, prs, pre = normalized.pop()
                normalized.append((ps, e, prs, re))
            continue
        normalized.append((s, e, rs, re))
    scenes = []
    for idx, (s, e, rs, re) in enumerate(normalized, start=1):
        text, sub_s, sub_e = _text_between(units, s, e)
        scenes.append({"candidate_id": f"scene_{idx:04d}", "candidate_type": "scene", "video_start": round(s, 3), "video_end": round(e, 3), "start": round(s, 3), "end": round(e, 3), "duration": round(e - s, 3), "subtitle_start": sub_s, "subtitle_end": sub_e, "subtitle_text": text, "boundary_start_reason": rs, "boundary_end_reason": re, "boundary_confidence": "high" if "subtitle_gap" in (rs + re) else "medium", "source_scene_ids": [f"scene_{idx:04d}"], "need_semantic_review": True})
    return scenes


def _build_draft_stories(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stories, buf = [], []
    def flush():
        nonlocal buf
        if not buf:
            return
        s, e = buf[0]["video_start"], buf[-1]["video_end"]
        idx = len(stories) + 1
        stories.append({"candidate_id": f"story_{idx:04d}", "candidate_type": "draft_story", "video_start": s, "video_end": e, "start": s, "end": e, "duration": round(e - s, 3), "children": [x["candidate_id"] for x in buf], "subtitle_text": " ".join(x.get("subtitle_text") or "" for x in buf).strip(), "merge_reason": ["time_continuity", "scene_merge"] if len(buf) > 1 else ["single_scene"], "boundary_confidence": "medium", "need_semantic_review": True})
        buf = []
    for sc in scenes:
        if not buf:
            buf.append(sc); continue
        cur_duration = sc["video_end"] - buf[0]["video_start"]
        gap = sc["video_start"] - buf[-1]["video_end"]
        strong_break = "video_boundary" in (sc.get("boundary_start_reason") or []) and gap >= 1.5
        if cur_duration <= 120.0 and not strong_break:
            buf.append(sc)
        elif buf[-1]["video_end"] - buf[0]["video_start"] < 45.0 and cur_duration <= 180.0:
            buf.append(sc)
        else:
            flush(); buf.append(sc)
    flush()
    return stories


def _audit_enabled() -> bool:
    return str(_cfg("movie_story_audit_export_clips", "true")).strip().lower() not in {"0", "false", "no", "off"}


def _audit_export_clip(video_path: str, out: Path, start: float, end: float) -> bool:
    if not video_path or not Path(video_path).exists():
        return False
    dur = max(float(end) - float(start), 0.1)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{float(start):.3f}", "-i", video_path, "-t", f"{dur:.3f}", "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)]
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=max(30, int(dur) + 30)).returncode == 0
    except Exception:
        return False


def _audit_stage(video_path: str, output_script_path: str, stage: str, items: List[Dict[str, Any]], metadata=None):
    try:
        root = Path(output_script_path).parent / "_movie_story_direct_v2_audit" if output_script_path else Path(".-workspace") / "debug" / "_movie_story_direct_v2_audit"
        run_id = os.environ.get("AIVIDEO_AUDIT_RUN_ID") or time.strftime("run_%Y%m%d_%H%M%S")
        os.environ["AIVIDEO_AUDIT_RUN_ID"] = run_id
        run = root / run_id
        stage_dir = run / ("".join(c if c.isalnum() or c in "._-" else "_" for c in stage)[:120])
        clips = stage_dir / "clips"; clips.mkdir(parents=True, exist_ok=True)
        max_n = int(_cfg("movie_story_audit_max_clips_per_stage", 120) or 120)
        keep = int(_cfg("movie_story_audit_keep_runs", 2) or 2)
        if root.exists():
            runs = [p for p in root.glob("run_*") if p.is_dir()]
            runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for old in runs[keep:]: shutil.rmtree(old, ignore_errors=True)
        rows, exported, total = [], 0, 0.0
        for idx, item in enumerate(items or [], start=1):
            s = float(item.get("video_start", item.get("start", 0.0)) or 0.0)
            e = float(item.get("video_end", item.get("end", s)) or s)
            dur = max(0.0, e - s); total += dur
            row = {"idx": idx, "id": item.get("candidate_id") or item.get("highlight_id") or item.get("segment_id") or idx, "video_start": s, "video_end": e, "duration": round(dur, 3), "score": item.get("highlight_score") or (item.get("scores") or {}).get("highlight_score"), "text": str(item.get("subtitle_text") or item.get("source_text") or "")[:300]}
            if _audit_enabled() and idx <= max_n and e > s:
                path = clips / f"{idx:03d}_{_safe_id(row['id'])}_{s:.3f}_{e:.3f}.mp4"
                ok = _audit_export_clip(video_path, path, s, e)
                row["clip_path"] = str(path); row["exported"] = ok; exported += 1 if ok else 0
            rows.append(row)
        manifest = {"stage": stage, "count": len(items), "exported": exported, "total_duration": round(total, 3), "metadata": metadata or {}, "items": rows}
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if rows:
            with (stage_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys())); writer.writeheader(); writer.writerows(rows)
        index_path = run / "_stage_index.json"
        try: index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        except Exception: index = []
        index.append({"stage": stage, "dir": str(stage_dir), "count": len(items), "exported": exported, "total_duration": round(total, 3)})
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning("movie_story v2 audit: stage=%s count=%s exported=%s dir=%s", stage, len(items), exported, stage_dir)
    except Exception as exc:
        logger.warning("movie_story v2 audit failed: stage=%s error=%s", stage, exc)


def build_plot_chunks_v2(video_path, segments, full_subtitle_understanding=None, video_boundary_candidates=None, output_script_path=""):
    prologue_end = story_end = None
    if isinstance(full_subtitle_understanding, dict):
        prologue_end = _parse_time(full_subtitle_understanding.get("prologue_end_time"))
        story_end = _parse_time(full_subtitle_understanding.get("story_end_time"))
    units = _subtitle_units(segments)
    fallback_start, fallback_end = (units[0]["start"], units[-1]["end"]) if units else (0.0, 0.0)
    story_start = float(prologue_end) if prologue_end is not None else fallback_start
    final_end = float(story_end) if story_end is not None else fallback_end
    if final_end <= story_start: story_start, final_end = fallback_start, fallback_end
    boundaries = _fuse_boundaries(_subtitle_boundaries(units), video_boundary_candidates or [], story_start=story_start, story_end=final_end)
    scenes = _build_scene_candidates(units, boundaries, story_start, final_end)
    stories = _build_draft_stories(scenes) if str(_cfg("movie_story_segmentation_mode", "hybrid") or "hybrid") != "scene" else []
    _audit_stage(video_path, output_script_path, "01_scene_candidates", scenes, {"policy": "cut_all_no_filter"})
    _audit_stage(video_path, output_script_path, "02_draft_story_candidates", stories, {"policy": "structural_merge_no_filter"})
    source = stories if stories else scenes
    chunks = []
    for idx, item in enumerate(source, start=1):
        s = float(item.get("video_start", 0.0) or 0.0); e = float(item.get("video_end", s) or s)
        if e <= s: continue
        seg_id = f"plot_{idx:03d}"
        chunks.append({"segment_id": seg_id, "scene_id": seg_id, "candidate_id": item.get("candidate_id") or seg_id, "candidate_type": item.get("candidate_type") or "draft_story", "start": s, "end": e, "video_start": s, "video_end": e, "duration": round(e-s, 3), "timestamp": f"{_fmt(s)}-{_fmt(e)}", "subtitle_start": item.get("subtitle_start", s), "subtitle_end": item.get("subtitle_end", e), "subtitle_text": item.get("subtitle_text") or "", "main_text_evidence": item.get("subtitle_text") or "", "source_text": item.get("subtitle_text") or "", "boundary_confidence": item.get("boundary_confidence", "medium"), "merge_reason": item.get("merge_reason") or [], "source_scene_ids": item.get("children") or item.get("source_scene_ids") or [], "stage1_policy": "movie_story_direct_v2_cut_all_no_filter"})
    _audit_stage(video_path, output_script_path, "03_legacy_plot_chunks_for_old_pipeline", chunks, {"policy": "direct_v2_stage1"})
    logger.warning("movie_story direct v2 stage1: scenes=%s stories=%s chunks=%s", len(scenes), len(stories), len(chunks))
    return chunks


_PLOT_RULES = [("信息揭露", ["真相", "秘密", "原来", "知道", "发现", "告诉", "证据", "身份"]), ("冲突升级", ["吵", "打", "杀", "滚", "别逼", "你敢", "威胁", "报仇"]), ("人物转折", ["决定", "不再", "终于", "改变", "答应", "拒绝", "离开"]), ("关系变化", ["相信", "怀疑", "背叛", "原谅", "误会", "合作", "分开"]), ("关键决定", ["必须", "不能", "要去", "留下", "救", "走", "选择"]), ("情感爆发", ["哭", "流泪", "崩溃", "对不起", "委屈", "恨", "爱"]), ("阴谋推进", ["计划", "安排", "利用", "陷害", "坐收渔利", "密令"])]

def _plot_function(text: str) -> str:
    for name, keys in _PLOT_RULES:
        if any(k in text for k in keys): return name
    return "弱过渡" if len(text) < 20 else "发展"


def _score_segment(item: Dict[str, Any]):
    text = str(item.get("subtitle_text") or item.get("source_text") or item.get("main_text_evidence") or "")
    plot = item.get("plot_function") or _plot_function(text); item["plot_function"] = plot
    reasons = []
    story = 0.25
    if plot in {"冲突升级", "反转", "高潮", "结局收束"}: story = 0.95; reasons.append(f"强剧情功能:{plot}")
    elif plot in {"信息揭露", "阴谋推进", "关键决定", "人物转折", "关系变化"}: story = 0.82; reasons.append(f"剧情推进:{plot}")
    elif plot in {"发展", "铺垫"}: story = 0.48; reasons.append(f"主线铺垫:{plot}")
    info_tags = [k for k in ["真相", "秘密", "身份", "计划", "证据", "误会", "背叛", "陷害"] if k in text]
    emotion_tags = [k for k in ["哭", "流泪", "恨", "对不起", "怕", "崩溃", "紧张"] if k in text]
    char = 0.2 + (0.25 if re.findall(r"[\u4e00-\u9fa5]{2,4}", text[:120]) else 0.0)
    if any(k in text for k in ["决定", "相信", "怀疑", "背叛", "原谅", "离开", "留下"]): char += 0.25; reasons.append("人物关系或目标变化")
    char = min(char, 1.0)
    info = 0.85 if info_tags else 0.15
    emotion = 0.78 if emotion_tags else 0.15
    importance = item.get("importance_level") or ("high" if plot in {"信息揭露", "冲突升级", "人物转折", "关键决定", "情感爆发", "阴谋推进"} else "medium")
    continuity = 0.7 if importance == "high" else 0.55
    audio = 0.35 if plot in {"情感爆发", "冲突升级"} else 0.05
    highlight = max(0, min(1, 0.25*story + 0.2*char + 0.15*info + 0.15*emotion + 0.1*0.1 + 0.1*continuity + 0.05*audio))
    scores = {"story_score": round(story,3), "character_score": round(char,3), "information_score": round(info,3), "emotion_score": round(emotion,3), "visual_score": 0.1, "audio_score": round(audio,3), "continuity_score": round(continuity,3), "highlight_score": round(highlight,3)}
    if info_tags: reasons.append("存在信息增量:" + ",".join(info_tags[:4]))
    if emotion_tags: reasons.append("存在情绪变化:" + ",".join(emotion_tags[:4]))
    if not reasons: reasons.append("基础剧情候选")
    return scores, reasons


def select_story_highlights_v2(scene_evidence, segments=None, video_path="", output_script_path="", target_minutes=8, highlight_selectivity="balanced"):
    mode = selectivity_v2(highlight_selectivity)
    cfg = {"strict": {"threshold": 0.72, "mult": 0.85, "keep_weak": False}, "balanced": {"threshold": 0.55, "mult": 1.05, "keep_weak": False}, "loose": {"threshold": 0.35, "mult": 1.50, "keep_weak": True}, "very_loose": {"threshold": 0.15, "mult": 10.0, "keep_weak": True}}[mode]
    target_seconds = max(60.0, float(target_minutes or 8) * 60.0 * cfg["mult"])
    evidence = []
    for idx, item in enumerate(scene_evidence or [], start=1):
        cur = dict(item)
        cur.setdefault("candidate_id", cur.get("segment_id") or cur.get("scene_id") or f"candidate_{idx:04d}")
        cur.setdefault("video_start", cur.get("start", cur.get("semantic_start", 0.0)))
        cur.setdefault("video_end", cur.get("end", cur.get("semantic_end", cur.get("video_start", 0.0))))
        cur.setdefault("subtitle_text", cur.get("subtitle_text") or cur.get("source_text") or cur.get("main_text_evidence") or "")
        evidence.append(cur)
    _audit_stage(video_path, output_script_path, "04_scene_evidence_before_new_stage3", evidence, {"policy": "stage2_no_delete"})
    scored = []
    for item in evidence:
        s = float(item.get("video_start", 0.0) or 0.0); e = float(item.get("video_end", s) or s)
        if e <= s: continue
        scores, reasons = _score_segment(item); scored.append((scores["highlight_score"], e-s, item, scores, reasons))
    if mode == "very_loose":
        candidates = scored; candidates.sort(key=lambda x: float(x[2].get("video_start", 0.0)))
    else:
        candidates = [x for x in scored if x[0] >= cfg["threshold"] or cfg["keep_weak"]]
        candidates.sort(key=lambda x: (-x[0], float(x[2].get("video_start", 0.0))))
    selected, total = [], 0.0
    for row in candidates:
        if mode != "very_loose" and total >= target_seconds: break
        selected.append(row); total += row[1]
    selected.sort(key=lambda x: float(x[2].get("video_start", 0.0)))
    highlights = []
    for idx, (_, _, src, scores, reasons) in enumerate(selected, start=1):
        s = float(src.get("video_start", 0.0) or 0.0); e = float(src.get("video_end", s) or s)
        seg_id = src.get("segment_id") or src.get("candidate_id") or f"plot_{idx:03d}"
        highlights.append({"highlight_id": f"highlight_{idx:03d}", "highlight_rank": idx, "scene_ids": [src.get("scene_id") or seg_id], "segment_ids": [seg_id], "evidence_ids": [seg_id], "plot_functions": [src.get("plot_function")] if src.get("plot_function") else [], "highlight_reasons": reasons, "highlight_score": scores["highlight_score"], "importance_level": src.get("importance_level", "medium"), "boundary_confidence": src.get("boundary_confidence", "medium"), "raw_voice_retain": src.get("plot_function") in {"情感爆发", "冲突升级"}, "semantic_start": s, "semantic_end": e, "semantic_duration": round(e-s, 3), "semantic_timestamp": f"{_fmt(s)}-{_fmt(e)}", "start": s, "end": e, "video_start": s, "video_end": e, "duration": round(e-s, 3), "timestamp": f"{_fmt(s)}-{_fmt(e)}", "source_text": src.get("subtitle_text") or src.get("source_text") or "", "llm_highlight_selected": True, "highlight_filter_selected": True, "highlight_selectivity": mode, "scores": scores, "stage3_policy": "movie_story_direct_v2_multiscore_selection"})
    _audit_stage(video_path, output_script_path, "05_selected_highlights_new_stage3", highlights, {"selectivity": mode, "target_seconds": target_seconds})
    logger.warning("movie_story direct v2 stage3: mode=%s input=%s selected=%s duration=%.2fs", mode, len(evidence), len(highlights), sum(x["duration"] for x in highlights))
    return highlights
