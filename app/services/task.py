import re

import json
import os
from os import path

from loguru import logger

from app.config.audio_config import get_recommended_volumes_for_content
from app.models import const
from app.models.schema import VideoClipParams
from app.services import (
    audio_merger,
    clip_video,
    generate_video,
    merger_video,
    subtitle_merger,
    update_script,
    voice,
)
from app.services.composition_plan_adapter import composition_plan_to_script_items, is_composition_plan
from app.services import state as sm
from app.services.preflight_check import PreflightError, validate_script_items, validate_tts_results
from app.services.script_fallback import ensure_script_shape
from app.services.tts_cache import load_cached_tts_results, store_tts_results
from app.services.media_duration import probe_media_duration
from app.utils import utils


def _timestamp_to_seconds_range(timestamp: str):
    timestamp = str(timestamp or "").strip()
    if not timestamp or "-" not in timestamp:
        return None, None
    try:
        start_raw, end_raw = timestamp.split("-", 1)
        start = utils.time_to_seconds(start_raw.strip())
        end = utils.time_to_seconds(end_raw.strip())
        if end <= start:
            return None, None
        return round(start, 3), round(end, 3)
    except Exception:
        return None, None


def _normalize_script_item(item, idx: int):
    new_item = dict(item or {})
    start = new_item.get("start")
    end = new_item.get("end")
    try:
        start = float(start) if start is not None else None
        end = float(end) if end is not None else None
    except Exception:
        start, end = None, None

    if start is None or end is None or end <= start:
        ts_start, ts_end = _timestamp_to_seconds_range(new_item.get("timestamp", ""))
        if ts_start is not None and ts_end is not None:
            start, end = ts_start, ts_end

    if start is None:
        start = 0.0
    if end is None or end <= start:
        duration_guess = float(new_item.get("duration") or 0)
        end = start + max(duration_guess, 1.0)

    new_item["start"] = round(float(start), 3)
    new_item["end"] = round(float(end), 3)
    new_item["duration"] = round(max(float(end) - float(start), 0.001), 3)
    new_item["timestamp"] = f"{utils.format_time(start)}-{utils.format_time(end)}"
    new_item.setdefault("_id", idx)
    new_item.setdefault("OST", 2)
    new_item.setdefault("picture", "")
    return new_item


def _normalize_script_list(items):
    normalized = [_normalize_script_item(item, idx) for idx, item in enumerate(items or [], start=1)]
    normalized.sort(key=lambda x: (float(x.get("start", 0.0) or 0.0), int(x.get("_id", 0) or 0)))
    return normalized


_SCRIPT_MODE_SENTINELS = {"summary", "short_summary", "short", "file_selection", "upload_script"}


def _prefer_highlight_script_path(video_script_path: str) -> str:
    normalized_path = str(video_script_path or "").strip()
    if not normalized_path or not path.isfile(normalized_path):
        return normalized_path
    if normalized_path.endswith("_highlight_script.json"):
        return normalized_path
    if normalized_path.endswith("_movie_story.json"):
        candidate = normalized_path[:-len("_movie_story.json")] + "_highlight_script.json"
        if path.isfile(candidate):
            logger.info(f"检测到高光脚本，优先用于最终合成: {candidate}")
            return candidate
    return normalized_path




def _preview_log_text(text, max_chars: int = 120) -> str:
    text = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return "(空)"
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def _pick_script_item_interval(item):
    if not isinstance(item, dict):
        return None

    # raw_srt multi-clip opening/ending: old composer uses one interval,
    # so choose the first concrete clip and keep source_clips metadata.
    for clips_key in ("source_clips", "raw_srt_source_clips"):
        clips = item.get(clips_key)
        if isinstance(clips, list):
            for clip in clips:
                if not isinstance(clip, dict):
                    continue
                start = _parse_time_to_seconds(
                    clip.get("start", clip.get("source_start", clip.get("video_start"))),
                    None,
                )
                end = _parse_time_to_seconds(
                    clip.get("end", clip.get("source_end", clip.get("video_end"))),
                    None,
                )
                if start is not None and end is not None and end > start:
                    return float(start), float(end)

    # Prefer numeric/display fields over timestamp because a bad old timestamp
    # may already be 00:00:00,000-00:00:01,000.
    for a, b in (
        ("start", "end"),
        ("source_start", "source_end"),
        ("video_start", "video_end"),
        ("start_time", "end_time"),
        ("begin", "finish"),
    ):
        start = _parse_time_to_seconds(item.get(a), None)
        end = _parse_time_to_seconds(item.get(b), None)
        if start is not None and end is not None and end > start:
            return float(start), float(end)

    # Last resort: parse a timestamp range.
    for key in ("new_timestamp", "timestamp", "source_timestamp"):
        raw = item.get(key)
        if not raw:
            continue
        parts = re.split(r"\s*(?:-->|->|~|—|–|至|到|-)\s*", str(raw), maxsplit=1)
        if len(parts) != 2:
            continue
        start = _parse_time_to_seconds(parts[0], None)
        end = _parse_time_to_seconds(parts[1], None)
        if start is not None and end is not None and end > start:
            return float(start), float(end)

    return None


