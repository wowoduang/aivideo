# -*- coding: utf-8 -*-
from __future__ import annotations

"""
aliyun_funasr_speaker_context.py

把阿里云 Fun-ASR/Paraformer 录音文件识别的 speaker_id 结果对齐到原始 SRT 时间轴，
生成 raw_srt 第一轮提示词使用的 {speaker_context} 文本。

本模块不从字幕文本猜人名；字幕只作为时间轴和对齐容器。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.aliyun_funasr_speaker_context",
    "entry_points": [
        "normalize_aliyun_transcription_result",
        "build_speaker_context_text_from_aliyun_segments",
        "build_speaker_context_text_from_aliyun_result",
        "submit_funasr_recording_task",
    ],
    "called_by": [
        "movie_story/two_round_narration.py",
        "movie_story/raw_srt_context_builder.py",
    ],
    "decisions": [
        "2026-05: 阿里云 Fun-ASR/Paraformer diarization 是 speaker_context 第一版主线。",
        "2026-05: SRT 时间轴是输出主时间轴，Fun-ASR 时间轴只用于对齐 speaker_id。",
        "2026-05: 无 speaker_role_map 时输出 SPEAKER_00，不输出角色名。",
    ],
    "pending": [
        "接入 OSS 上传音频并生成公网 file_url。",
        "接入声纹库角色映射。",
    ],
    "ai_constraints": [
        "禁止解析字幕文本中的人名来生成 speaker_context。",
        "禁止调用 LLM 判断说话人。",
        "禁止输出两套时间轴。",
    ],
}

import time
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger


DEFAULT_DIARIZED_CONFIDENCE = 0.86
DEFAULT_MAPPED_CONFIDENCE = 0.90
UNCERTAIN_THRESHOLD = 0.70


def normalize_aliyun_transcription_result(result_json: Mapping[str, Any]) -> list[dict[str, Any]]:
    """
    从阿里云 transcription_url 下载后的 JSON 中抽取 diarization 句子结果。

    阿里云结果核心结构通常为：
        transcripts[*].sentences[*].begin_time
        transcripts[*].sentences[*].end_time
        transcripts[*].sentences[*].text
        transcripts[*].sentences[*].speaker_id

    begin_time/end_time 单位为毫秒。
    """
    segments: list[dict[str, Any]] = []
    transcripts = result_json.get("transcripts") or []
    if not isinstance(transcripts, list):
        return segments

    for transcript in transcripts:
        if not isinstance(transcript, Mapping):
            continue
        sentences = transcript.get("sentences") or []
        if not isinstance(sentences, list):
            continue
        for sentence in sentences:
            if not isinstance(sentence, Mapping):
                continue
            normalized = _normalize_sentence(sentence)
            if normalized is not None:
                segments.append(normalized)

    segments.sort(key=lambda item: (_safe_float(item.get("start"), default=0.0), _safe_float(item.get("end"), default=0.0)))
    logger.info("已归一化阿里云 Fun-ASR speaker segments: {}", len(segments))
    return segments


def build_speaker_context_text_from_aliyun_result(
    subtitle_segments: Sequence[Mapping[str, Any]],
    aliyun_result_json: Mapping[str, Any],
    *,
    speaker_role_map: Mapping[str, str] | None = None,
    speaker_confidence_map: Mapping[str, float] | None = None,
    max_lines: int = 260,
) -> str:
    """从阿里云完整 JSON 结果直接生成 {speaker_context} 文本。"""
    aliyun_segments = normalize_aliyun_transcription_result(aliyun_result_json)
    return build_speaker_context_text_from_aliyun_segments(
        subtitle_segments,
        aliyun_segments,
        speaker_role_map=speaker_role_map,
        speaker_confidence_map=speaker_confidence_map,
        max_lines=max_lines,
    )


def build_speaker_context_text_from_aliyun_segments(
    subtitle_segments: Sequence[Mapping[str, Any]],
    aliyun_segments: Sequence[Mapping[str, Any]],
    *,
    speaker_role_map: Mapping[str, str] | None = None,
    speaker_confidence_map: Mapping[str, float] | None = None,
    max_lines: int = 260,
) -> str:
    """
    把阿里云 speaker segments 对齐到 SRT 段，输出最终 {speaker_context} 文本。

    输出格式：
        00:04:44~00:04:48 | SPEAKER_00 | 0.86 | diarized
        00:04:44~00:04:48 | 朱重八 | 0.90 | confirmed
        00:07:52~00:08:00 | 母亲 | 0.65 | candidate（存疑）
    """
    if not subtitle_segments or not aliyun_segments:
        return "暂无可靠说话人识别结果。"

    role_map = dict(speaker_role_map or {})
    confidence_map = {str(key): float(value) for key, value in dict(speaker_confidence_map or {}).items()}

    lines: list[str] = []
    for subtitle in subtitle_segments:
        aligned = _align_one_subtitle_to_aliyun_segment(subtitle, aliyun_segments)
        if aligned is None:
            continue
        line = _format_aligned_speaker_line(
            subtitle,
            aligned,
            speaker_role_map=role_map,
            speaker_confidence_map=confidence_map,
        )
        if line:
            lines.append(line)
        if len(lines) >= max_lines:
            lines.append("……（说话人识别结果过长，已截断）")
            break

    if not lines:
        return "暂无可靠说话人识别结果。"
    return "\n".join(lines)


def submit_funasr_recording_task(
    file_url: str,
    *,
    api_key: str,
    model: str = "fun-asr",
    speaker_count: int | None = None,
    language_hints: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    提交阿里云 Fun-ASR/Paraformer 录音文件识别任务。

    注意：
    - file_url 必须是公网可访问 HTTP/HTTPS URL，或 RESTful 支持的 OSS URL。
    - diarization_enabled 固定为 True。
    - 说话人分离仅适用于单声道音频，音频应先用 ffmpeg 转单声道。
    """
    try:
        from dashscope.audio.asr import Transcription
    except ImportError as exc:
        raise RuntimeError("缺少 dashscope，请先安装：pip install dashscope") from exc

    kwargs: dict[str, Any] = {"diarization_enabled": True}
    if speaker_count is not None:
        kwargs["speaker_count"] = speaker_count
    if language_hints:
        kwargs["language_hints"] = list(language_hints)

    response = Transcription.async_call(
        model=model,
        file_urls=[file_url],
        api_key=api_key,
        **kwargs,
    )
    return _response_to_dict(response)


