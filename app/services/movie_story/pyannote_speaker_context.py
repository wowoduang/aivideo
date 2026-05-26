# -*- coding: utf-8 -*-
from __future__ import annotations

"""
pyannote_speaker_context.py

使用 pyannote diarization 结果生成 raw_srt 第一轮可直接填充的 {speaker_context} 文本。
字幕只作为主时间轴和对齐容器，不从字幕文本中解析或猜测角色名。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.pyannote_speaker_context",
    "entry_points": [
        "build_speaker_context_text_from_segments",
        "run_pyannote_diarization",
        "build_pyannote_speaker_context_text",
    ],
    "called_by": [
        "movie_story/two_round_narration.py",
        "movie_story/raw_srt_context_builder.py",
    ],
    "decisions": [
        "2026-05: {speaker_context} 只能来自音频侧说话人识别证据；字幕只用于时间对齐。",
        "2026-05: 当前主线选择 pyannote diarization；Silero 只作为未来可选 VAD 前置。",
        "2026-05: 没有音频识别证据时输出暂无可靠说话人识别结果，不从字幕猜人名。",
    ],
    "pending": [
        "接入角色声纹库 embedding 匹配结果。",
        "接入前端/项目级 SPEAKER_XX 到角色名的人工映射配置。",
        "必要时增加 Silero VAD 前置清洗，但不得替代 pyannote diarization。",
    ],
    "ai_constraints": [
        "禁止使用字幕文本解析角色名。",
        "禁止根据称呼关系或剧情上下文猜说话人。",
        "禁止把 pyannote 的 speech segment 时间轴作为下游主时间轴。",
        "禁止没有音频证据时输出角色名。",
    ],
}

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass(frozen=True)
class SpeechSegment:
    """音频侧说话人分离片段。"""

    start: float
    end: float
    speaker_id: str
    confidence: float = 0.0
    source: str = "pyannote"


@dataclass(frozen=True)
class SubtitleSegment:
    """SRT 主时间轴字幕片段。"""

    start: float
    end: float
    text: str = ""


@dataclass(frozen=True)
class RoleMapping:
    """SPEAKER_XX 到角色名的映射。"""

    role_name: str
    confidence: float = 1.0
    source: str = "manual_map"


def build_pyannote_speaker_context_text(
    media_path: str | Path,
    subtitle_segments: Sequence[Mapping[str, Any]],
    *,
    hf_token: str | None = None,
    speaker_role_map: Mapping[str, str | Mapping[str, Any]] | None = None,
    model_id: str = "pyannote/speaker-diarization-3.1",
    device: str = "auto",
    tmp_dir: str | Path | None = None,
    min_overlap_ratio: float = 0.2,
) -> str:
    """
    从视频/音频运行 pyannote diarization，并生成第一轮提示词用的 {speaker_context}。

    规则：
        - 字幕只用于对齐时间，不解析人名。
        - 如果 speaker_role_map 没有映射，输出 SPEAKER_00 这类 ID。
        - 如果没有可靠音频结果，输出“暂无可靠说话人识别结果。”。
    """
    audio_path = ensure_wav_audio(media_path, tmp_dir=tmp_dir)
    speech_segments = run_pyannote_diarization(
        audio_path,
        hf_token=hf_token,
        model_id=model_id,
        device=device,
    )
    return build_speaker_context_text_from_segments(
        subtitle_segments,
        speech_segments=speech_segments,
        speaker_role_map=speaker_role_map,
        min_overlap_ratio=min_overlap_ratio,
    )


def run_pyannote_diarization(
    audio_path: str | Path,
    *,
    hf_token: str | None = None,
    model_id: str = "pyannote/speaker-diarization-3.1",
    device: str = "auto",
) -> list[SpeechSegment]:
    """运行 pyannote speaker diarization，返回音频侧 speech segments。"""
    token = hf_token or os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("缺少 Hugging Face token：请设置 HUGGINGFACE_TOKEN 或传入 hf_token。")

    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError("缺少 pyannote.audio：请先安装 pip install pyannote.audio。") from exc

    pipeline = Pipeline.from_pretrained(model_id, use_auth_token=token)
    if device != "cpu":
        _try_move_pipeline_to_device(pipeline, device=device)

    diarization = pipeline(str(audio_path))
    segments: list[SpeechSegment] = []
    for turn, _track, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            SpeechSegment(
                start=float(turn.start),
                end=float(turn.end),
                speaker_id=str(speaker),
                confidence=1.0,
                source="pyannote",
            )
        )
    logger.info("pyannote diarization 完成: audio={}, segments={}", audio_path, len(segments))
    return segments


def ensure_wav_audio(media_path: str | Path, *, tmp_dir: str | Path | None = None) -> Path:
    """确保输入是 16kHz mono wav；视频文件会用 ffmpeg 提取音频。"""
    source = Path(media_path)
    if not source.exists():
        raise FileNotFoundError("媒体文件不存在: {}".format(source))
    if source.suffix.lower() == ".wav":
        return source

    target_dir = Path(tmp_dir) if tmp_dir is not None else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "{}_pyannote_16k_mono.wav".format(source.stem)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(target),
    ]
    logger.info("提取 pyannote 音频: {}", " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg 提取音频失败: {}".format(result.stderr.strip()))
    return target


def build_speaker_context_text_from_segments(
    subtitle_segments: Sequence[Mapping[str, Any]],
    *,
    speech_segments: Sequence[SpeechSegment | Mapping[str, Any]],
    speaker_role_map: Mapping[str, str | Mapping[str, Any]] | None = None,
    min_overlap_ratio: float = 0.2,
    max_lines: int = 260,
) -> str:
    """
    把音频侧 speech_segments 对齐到 SRT 主时间轴，生成最终 {speaker_context} 文本。

    输出格式：
        00:04:44~00:04:48 | 朱重八 | 0.95 | confirmed
        00:04:48~00:04:52 | SPEAKER_00 | 0.86 | diarized
        00:07:52~00:08:00 | 母亲 | 0.65 | candidate（存疑）
    """
    subtitles = [_subtitle_from_mapping(item) for item in subtitle_segments]
    speeches = [_speech_from_any(item) for item in speech_segments]
    role_map = _normalize_role_map(speaker_role_map or {})

    lines: list[str] = []
    for subtitle in subtitles:
        match = find_best_speech_for_subtitle(subtitle, speeches)
        if match is None:
            continue
        speech, overlap_ratio = match
        if overlap_ratio < min_overlap_ratio:
            continue
        speaker_name, confidence, status = _resolve_speaker_label(speech, role_map, overlap_ratio)
        lines.append(
            "{}~{} | {} | {:.2f} | {}".format(
                _format_time_compact(subtitle.start),
                _format_time_compact(subtitle.end),
                speaker_name,
                confidence,
                status,
            )
        )
        if len(lines) >= max_lines:
            lines.append("……（说话人识别结果过长，已截断）")
            break

    if not lines:
        return "暂无可靠说话人识别结果。"
    return "\n".join(_merge_adjacent_lines(lines))


def find_best_speech_for_subtitle(
    subtitle: SubtitleSegment,
    speech_segments: Sequence[SpeechSegment],
) -> tuple[SpeechSegment, float] | None:
    """为一条字幕找重叠比例最高的音频侧说话人片段。"""
    best: SpeechSegment | None = None
    best_ratio = 0.0
    for speech in speech_segments:
        ratio = _overlap_ratio(subtitle.start, subtitle.end, speech.start, speech.end)
        if ratio > best_ratio:
            best = speech
            best_ratio = ratio
    if best is None:
        return None
    return best, best_ratio


def _resolve_speaker_label(
    speech: SpeechSegment,
    role_map: Mapping[str, RoleMapping],
    overlap_ratio: float,
) -> tuple[str, float, str]:
    """把 SPEAKER_XX 解析为最终显示名、置信度和状态。"""
    mapping = role_map.get(speech.speaker_id)
    if mapping is None:
        confidence = _clamp_confidence(speech.confidence or overlap_ratio)
        return speech.speaker_id, confidence, "diarized"

    confidence = _clamp_confidence(min(mapping.confidence, speech.confidence or 1.0))
    if confidence >= 0.85:
        return mapping.role_name, confidence, "confirmed"
    if confidence >= 0.70:
        return mapping.role_name, confidence, "candidate"
    return mapping.role_name, confidence, "candidate（存疑）"


def _normalize_role_map(raw_map: Mapping[str, str | Mapping[str, Any]]) -> dict[str, RoleMapping]:
    """标准化 SPEAKER_XX 到角色名的映射。"""
    normalized: dict[str, RoleMapping] = {}
    for speaker_id, value in raw_map.items():
        if isinstance(value, str):
            normalized[str(speaker_id)] = RoleMapping(role_name=value, confidence=1.0, source="manual_map")
            continue
        role_name = str(value.get("role_name") or value.get("speaker") or "").strip()
        if not role_name:
            continue
        normalized[str(speaker_id)] = RoleMapping(
            role_name=role_name,
            confidence=_safe_float(value.get("confidence"), default=1.0),
            source=str(value.get("source") or "manual_map"),
        )
    return normalized


def _subtitle_from_mapping(value: Mapping[str, Any]) -> SubtitleSegment:
    """从字幕 dict 构建 SubtitleSegment。"""
    return SubtitleSegment(
        start=_to_seconds(value.get("start")),
        end=_to_seconds(value.get("end")),
        text=str(value.get("text") or value.get("content") or ""),
    )


def _speech_from_any(value: SpeechSegment | Mapping[str, Any]) -> SpeechSegment:
    """从 SpeechSegment 或 dict 构建 SpeechSegment。"""
    if isinstance(value, SpeechSegment):
        return value
    return SpeechSegment(
        start=_to_seconds(value.get("start")),
        end=_to_seconds(value.get("end")),
        speaker_id=str(value.get("speaker_id") or value.get("speaker") or "SPEAKER_UNKNOWN"),
        confidence=_safe_float(value.get("confidence"), default=1.0),
        source=str(value.get("source") or "pyannote"),
    )


def _try_move_pipeline_to_device(pipeline: Any, *, device: str) -> None:
    """尽量把 pyannote pipeline 移到 GPU；失败时继续使用默认设备。"""
    try:
        import torch

        target_device = torch.device("cuda" if device == "auto" and torch.cuda.is_available() else device)
        pipeline.to(target_device)
        logger.info("pyannote pipeline 使用设备: {}", target_device)
    except Exception as exc:
        logger.warning("pyannote pipeline 切换设备失败，使用默认设备: {}", exc)


def _merge_adjacent_lines(lines: list[str]) -> list[str]:
    """当前保留逐句对齐结果；后续可按同角色连续片段合并。"""
    return lines


def _overlap_ratio(start: float, end: float, other_start: float, other_end: float) -> float:
    """计算 speech segment 覆盖字幕段的比例。"""
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


def _format_time_compact(seconds: float) -> str:
    """把秒数格式化为 HH:MM:SS。"""
    seconds = max(float(seconds), 0.0)
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


def _clamp_confidence(value: float) -> float:
    """把置信度限制在 0 到 1。"""
    return round(max(0.0, min(float(value), 1.0)), 4)