def _normalize_script_item_time_fields(script_items):
    if not isinstance(script_items, list):
        return script_items

    fixed = []
    for raw in script_items:
        if not isinstance(raw, dict):
            fixed.append(raw)
            continue

        item = dict(raw)
        interval = _pick_script_item_interval(item)
        if interval is None:
            fixed.append(item)
            continue

        start, end = interval
        if end <= start:
            end = start + 0.5

        timestamp = f"{_format_timestamp_srt(start)}-{_format_timestamp_srt(end)}"

        item["start"] = round(float(start), 3)
        item["end"] = round(float(end), 3)
        item["source_start"] = round(float(start), 3)
        item["source_end"] = round(float(end), 3)
        item["video_start"] = round(float(start), 3)
        item["video_end"] = round(float(end), 3)
        item["duration"] = round(float(end - start), 3)
        item["timestamp"] = timestamp
        item["new_timestamp"] = timestamp
        item["source_timestamp"] = timestamp

        fixed.append(item)

    return fixed



def _parse_time_to_seconds(value, default=None):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return default
    raw = str(value).strip()
    if not raw:
        return default
    raw = re.split(r"\s*(?:-->|->|~|—|–|至|到|-)\s*", raw, maxsplit=1)[0].strip()
    raw = raw.replace(",", ".")
    try:
        parts = raw.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        return float(raw)
    except Exception:
        return default


def _time_range_from_text(value):
    if not value:
        return None
    parts = re.split(r"\s*(?:-->|->|~|—|–|至|到|-)\s*", str(value).strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    start = _parse_time_to_seconds(parts[0], None)
    end = _parse_time_to_seconds(parts[1], None)
    if start is None or end is None or end <= start:
        return None
    return float(start), float(end)


def _get_item_source_ranges(item):
    ranges = []
    if not isinstance(item, dict):
        return ranges

    for clips_key in ("source_clips", "raw_srt_source_clips"):
        clips = item.get(clips_key)
        if isinstance(clips, list):
            for clip in clips:
                if not isinstance(clip, dict):
                    continue
                s = _parse_time_to_seconds(clip.get("start", clip.get("source_start", clip.get("video_start"))), None)
                e = _parse_time_to_seconds(clip.get("end", clip.get("source_end", clip.get("video_end"))), None)
                if s is not None and e is not None and e > s:
                    ranges.append((float(s), float(e)))

    for key in ("raw_srt_source_timestamp", "source_timestamp_original", "original_timestamp", "source_timestamp"):
        parsed = _time_range_from_text(item.get(key))
        if parsed:
            ranges.append(parsed)

    for a, b in (("raw_srt_source_start", "raw_srt_source_end"), ("source_start", "source_end"), ("start", "end"), ("video_start", "video_end")):
        s = _parse_time_to_seconds(item.get(a), None)
        e = _parse_time_to_seconds(item.get(b), None)
        if s is not None and e is not None and e > s:
            ranges.append((float(s), float(e)))

    for key in ("new_timestamp", "timestamp"):
        parsed = _time_range_from_text(item.get(key))
        if parsed:
            ranges.append(parsed)

    out, seen = [], set()
    for s, e in ranges:
        k = (round(s, 3), round(e, 3))
        if k not in seen:
            seen.add(k)
            out.append((s, e))
    return out


def _ffprobe_duration(path):
    if not path:
        return None
    try:
        p = str(path)
        if not os.path.exists(p):
            return None
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nk=1:nw=1", p
        ], stderr=subprocess.STDOUT, text=True, timeout=15).strip()
        v = float(out)
        return v if v > 0 else None
    except Exception:
        return None