def wait_funasr_task(
    task_response_or_id: Mapping[str, Any] | str,
    *,
    api_key: str,
    poll_interval_seconds: float = 5.0,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    """等待阿里云录音文件识别任务完成。"""
    try:
        from dashscope.audio.asr import Transcription
    except ImportError as exc:
        raise RuntimeError("缺少 dashscope，请先安装：pip install dashscope") from exc

    task_id = _extract_task_id(task_response_or_id)
    if not task_id:
        raise ValueError("未找到 task_id")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = Transcription.fetch(task=task_id, api_key=api_key)
        payload = _response_to_dict(response)
        status = str(((payload.get("output") or {}).get("task_status")) or "")
        if status in {"SUCCEEDED", "FAILED"}:
            return payload
        logger.info("Fun-ASR 任务仍在执行: task_id={}, status={}", task_id, status)
        time.sleep(poll_interval_seconds)

    raise TimeoutError("等待 Fun-ASR 任务超时: {}".format(task_id))


def extract_transcription_urls(task_payload: Mapping[str, Any]) -> list[str]:
    """从任务结果中提取 transcription_url。"""
    output = task_payload.get("output") or {}
    if not isinstance(output, Mapping):
        return []
    results = output.get("results") or []
    urls: list[str] = []
    if not isinstance(results, list):
        return urls
    for item in results:
        if isinstance(item, Mapping) and item.get("subtask_status") == "SUCCEEDED" and item.get("transcription_url"):
            urls.append(str(item["transcription_url"]))
    return urls


def load_transcription_json_from_url(url: str, *, timeout_seconds: float = 60.0) -> dict[str, Any]:
    """下载 transcription_url 对应的 JSON 识别结果。"""
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("缺少 requests，请先安装：pip install requests") from exc

    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("transcription_url 返回的不是 JSON object")
    return data


def _normalize_sentence(sentence: Mapping[str, Any]) -> dict[str, Any] | None:
    """归一化阿里云 sentence。"""
    start_ms = _safe_float(sentence.get("begin_time"), default=-1.0)
    end_ms = _safe_float(sentence.get("end_time"), default=-1.0)
    if start_ms < 0 or end_ms <= start_ms:
        return None

    raw_speaker = sentence.get("speaker_id")
    speaker_id = _format_speaker_id(raw_speaker)
    return {
        "start": start_ms / 1000.0,
        "end": end_ms / 1000.0,
        "speaker_id": speaker_id,
        "text": str(sentence.get("text") or ""),
        "confidence": DEFAULT_DIARIZED_CONFIDENCE,
        "source": "aliyun_funasr_diarization",
    }


def _align_one_subtitle_to_aliyun_segment(
    subtitle: Mapping[str, Any],
    aliyun_segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """把一条 SRT 字幕对齐到重叠比例最高的阿里云 speaker segment。"""
    start = _to_seconds(subtitle.get("start"))
    end = _to_seconds(subtitle.get("end"))
    if end <= start:
        return None

    best_segment: dict[str, Any] | None = None
    best_ratio = 0.0
    for segment in aliyun_segments:
        ratio = _overlap_ratio(
            start,
            end,
            _to_seconds(segment.get("start")),
            _to_seconds(segment.get("end")),
        )
        if ratio > best_ratio:
            best_ratio = ratio
            best_segment = dict(segment)

    if best_segment is None or best_ratio <= 0:
        return None
    best_segment["overlap_ratio"] = round(best_ratio, 4)
    return best_segment


def _format_aligned_speaker_line(
    subtitle: Mapping[str, Any],
    aligned: Mapping[str, Any],
    *,
    speaker_role_map: Mapping[str, str],
    speaker_confidence_map: Mapping[str, float],
) -> str:
    """格式化对齐后的 speaker_context 行。"""
    speaker_id = str(aligned.get("speaker_id") or "SPEAKER_UNKNOWN")
    role_name = speaker_role_map.get(speaker_id)
    if role_name:
        speaker = role_name
        confidence = float(speaker_confidence_map.get(speaker_id, aligned.get("confidence", DEFAULT_MAPPED_CONFIDENCE)))
        status = _status_for_mapped_role(confidence)
    else:
        speaker = speaker_id
        confidence = float(aligned.get("confidence", DEFAULT_DIARIZED_CONFIDENCE))
        status = "diarized"

    return "{}~{} | {} | {:.2f} | {}".format(
        _format_time_compact(subtitle.get("start")),
        _format_time_compact(subtitle.get("end")),
        speaker,
        confidence,
        status,
    )


def _status_for_mapped_role(confidence: float) -> str:
    """根据映射角色的置信度输出状态。"""
    if confidence < UNCERTAIN_THRESHOLD:
        return "candidate（存疑）"
    return "confirmed"


def _format_speaker_id(value: Any) -> str:
    """把阿里云 speaker_id 统一为 SPEAKER_00 格式。"""
    if value is None:
        return "SPEAKER_UNKNOWN"
    try:
        number = int(value)
        return "SPEAKER_{:02d}".format(number)
    except (TypeError, ValueError):
        text = str(value)
        if text.startswith("SPEAKER_"):
            return text
        return "SPEAKER_{}".format(text)


def _extract_task_id(task_response_or_id: Mapping[str, Any] | str) -> str:
    """提取 task_id。"""
    if isinstance(task_response_or_id, str):
        return task_response_or_id
    output = task_response_or_id.get("output") or {}
    if isinstance(output, Mapping) and output.get("task_id"):
        return str(output["task_id"])
    if task_response_or_id.get("task_id"):
        return str(task_response_or_id["task_id"])
    return ""


def _response_to_dict(response: Any) -> dict[str, Any]:
    """把 dashscope response 转为 dict。"""
    if isinstance(response, dict):
        return response
    if hasattr(response, "to_dict"):
        data = response.to_dict()
        if isinstance(data, dict):
            return data
    if hasattr(response, "__dict__"):
        return dict(response.__dict__)
    return {"raw_response": str(response)}


def _overlap_ratio(start: float, end: float, other_start: float, other_end: float) -> float:
    """计算两个时间段相对于字幕段的重叠比例。"""
    if end <= start or other_end <= other_start:
        return 0.0
    overlap = max(0.0, min(end, other_end) - max(start, other_start))
    return overlap / max(end - start, 0.001)


def _to_seconds(value: Any) -> float:
    """把秒数或 SRT 时间字符串转为秒。"""
    if isinstance(value, int | float):
        return float(value)
    text = str(value or "").strip().replace(",", ".")
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except ValueError:
        return 0.0


def _format_time_compact(value: Any) -> str:
    """把时间值格式化为 HH:MM:SS。"""
    seconds = max(_to_seconds(value), 0.0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, secs)


def _safe_float(value: Any, *, default: float) -> float:
    """安全转 float。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