def _audio_path(obj):
    if not isinstance(obj, dict):
        return None
    for key in ("audio_file", "audio_path", "file_path", "path", "filename", "audio", "voice_file", "tts_audio"):
        v = obj.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _collect_tts_durations(tts_results, script_items):
    raw = tts_results
    if isinstance(raw, dict):
        for key in ("items", "results", "tts_results", "audio_results", "audios", "files"):
            if isinstance(raw.get(key), list):
                raw = raw.get(key)
                break
    if not isinstance(raw, list):
        raw = []
    durations = []
    for idx, item in enumerate(script_items or []):
        result = raw[idx] if idx < len(raw) else None
        dur = None
        if isinstance(result, dict):
            for key in ("duration", "audio_duration", "duration_seconds", "seconds", "tts_duration", "voice_duration"):
                val = result.get(key)
                try:
                    if val is not None and float(val) > 0:
                        dur = float(val)
                        break
                except Exception as _e:
                    logger.debug("数值转换失败，跳过: {}", _e)
            if dur is None:
                dur = _ffprobe_duration(_audio_path(result))
        if dur is None and isinstance(item, dict):
            dur = _ffprobe_duration(_audio_path(item))
        if dur is None:
            text = str(item.get("narration") or item.get("text") or "") if isinstance(item, dict) else ""
            dur = max(len(text) / 5.0, 3.0)
        durations.append(float(dur))
    return durations


def _overlap(a_start, a_end, b_start, b_end):
    return max(0.0, min(float(a_end), float(b_end)) - max(float(a_start), float(b_start)))


def _find_free_window(source_start, source_end, need_duration, used_windows, gap=0.15):
    source_start, source_end, need_duration = float(source_start), float(source_end), float(need_duration)
    if source_end <= source_start:
        return None
    need = min(need_duration, source_end - source_start)
    intervals = []
    for u_start, u_end in used_windows:
        if _overlap(source_start, source_end, u_start, u_end) > 0:
            intervals.append((max(source_start, u_start), min(source_end, u_end)))
    intervals.sort()
    cursor = source_start
    for u_start, u_end in intervals:
        if u_start - cursor >= need:
            return cursor, cursor + need
        cursor = max(cursor, u_end + gap)
    if source_end - cursor >= need:
        return cursor, cursor + need
    return None


def _find_least_overlap_window(source_start, source_end, need_duration, used_windows):
    source_start, source_end = float(source_start), float(source_end)
    total = source_end - source_start
    if total <= 0:
        return source_start, source_start + 0.5
    need = min(float(need_duration), total)
    best = (source_start, source_start + need)
    best_overlap = None
    pos = source_start
    max_start = source_end - need
    while pos <= max_start + 1e-6:
        end = pos + need
        ov = sum(_overlap(pos, end, u_start, u_end) for u_start, u_end in used_windows)
        if best_overlap is None or ov < best_overlap:
            best_overlap = ov
            best = (pos, end)
        pos += 0.5
    return best


def _allocate_video_windows_from_tts(script_items, tts_results=None, padding=0.0):
    if not isinstance(script_items, list):
        return script_items
    durations = _collect_tts_durations(tts_results, script_items)
    used_windows = []
    fixed = []
    for idx, raw in enumerate(script_items):
        if not isinstance(raw, dict):
            fixed.append(raw)
            continue
        item = dict(raw)
        source_ranges = _get_item_source_ranges(item)
        if not source_ranges:
            item["OST"] = 0
            item["composition_audio_mode"] = "tts"
            fixed.append(item)
            continue
        need = durations[idx] if idx < len(durations) else max(len(str(item.get("narration") or item.get("text") or "")) / 5.0, 3.0)
        need = float(need) + float(padding or 0.0)
        chosen = None
        for s_start, s_end in source_ranges:
            chosen = _find_free_window(s_start, s_end, need, used_windows)
            if chosen is not None:
                break
        if chosen is None:
            best, best_ov = None, None
            for s_start, s_end in source_ranges:
                cand = _find_least_overlap_window(s_start, s_end, need, used_windows)
                ov = sum(_overlap(cand[0], cand[1], u_start, u_end) for u_start, u_end in used_windows)
                if best is None or ov < best_ov:
                    best, best_ov = cand, ov
            chosen = best
        if chosen is None:
            fixed.append(item)
            continue
        v_start, v_end = chosen
        if v_end <= v_start:
            v_end = v_start + max(need, 0.5)
        used_windows.append((float(v_start), float(v_end)))
        src = source_ranges[0]
        item["raw_srt_source_start"] = round(float(src[0]), 3)
        item["raw_srt_source_end"] = round(float(src[1]), 3)
        item["raw_srt_source_timestamp"] = f"{_format_timestamp_srt(src[0])}-{_format_timestamp_srt(src[1])}"
        final_ts = f"{_format_timestamp_srt(v_start)}-{_format_timestamp_srt(v_end)}"
        item["start"] = round(float(v_start), 3)
        item["end"] = round(float(v_end), 3)
        item["source_start"] = round(float(v_start), 3)
        item["source_end"] = round(float(v_end), 3)
        item["video_start"] = round(float(v_start), 3)
        item["video_end"] = round(float(v_end), 3)
        item["duration"] = round(float(v_end - v_start), 3)
        item["timestamp"] = final_ts
        item["new_timestamp"] = final_ts
        item["source_timestamp"] = final_ts
        item["allocated_from_source_range"] = True
        item["audio_duration"] = round(float(need), 3)
        item["OST"] = 0
        item["composition_audio_mode"] = "tts"
        fixed.append(item)
    return fixed


def _force_raw_srt_ost_zero(script_items):
    if not isinstance(script_items, list):
        return script_items
    out = []
    for raw in script_items:
        if isinstance(raw, dict):
            item = dict(raw)
            item["OST"] = 0
            item["composition_audio_mode"] = "tts"
            out.append(item)
        else:
            out.append(raw)
    return out


def _log_script_items_preview(list_script, video_ost):
    total = len(list_script or [])
    logger.debug(f"解说片段数: {total}")
    logger.debug(f"解说 OST 列表: {video_ost}")
    for idx, item in enumerate(list_script or [], start=1):
        timestamp = item.get("timestamp") or f"{utils.format_time(item.get('start', 0))}-{utils.format_time(item.get('end', 0))}"
        ost = item.get("OST")
        narration = _preview_log_text(item.get("narration"), 160)
        logger.debug(f"解说片段 [{idx}/{total}] 时间戳={timestamp} OST={ost} 文案={narration}")

def _prepare_script_items(list_script):
    list_script = ensure_script_shape(list_script)
    list_script = _normalize_script_list(list_script)
    validate_script_items(list_script)
    _validate_composition_script_quality(list_script)
    video_ost = [i["OST"] for i in list_script]
    list_script = _normalize_script_item_time_fields(list_script)
    list_script = _force_raw_srt_ost_zero(list_script)
    _log_script_items_preview(list_script, video_ost)
    return list_script, video_ost


def _validate_composition_script_quality(list_script):
    if not list_script:
        raise ValueError("最终合成脚本为空")

    issues = []
    has_highlight_metadata = any("llm_highlight_selected" in item for item in list_script)
    highlight_only_mode = any(bool(item.get("highlight_id")) for item in list_script) and all(
        str(item.get("narration") or "").strip() == "" for item in list_script
    )

    for idx, item in enumerate(list_script, start=1):
        seg_label = str(item.get("segment_id") or item.get("_id") or idx)
        start = float(item.get("start", 0.0) or 0.0)
        end = float(item.get("end", start) or start)
        if end <= start:
            issues.append(f"片段时间非法: {seg_label}")
        if (
            has_highlight_metadata
            and not bool(item.get("llm_highlight_selected"))
            and not bool(item.get("highlight_filter_selected"))
            and not highlight_only_mode
        ):
            issues.append(f"脚本包含未通过高光筛选的片段: {seg_label}")
        nv = item.get("narration_validation") or {}
        if nv.get("status") == "reject":
            issues.append(f"脚本包含被拒绝的解说文案: {seg_label}")
        if int(item.get("OST", 2) or 2) == 1 and not highlight_only_mode:
            if not bool(item.get("llm_raw_voice_keep")) and not bool(item.get("raw_voice_retain_suggestion")):
                issues.append(f"原声片段未经高光许可: {seg_label}")
        if not highlight_only_mode and int(item.get("OST", 2) or 2) in {0, 2} and not str(item.get("narration") or "").strip():
            issues.append(f"需配音片段缺少解说词: {seg_label}")

    deduped = []
    for issue in issues:
        if issue not in deduped:
            deduped.append(issue)
    if deduped:
        raise ValueError("；".join(deduped))


def _is_highlight_only_script(list_script) -> bool:
    return bool(list_script) and any(bool(item.get("highlight_id")) for item in list_script) and all(
        str(item.get("narration") or "").strip() == "" for item in list_script
    )


def _is_direct_cut_raw_script(list_script) -> bool:
    return bool(list_script) and all(
        bool(item.get("direct_cut_first"))
        and int(item.get("OST", 2) or 2) == 1
        and not str(item.get("narration") or "").strip()
        for item in list_script
    )


def _force_narrated_segments_to_voice_only(list_script):
    # 有解说的片段不保留原声，避免原片声音盖过解说。
    # narration 非空：OST=0；narration 为空：OST=1。
    fixed = []
    changed = 0
    for item in list_script or []:
        row = dict(item)
        has_narration = bool(str(row.get("narration") or "").strip())
        old_ost = int(row.get("OST", 2) or 2)
        new_ost = 0 if has_narration else 1
        if old_ost != new_ost:
            changed += 1
            row["ost_before_audio_policy"] = old_ost
            row["OST"] = new_ost
        fixed.append(row)
    if changed:
        logger.warning("音频策略修正：有解说片段强制去原声，修正 {} 个 OST", changed)
    return fixed


def _load_and_prepare_script(video_script_path: str, fallback_items=None):
    normalized_path = _prefer_highlight_script_path(video_script_path)
    can_use_fallback = bool(fallback_items)
    path_looks_like_mode = normalized_path in _SCRIPT_MODE_SENTINELS

    if normalized_path and path.exists(normalized_path):
        try:
            with open(normalized_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            list_script = composition_plan_to_script_items(payload) if is_composition_plan(payload) else payload
            return _prepare_script_items(list_script)
        except PreflightError:
            raise
        except Exception as e:
            logger.error(f"无法读取视频 json 脚本，请检查脚本格式是否正确: {e}")
            raise ValueError("无法读取视频 json 脚本，请检查脚本格式是否正确")

    if can_use_fallback:
        if normalized_path:
            if path_looks_like_mode:
                logger.warning(f"检测到脚本模式标识 {normalized_path}，将直接使用内存中的脚本内容继续处理")
            else:
                logger.warning(f"脚本文件不存在: {normalized_path}，将回退到当前已生成但未保存的脚本内容")
        else:
            logger.warning("未提供脚本文件路径，将直接使用当前已生成的脚本内容")
        return _prepare_script_items(fallback_items)

    logger.error(f"解说脚本文件不存在: {normalized_path}，请先点击【保存脚本】按钮保存脚本后再生成视频")
    raise ValueError("解说脚本文件不存在！请先点击【保存脚本】按钮保存脚本后再生成视频。")



def _parse_ts_range(value):
    if not value:
        return None
    text = str(value).strip()
    parts = re.split(r"\s*(?:-->|->|~|—|–|至|到|-)\s*", text, maxsplit=1)
    if len(parts) != 2:
        return None

    def parse_one(raw):
        raw = str(raw).strip().replace(",", ".")
        try:
            ps = raw.split(":")
            if len(ps) == 2:
                return float(ps[0]) * 60.0 + float(ps[1])
            if len(ps) == 3:
                return float(ps[0]) * 3600.0 + float(ps[1]) * 60.0 + float(ps[2])
            return float(raw)
        except Exception:
            return None

    start = parse_one(parts[0])
    end = parse_one(parts[1])
    if start is None or end is None or end <= start:
        return None
    return float(start), float(end)


def _format_timestamp_srt(seconds):
    try:
        value = max(float(seconds or 0.0), 0.0)
    except Exception:
        value = 0.0

    total_ms = int(round(value * 1000.0))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    sec = total_s % 60
    total_m = total_s // 60
    minute = total_m % 60
    hour = total_m // 60
    return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def _make_tts_file_keys_unique(video_items):
    """Make TTS audio/subtitle file keys unique before _build_tts_results.

    TTS currently names audio/subtitle files from timestamp/new_timestamp/source_timestamp.
    When opening and argument share the same source range, TTS overwrites the earlier mp3/srt.
    This function only dedupes the TTS naming timestamp for exact duplicates.
    It preserves raw source range for the later v15 video window allocator.
    """
    if not isinstance(video_items, list):
        return video_items

    seen = {}
    fixed = []

    for index, raw in enumerate(video_items, start=1):
        if not isinstance(raw, dict):
            fixed.append(raw)
            continue

        item = dict(raw)

        if item.get("generation_mode") == "raw_srt_two_round_narration" or item.get("composition_audio_mode") == "tts":
            item["OST"] = 0
            item["composition_audio_mode"] = "tts"

        base_ts = (
            item.get("new_timestamp")
            or item.get("timestamp")
            or item.get("source_timestamp")
            or item.get("raw_srt_source_timestamp")
        )

        if base_ts:
            original_source_ts = item.get("source_timestamp") or base_ts
            item.setdefault("source_timestamp_original", original_source_ts)
            item.setdefault("raw_srt_source_timestamp", item.get("raw_srt_source_timestamp") or original_source_ts)
            item.setdefault("raw_srt_source_timestamp_before_tts_dedupe", original_source_ts)

            key = str(base_ts)
            dup_index = seen.get(key, 0)
            seen[key] = dup_index + 1

            if dup_index > 0:
                parsed = _parse_ts_range(base_ts)
                if parsed:
                    start, end = parsed
                    # Tiny offset: enough to make filenames unique, small enough not to affect later source-pool allocation.
                    offset = 0.037 * dup_index
                    unique_ts = f"{_format_timestamp_srt(start + offset)}-{_format_timestamp_srt(end + offset)}"
                else:
                    unique_ts = f"{base_ts}__item{index:03d}"

                item["timestamp"] = unique_ts
                item["new_timestamp"] = unique_ts
                item["source_timestamp"] = unique_ts
                item["tts_file_timestamp"] = unique_ts
                item["tts_file_key_deduped"] = True
                item["tts_file_key_dedup_index"] = dup_index

        fixed.append(item)

    return fixed

def _build_tts_results(task_id: str, list_script, params):
    tts_segments = [segment for segment in list_script if segment["OST"] in [0, 2]]
    logger.info(f"需要生成TTS的片段数: {len(tts_segments)}")
    if not tts_segments:
        return [], []

    cached_results, missing_items = load_cached_tts_results(
        task_id=task_id,
        list_script=tts_segments,
        voice_name=params.voice_name,
        voice_rate=params.voice_rate,
        voice_pitch=params.voice_pitch,
        tts_engine=params.tts_engine,
    )

    generated_results = []
    if missing_items:
        generated_results = voice.tts_multiple(
            task_id=task_id,
            list_script=missing_items,
            tts_engine=params.tts_engine,
            voice_name=params.voice_name,
            voice_rate=params.voice_rate,
            voice_pitch=params.voice_pitch,
        ) or []
        if generated_results:
            store_tts_results(
                list_script=missing_items,
                tts_results=generated_results,
                voice_name=params.voice_name,
                voice_rate=params.voice_rate,
                voice_pitch=params.voice_pitch,
                tts_engine=params.tts_engine,
            )

    tts_results = sorted(cached_results + generated_results, key=lambda x: x.get('_id', 0))
    tts_results = _ensure_tts_result_durations(tts_results)
    validate_tts_results(list_script, tts_results)
    return tts_segments, tts_results


def _ensure_tts_result_durations(tts_results):
    updated = []
    for item in tts_results or []:
        new_item = dict(item)
        duration = float(new_item.get("duration") or 0)
        if duration <= 0:
            duration = probe_media_duration(new_item.get("audio_file", ""))
            if duration > 0:
                new_item["duration"] = duration
        updated.append(new_item)
    return updated


def _align_script_timings_to_audio(script_list):
    aligned = []
    for item in script_list or []:
        new_item = dict(item)
        duration = float(new_item.get("duration") or 0)
        if duration <= 0 and new_item.get("audio"):
            duration = probe_media_duration(new_item.get("audio"))
            if duration > 0:
                new_item["duration"] = duration
        aligned.append(new_item)
    return aligned


def _merge_audio_and_subtitles(task_id: str, list_script, total_duration: float) -> tuple[str, str]:
    if not list_script:
        return "", ""

    audio_path = audio_merger.merge_audio_files(
        task_id=task_id,
        total_duration=total_duration,
        list_script=list_script,
    )
    subtitle_path = subtitle_merger.merge_subtitle_files(list_script) or ""
    return audio_path, subtitle_path



def _probe_source_video_size(video_path: str):
    # 读取原视频真实宽高。失败返回 (0, 0)。
    try:
        import subprocess
        if not video_path or not os.path.exists(video_path):
            return 0, 0
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            video_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=20)
        text = (result.stdout or "").strip()
        if "x" in text:
            w, h = text.split("x")[:2]
            return int(w), int(h)
    except Exception as exc:
        logger.warning("读取原视频宽高失败: {} | {}", video_path, exc)
    return 0, 0


def _infer_effective_video_aspect(params):
    # 复刻旧 UI 的关键逻辑：按原视频宽高推断横竖屏。
    # 同时更细一点：识别 4:3 / 3:4 / 1:1。
    ui_aspect = str(getattr(params, "video_aspect", "") or "").strip()
    video_path = str(getattr(params, "video_origin_path", "") or "").strip()
    w, h = _probe_source_video_size(video_path)

    if w <= 0 or h <= 0:
        logger.warning("旧UI式横竖屏推断失败，继续使用 UI 参数: ui_aspect={}", ui_aspect)
        return ui_aspect or "16:9"

    ratio = w / h

    if 0.92 <= ratio <= 1.08:
        effective = "1:1"
    elif h > w:
        if 0.70 <= ratio <= 0.82:
            effective = "3:4"
        else:
            effective = "9:16"
    else:
        if 1.24 <= ratio <= 1.45:
            effective = "4:3"
        else:
            effective = "16:9"

    if effective != ui_aspect:
        logger.warning(
            "旧UI式横竖屏推断: source={}x{}, ratio={:.4f}, ui_aspect={}, effective={}",
            w, h, ratio, ui_aspect, effective
        )
    else:
        logger.warning(
            "旧UI式横竖屏推断: source={}x{}, ratio={:.4f}, ui_aspect 与 effective 一致: {}",
            w, h, ratio, effective
        )

    return effective


def _combine_video_segments(task_id: str, params: VideoClipParams, new_script_list, video_ost):
    combined_video_path = path.join(utils.task_dir(task_id), "merger.mp4")
    video_clips = []
    for new_script in new_script_list:
        video_path = new_script.get("video")
        if video_path and os.path.exists(video_path):
            video_clips.append(video_path)
        else:
            logger.error(f"片段 {new_script.get('_id')} 的视频文件不存在: {video_path}")

    if not video_clips:
        raise ValueError("没有可用于合并的视频片段")

    effective_video_aspect = _infer_effective_video_aspect(params)
    merger_video.combine_clip_videos(
        output_video_path=combined_video_path,
        video_paths=video_clips,
        video_ost_list=video_ost,
        video_aspect=effective_video_aspect,
        threads=params.n_threads,
    )
    return combined_video_path


_CANONICAL_VIDEO_SUBTITLE_FONT = "C:/Windows/Fonts/simhei.ttf"
_LEGACY_VIDEO_SUBTITLE_FONT_ALIASES = {
    "SimHei": _CANONICAL_VIDEO_SUBTITLE_FONT,
}


def _canonicalize_video_font_name(font_name: object) -> str:
    """Return the canonical subtitle font contract used by video jobs.

    Historical UI/build artifacts may still submit ``SimHei`` even after the
    schema default was changed. The video pipeline contract now expects a real
    font file path. This function migrates only the exact historical default
    alias and blank values to the canonical Windows font path. Other values are
    left unchanged and are still validated by generate_video.
    """
    font_text = "" if font_name is None else str(font_name).strip()
    if not font_text:
        return _CANONICAL_VIDEO_SUBTITLE_FONT

    return _LEGACY_VIDEO_SUBTITLE_FONT_ALIASES.get(font_text, font_text)



def _final_merge(task_id: str, params: VideoClipParams, combined_video_path: str, list_script, *, audio_path: str = "", subtitle_path: str = ""):
    output_video_path = path.join(utils.task_dir(task_id), "combined.mp4")
    bgm_path = utils.get_bgm_file()
    optimized_volumes = get_recommended_volumes_for_content("mixed")
    has_original_audio_segments = any(int(segment.get("OST", 0) or 0) == 1 for segment in list_script)
    direct_cut_raw_mode = _is_direct_cut_raw_script(list_script)

    user_tts_volume = float(getattr(params, "tts_volume", 1.0) or 1.0)
    user_original_volume = float(getattr(params, "original_volume", 0.7) or 0.7)
    user_bgm_volume = float(getattr(params, "bgm_volume", 0.3) or 0.3)

    if direct_cut_raw_mode:
        final_tts_volume = user_tts_volume
        final_original_volume = 1.0
        final_bgm_volume = 0.0
        bgm_path = ""
        audio_policy = "direct_cut_original_audio"
    else:
        final_tts_volume = max(user_tts_volume, float(optimized_volumes.get("tts_volume", 1.0) or 1.0), 1.35)
        final_original_volume = min(user_original_volume, 0.45) if has_original_audio_segments else 0.0
        final_bgm_volume = min(user_bgm_volume, float(optimized_volumes.get("bgm_volume", 0.18) or 0.18), 0.12)
        audio_policy = "narration_mutes_original"

    options = {
        "voice_volume": final_tts_volume,
        "bgm_volume": final_bgm_volume,
        "original_audio_volume": final_original_volume,
        "keep_original_audio": has_original_audio_segments,
        "subtitle_enabled": params.subtitle_enabled,
        "subtitle_font": _canonicalize_video_font_name(params.font_name),
        "subtitle_font_size": params.font_size,
        "subtitle_color": params.text_fore_color,
        "subtitle_bg_color": None,
        "subtitle_position": params.subtitle_position,
        "custom_position": params.custom_position,
        "threads": params.n_threads,
        "disable_smart_volume": True,
        "audio_policy": audio_policy,
    }
    generate_video.merge_materials(
        video_path=combined_video_path,
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        bgm_path=bgm_path,
        output_path=output_video_path,
        options=options,
    )
    return output_video_path


def _run_pipeline(task_id: str, params: VideoClipParams):
    logger.info(f"\n\n## 开始统一视频处理任务: {task_id}")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=0)

    logger.info("\n\n## 1. 加载视频脚本")
    list_script, video_ost = _load_and_prepare_script(params.video_clip_json_path, fallback_items=params.video_clip_json)
    logger.info("最终合成脚本模式: {}", "highlight_only" if _is_highlight_only_script(list_script) else "narrated_story")

    logger.info("\n\n## 2. 根据OST设置生成音频列表")
    try:
        list_script = _make_tts_file_keys_unique(list_script)
        tts_segments, tts_results = _build_tts_results(task_id, list_script, params)
    except PreflightError as e:
        logger.error(str(e))
        raise ValueError(str(e))
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=20)
    logger.info("\n\n## 3. 统一视频裁剪（基于OST类型）")
    list_script = _allocate_video_windows_from_tts(list_script, locals().get('tts_results') or locals().get('audio_results') or locals().get('tts_result') or locals().get('tts_tasks'))
    video_clip_output_dir = utils.task_dir(os.path.join(task_id, "clip_video_unified"))
    video_clip_result = clip_video.clip_video_unified(
        video_origin_path=params.video_origin_path,
        script_list=list_script,
        tts_results=tts_results,
        output_dir=video_clip_output_dir,
        task_id=task_id,
    )
    tts_clip_result = {tts_result["_id"]: tts_result["audio_file"] for tts_result in tts_results}
    subclip_clip_result = {tts_result["_id"]: tts_result["subtitle_file"] for tts_result in tts_results}
    new_script_list = update_script.update_script_timestamps(list_script, video_clip_result, tts_clip_result, subclip_clip_result)
    new_script_list = _align_script_timings_to_audio(new_script_list)
    logger.info(f"统一裁剪完成，处理了 {len(video_clip_result)} 个视频片段")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=60)

    logger.info("\n\n## 4. 合并音频和字幕")
    total_duration = sum([script.get("duration", 0) for script in new_script_list])
    merged_audio_path = ""
    merged_subtitle_path = ""
    if tts_segments:
        try:
            merged_audio_path, merged_subtitle_path = _merge_audio_and_subtitles(task_id, new_script_list, total_duration)
        except Exception as e:
            logger.error(f"合并音频/字幕文件失败: {str(e)}")
            raise
    else:
        logger.warning("没有需要合并的音频/字幕")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=80)

    logger.info("\n\n## 5. 合并视频")
    combined_video_path = _combine_video_segments(task_id, params, new_script_list, video_ost)

    logger.info(f"\n\n## 6. 最后一步: 合并字幕/BGM/配音/视频")
    output_video_path = _final_merge(
        task_id,
        params,
        combined_video_path,
        list_script,
        audio_path=merged_audio_path,
        subtitle_path=merged_subtitle_path,
    )

    kwargs = {
        "videos": [output_video_path],
        "combined_videos": [combined_video_path],
    }
    sm.state.update_task(task_id, state=const.TASK_STATE_COMPLETE, progress=100, **kwargs)
    logger.success(f"统一处理任务 {task_id} 已完成")
    return kwargs


def start_subclip(task_id: str, params: VideoClipParams, subclip_path_videos: dict = None):
    return _run_pipeline(task_id, params)


def start_subclip_unified(task_id: str, params: VideoClipParams):
    return _run_pipeline(task_id, params)


def validate_params(video_path, audio_path, output_file, params):
    if not video_path:
        raise ValueError("视频路径不能为空")
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    if audio_path and not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")
    if not output_file:
        raise ValueError("输出文件路径不能为空")
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not params:
        raise ValueError("视频参数不能为空")
