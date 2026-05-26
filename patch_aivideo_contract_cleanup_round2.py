# -*- coding: utf-8 -*-
from __future__ import annotations

"""
patch_aivideo_contract_cleanup_round2.py

Round-2 aivideo contract cleanup after the old selected-highlight visual
postprocessor was removed. This patch does not change any two-round prompt
text. It fixes runtime contracts, official API field mapping, and tests that
still depend on external local files or old movie_story entry behavior.
"""

import argparse
import datetime as _dt
import shutil
from pathlib import Path


UNIFIED_ENTRY = '''# -*- coding: utf-8 -*-
from __future__ import annotations

"""
unified_entry.py

统一前端编辑入口。负责把前端 movie_story / highlight 请求路由到当前正式主流程。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.unified_entry",
    "entry_points": [
        "run_unified_edit_request",
        "run_movie_story_request",
        "run_highlight_request",
    ],
    "called_by": [
        "app.services.local_job_runner",
        "app.api.routers.jobs",
    ],
    "decisions": [
        "2026-05: movie_story_script 主流程只允许 two_round / two_round_visual；旧 native/legacy 不再作为主流程或 fallback。",
        "2026-05: highlight_edit 产品链仍通过 run_highlight_edit_engine 路由，和 movie_story_script 主流程分离。",
    ],
    "pending": [
        "长视频拆多个短视频产品链稳定后，在此处增加独立显式入口，不能复用旧 native/legacy movie_story。",
        "legacy/native 中仍有价值的确定性模块迁移完成后，将旧目录移入项目回收站。",
    ],
    "ai_constraints": [
        "禁止恢复 old native/legacy movie_story 主流程。",
        "禁止把 two_round_visual 缺配置时降级到 two_round。",
        "禁止修改基础双轮链和视觉增强链的两轮提示词内容，除非用户明确要求。",
    ],
}

import os
from typing import Any, Callable, Dict, Optional

from loguru import logger

from app.services.movie_story.edit_modes import (
    ENTRY_HIGHLIGHT_SCRIPT,
    ENTRY_MOVIE_STORY_SCRIPT,
    RAW_HIGHLIGHT,
    engine_mode_for_highlight,
    resolve_unified_mode,
)
from app.services.movie_story.edit_result import UnifiedEditResult
from app.services.movie_story.engines import run_highlight_edit_engine
from app.services.movie_story.two_round_feature_modes import run_movie_story_two_round_feature_mode

ProgressCallback = Optional[Callable[[int, str], None]]

_ALLOWED_MOVIE_STORY_MODES = {"two_round", "two_round_visual"}
_DISABLED_OLD_MOVIE_STORY_MODES = {
    "native",
    "legacy",
    "native_runtime",
    "legacy_understanding",
    "subtitle_first_pipeline",
}


def movie_story_scene_overrides_from_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve advanced movie-story controls at the unified API boundary."""

    overrides: Dict[str, Any] = {
        "target_duration_minutes": int(request.get("target_duration_minutes", 8) or 8),
        "narrative_strategy": str(request.get("narrative_strategy", "chronological") or "chronological"),
        "accuracy_priority": str(request.get("accuracy_priority", "high") or "high"),
        "highlight_only": bool(request.get("highlight_only", False)),
        "highlight_selectivity": str(request.get("highlight_selectivity", "balanced") or "balanced"),
        "video_title": str(request.get("video_theme", "") or request.get("video_title", "") or ""),
        "short_name": str(request.get("video_theme", "") or request.get("video_title", "") or ""),
        "temperature": float(request.get("temperature", 0.7) or 0.7),
        "prologue_strategy": str(request.get("prologue_strategy", "speech_first") or "speech_first"),
        "manual_prologue_end_time": str(request.get("manual_prologue_end_time", "") or ""),
        "movie_story_strategy": str(request.get("movie_story_strategy", "") or ""),
        "skip_llm": bool(request.get("skip_llm", False)),
    }
    passthrough_keys = [
        "movie_story_narration_llm_mode",
        "narration_llm_mode",
        "movie_story_narration_llm_max_segments",
        "movie_story_enable_global_llm",
        "movie_story_enable_segment_llm",
        "movie_story_enable_story_validation_llm",
        "movie_story_enable_highlight_plan_llm",
        "movie_story_enable_narration_validation_llm",
        "movie_story_disable_llm_highlight_plan",
        "movie_story_highlight_plan_max_candidates",
        "movie_story_typed_selector_error_policy",
        "movie_story_audit_export_clips",
        "movie_story_audit_keep_runs",
        "movie_story_audit_keep_stages",
        "movie_story_audit_include_legacy_stages",
        "movie_story_audit_clip_stages",
        "movie_story_audit_max_clips_per_stage",
        "boundary_merge_window_sec",
        "clip_match_tolerance_seconds",
        "scene_threshold",
        "min_scene_len",
        "skip_llm",
    ]
    for key in passthrough_keys:
        if key in request and request.get(key) is not None:
            overrides[key] = request.get(key)
    return overrides


def run_unified_edit_request(
    *,
    entry: str,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
    output_script_path: str = "",
) -> Dict[str, Any]:
    """Run a front-end edit request through one normalized movie-story entry layer."""

    mode_info = resolve_unified_mode(entry, request)
    logger.info("unified edit request: entry={} mode={}", mode_info.entry, mode_info.mode)

    if mode_info.entry == ENTRY_MOVIE_STORY_SCRIPT:
        payload = run_movie_story_request(
            request=request,
            progress_callback=progress_callback,
            output_script_path=output_script_path,
        )
    elif mode_info.entry == ENTRY_HIGHLIGHT_SCRIPT:
        payload = run_highlight_request(
            request=request,
            progress_callback=progress_callback,
        )
    else:
        payload = {
            "success": False,
            "error": f"unsupported_unified_entry:{mode_info.entry}",
            "script_items": [],
            "warnings": [],
        }

    result = UnifiedEditResult.from_payload(entry=mode_info.entry, mode=mode_info.mode, payload=payload)
    normalized = result.to_payload()
    normalized.setdefault("unified_mode_info", mode_info.as_dict())
    return normalized


def run_highlight_request(
    *,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
) -> Dict[str, Any]:
    """Run the highlight edit product path through its separate engine boundary."""

    mode_info = resolve_unified_mode(ENTRY_HIGHLIGHT_SCRIPT, request)
    prefer_raw_audio = bool(request.get("prefer_raw_audio", True)) or mode_info.mode == RAW_HIGHLIGHT
    return run_highlight_edit_engine(
        video_path=str(request.get("video_path", "") or ""),
        mode=engine_mode_for_highlight(mode_info.mode),
        target_duration_seconds=int(request.get("target_duration_seconds", 480) or 480),
        movie_title=str(request.get("movie_title", "") or ""),
        highlight_profile=str(request.get("highlight_profile", "auto") or "auto"),
        subtitle_path=str(request.get("subtitle_path", "") or ""),
        narration_text=str(request.get("narration_text", "") or ""),
        narration_audio_path=str(request.get("narration_audio_path", "") or ""),
        prefer_raw_audio=prefer_raw_audio,
        visual_mode="off" if bool(request.get("skip_llm", False)) else str(request.get("visual_mode", "auto") or "auto"),
        regenerate_subtitle=bool(request.get("regenerate_subtitle", False)),
        subtitle_backend=str(request.get("subtitle_backend", "") or ""),
        engine_backend=str(request.get("engine_backend", "") or ""),
        edit_engine_backend=str(request.get("edit_engine_backend", "") or ""),
        highlight_engine_backend=str(request.get("highlight_engine_backend", "") or ""),
        progress_callback=progress_callback,
    )


def run_movie_story_request(
    *,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
    output_script_path: str = "",
) -> Dict[str, Any]:
    """Run one of the current movie_story mainflows; old native/legacy are rejected."""

    if not output_script_path:
        output_script_path = str(request.get("output_script_path", "") or "")

    movie_story_mode = _resolve_movie_story_mode(request)
    if movie_story_mode in _ALLOWED_MOVIE_STORY_MODES:
        return run_movie_story_two_round_feature_mode(
            request=request,
            progress_callback=progress_callback,
            output_script_path=output_script_path,
            visual_enabled=movie_story_mode == "two_round_visual",
        )
    if movie_story_mode in _DISABLED_OLD_MOVIE_STORY_MODES:
        raise RuntimeError(
            "old native/legacy movie_story mainflow is disabled; "
            "use two_round, two_round_visual, or the explicit long-video-to-short-video product path."
        )
    raise ValueError(f"unsupported_movie_story_mode:{movie_story_mode}")


def _resolve_movie_story_mode(request: Dict[str, Any]) -> str:
    """Resolve the explicit current movie_story mode without legacy fallback."""

    for key in ("movie_story_mode", "movie_story_feature_mode", "movie_story_strategy"):
        value = str(request.get(key) or "").strip().lower()
        if value:
            return value
    return "two_round"


def build_task_output_script_path(*, request: Dict[str, Any], task_dir: str) -> str:
    """Build the output path used by local job runner for movie_story script jobs."""

    requested = str(request.get("output_script_path", "") or "").strip()
    if requested:
        return requested
    return os.path.join(task_dir, "movie_story_script.json")
'''

TWO_ROUND_VISUAL_TEST = r'''# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.movie_story import two_round_visual_narration as visual


SRT_TEXT = """1
00:00:01,000 --> 00:00:03,000
你为什么回来？

2
00:00:08,000 --> 00:00:12,000
我不是来找你的。
"""


def test_generate_two_round_visual_narration_items_uses_visual_first_round(tmp_path, monkeypatch) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    monkeypatch.setattr(
        visual,
        "detect_shot_boundaries",
        lambda *args, **kwargs: [{"shot_id": "shot_0001", "start": 0.0, "end": 65.0}],
    )
    monkeypatch.setattr(
        visual,
        "build_scene_segments",
        lambda *args, **kwargs: [
            {
                "scene_id": "scene_0001",
                "start": 0.0,
                "end": 65.0,
                "duration": 65.0,
                "shot_ids": ["shot_0001"],
                "subtitle_count": 1,
            }
        ],
    )
    captured_focus_kwargs: dict[str, Any] = {}

    def fake_build_visual_focus_segments(**kwargs: Any) -> list[dict[str, Any]]:
        captured_focus_kwargs.update(kwargs)
        return [
            {
                "segment_id": "focus_001",
                "start": 0.0,
                "end": 65.0,
                "source": "manual",
                "reason": "unit test focus segment",
                "scene_id": "scene_0001",
            }
        ]

    monkeypatch.setattr(visual, "build_visual_focus_segments", fake_build_visual_focus_segments)
    monkeypatch.setattr(
        visual,
        "sample_keyframes_for_scene_context",
        lambda *args, **kwargs: [
            {
                "frame_id": "scene_frame",
                "timestamp": 1.0,
                "sampling_stage": "scene_context_low_density",
                "frame_path": str(tmp_path / "scene.jpg"),
            }
        ],
    )
    monkeypatch.setattr(
        visual,
        "sample_keyframes_for_visual_focus_segments",
        lambda *args, **kwargs: [
            {
                "frame_id": "focus_frame",
                "timestamp": 2.0,
                "sampling_stage": "visual_focus_detail",
                "frame_path": str(tmp_path / "focus.jpg"),
            }
        ],
    )
    (tmp_path / "scene.jpg").write_bytes(b"image")
    (tmp_path / "focus.jpg").write_bytes(b"image")

    def fake_first_round(**kwargs: Any) -> str:
        assert kwargs["image_paths"]
        assert "【视觉片段抽帧】" in kwargs["prompt"]
        assert "【视觉片段详细抽帧】" in kwargs["prompt"]
        assert "visual_focus_segments 不是 AI 推荐高光" not in kwargs["prompt"]
        return "故事段一：人物关系已经根据画面校正。\n步骤四：主线候选。\n步骤五：推荐主线。"

    def fake_text(prompt: str, *, api_key: str, base_url: str, model: str, timeout: int) -> str:
        assert "结构分析" in prompt
        return "【正式文案】\n**开场**\n[00:01 ~ 01:05]\n这是一段正式解说。"

    monkeypatch.setattr(visual, "call_multimodal_first_round_strict", fake_first_round)
    monkeypatch.setattr(visual, "_call_chat_completion", fake_text)

    items, metadata = visual.generate_two_round_visual_narration_items(
        raw_srt_text=SRT_TEXT,
        request={
            "video_path": str(video_path),
            "vision_api_key": "vk",
            "vision_model": "gemini/gemini-test",
            "movie_story_visual_focus_segments": [{"start": 1.0, "end": 12.0, "reason": "manual focus"}],
        },
        output_dir=tmp_path,
        text_api_key="tk",
        text_base_url="",
        text_model="tm",
        style="general",
    )

    assert items
    assert captured_focus_kwargs["manual_segments"] == [{"start": 1.0, "end": 12.0, "reason": "manual focus"}]
    assert Path(metadata["visual_context_path"]).exists()
    assert Path(metadata["analysis_prompt_path"]).exists()
'''

UNIFIED_TEST = r'''# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.movie_story import edit_modes
from app.services.movie_story import unified_entry


def test_resolve_unified_mode_for_movie_story_request() -> None:
    mode = edit_modes.resolve_unified_mode("movie-story-script", {"target_duration_minutes": 6, "highlight_only": False})
    assert mode.entry == edit_modes.ENTRY_MOVIE_STORY_SCRIPT
    assert mode.mode == edit_modes.MOVIE_STORY
    assert mode.generates_narration is True
    assert mode.uses_external_narration is False


def test_resolve_unified_mode_promotes_external_narration_to_narrated_highlight() -> None:
    mode = edit_modes.resolve_unified_mode(
        "highlight-script",
        {"mode": "highlight_recut", "narration_text": "Opening hook. Then reveal."},
    )
    assert mode.entry == edit_modes.ENTRY_HIGHLIGHT_SCRIPT
    assert mode.mode == edit_modes.NARRATED_HIGHLIGHT_EDIT
    assert mode.uses_external_narration is True


def test_movie_story_overrides_preserve_advanced_controls() -> None:
    overrides = unified_entry.movie_story_scene_overrides_from_request(
        {
            "target_duration_minutes": 9,
            "video_theme": "Test Movie",
            "highlight_selectivity": "strict",
            "movie_story_enable_highlight_plan_llm": True,
            "scene_threshold": 31,
        }
    )
    assert overrides["target_duration_minutes"] == 9
    assert overrides["video_title"] == "Test Movie"
    assert overrides["short_name"] == "Test Movie"
    assert overrides["highlight_selectivity"] == "strict"
    assert overrides["movie_story_enable_highlight_plan_llm"] is True
    assert overrides["scene_threshold"] == 31


def test_run_highlight_request_normalizes_raw_highlight(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run_highlight_edit_engine(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": [], "composition_plan": {"mode": kwargs["mode"], "segments": []}}

    monkeypatch.setattr(unified_entry, "run_highlight_edit_engine", fake_run_highlight_edit_engine)

    result = unified_entry.run_unified_edit_request(
        entry="highlight_script",
        request={"video_path": "demo.mp4", "mode": "raw_highlight", "prefer_raw_audio": False},
    )

    assert result["success"] is True
    assert result["unified_entry"] == edit_modes.ENTRY_HIGHLIGHT_SCRIPT
    assert result["unified_mode"] == edit_modes.RAW_HIGHLIGHT
    assert captured["mode"] == edit_modes.HIGHLIGHT_RECUT
    assert captured["prefer_raw_audio"] is True


def test_run_movie_story_request_uses_current_two_round_mainflow(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run_movie_story_two_round_feature_mode(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "script_items": [{"start": 1.0, "end": 2.0, "text": "Demo"}],
            "script_path": kwargs["output_script_path"],
            "warnings": [],
        }

    monkeypatch.setattr(unified_entry, "run_movie_story_two_round_feature_mode", fake_run_movie_story_two_round_feature_mode)

    result = unified_entry.run_unified_edit_request(
        entry="movie_story_script",
        request={
            "video_path": "demo.mp4",
            "video_theme": "Demo",
            "raw_srt_text": "1\n00:00:01,000 --> 00:00:03,000\nhello",
            "movie_story_mode": "two_round_visual",
        },
        output_script_path="E:/tmp/movie_story_script.json",
    )

    assert result["success"] is True
    assert result["unified_entry"] == edit_modes.ENTRY_MOVIE_STORY_SCRIPT
    assert result["unified_mode"] == edit_modes.MOVIE_STORY
    assert result["script_path"] == "E:/tmp/movie_story_script.json"
    assert captured["output_script_path"] == "E:/tmp/movie_story_script.json"
    assert captured["visual_enabled"] is True


@pytest.mark.parametrize("old_mode", ["native", "legacy", "native_runtime", "legacy_understanding"])
def test_run_movie_story_request_rejects_old_native_legacy_mainflow(old_mode: str) -> None:
    with pytest.raises(RuntimeError, match="old native/legacy movie_story mainflow is disabled"):
        unified_entry.run_movie_story_request(
            request={"video_path": "demo.mp4", "movie_story_mode": old_mode},
            output_script_path="E:/tmp/movie_story_script.json",
        )
'''

FUNASR_TEST = '''# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_funasr_speaker_diarization.py

测试正式 Fun-ASR speaker diarization 服务。
"""

import unittest
from pathlib import Path
from typing import Any

from app.services.movie_story import funasr_speaker_diarization


class FakeBailianService:
    """模拟现有 asr_bailian 服务。"""

    def recognize_filetrans_audio(self, **kwargs: Any) -> dict:
        """返回带 speaker_id 的阿里 transcription JSON。"""
        assert kwargs["model"] == "fun-asr"
        assert kwargs["diarization_enabled"] is True
        return {
            "raw_result": {
                "transcripts": [
                    {
                        "sentences": [
                            {
                                "begin_time": 284000,
                                "end_time": 288000,
                                "text": "我要天天吃大饼",
                                "speaker_id": 0,
                            },
                            {
                                "begin_time": 464000,
                                "end_time": 472000,
                                "text": "欠税不交",
                                "speaker_id": 1,
                            },
                        ]
                    }
                ]
            }
        }


class TestFunasrSpeakerDiarization(unittest.TestCase):
    """正式 Fun-ASR speaker diarization 服务测试。"""

    def test_build_preview_from_audio(self) -> None:
        """能复用 asr_bailian 结果生成 speaker preview。"""
        audio_path = Path(__file__).parent / "fixtures" / "funasr_test.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(_minimal_wav_bytes())

        original = funasr_speaker_diarization._create_bailian_asr_service
        funasr_speaker_diarization._create_bailian_asr_service = lambda: FakeBailianService()
        try:
            payload = funasr_speaker_diarization.build_funasr_speaker_preview_from_audio(str(audio_path))
        finally:
            funasr_speaker_diarization._create_bailian_asr_service = original

        self.assertEqual(payload["provider"], "aliyun_funasr")
        self.assertEqual(payload["speaker_preview"]["speaker_count"], 2)
        self.assertEqual(payload["speaker_segments_count"], 2)


def _minimal_wav_bytes() -> bytes:
    """Return a tiny valid WAV container for tests that only require an existing audio path."""
    return (
        b"RIFF"
        + (36).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (0).to_bytes(4, "little")
    )


if __name__ == "__main__":
    unittest.main()
'''

MODE_NORMALIZATION_TEST = r'''# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_movie_story_mode_normalization.py

Guards that stale legacy/native labels do not silently migrate into current
movie_story mainflows.
"""

import pytest

from app.services.movie_story.unified_entry import run_movie_story_request


@pytest.mark.parametrize("old_mode", ["legacy_understanding", "native_runtime", "legacy", "native"])
def test_old_movie_story_modes_are_disabled(old_mode: str) -> None:
    with pytest.raises(RuntimeError, match="old native/legacy movie_story mainflow is disabled"):
        run_movie_story_request(
            request={"movie_story_mode": old_mode, "video_path": "demo.mp4"},
            output_script_path="E:/tmp/movie_story_script.json",
        )


def test_unknown_mode_still_reaches_dispatcher_as_error() -> None:
    with pytest.raises(ValueError, match="unsupported_movie_story_mode:unknown_mode"):
        run_movie_story_request(
            request={"movie_story_mode": "unknown_mode", "video_path": "demo.mp4"},
            output_script_path="E:/tmp/movie_story_script.json",
        )
'''


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _replace_if_present(path: Path, old: str, new: str) -> bool:
    text = _read(path)
    if old not in text:
        return False
    _write(path, text.replace(old, new))
    return True


def _insert_header(path: Path) -> bool:
    text = _read(path)
    if text.startswith("# -*- coding: utf-8 -*-\nfrom __future__ import annotations"):
        return False
    if text.startswith("from __future__ import annotations\n"):
        _write(path, "# -*- coding: utf-8 -*-\n" + text)
        return True
    raise RuntimeError(f"Cannot safely insert standard header in {path}")


def _backup_files(project: Path, files: list[Path]) -> Path:
    backup_root = project / ".patch_backups" / f"contract_cleanup_round2_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    for path in files:
        backup_path = backup_root / path.relative_to(project)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
    return backup_root


def apply_patch(project: Path, *, dry_run: bool) -> list[str]:
    files = [
        project / "app/api/schemas/jobs.py",
        project / "web/src/lib/api.ts",
        project / "web/src/pages/editor/Material.tsx",
        project / "web/src/pages/editor/Analysis.tsx",
        project / "app/services/movie_story/two_round_visual_narration.py",
        project / "app/services/movie_story/unified_entry.py",
        project / "tests/movie_story/test_two_round_visual_narration.py",
        project / "tests/movie_story/test_funasr_speaker_diarization.py",
        project / "tests/test_movie_story_unified_entry.py",
        project / "tests/movie_story/test_movie_story_mode_normalization.py",
    ]
    actions: list[str] = []
    if dry_run:
        for path in files:
            actions.append(f"would update: {path.relative_to(project)}")
        return actions

    backup_root = _backup_files(project, files)

    jobs = project / "app/api/schemas/jobs.py"
    if _insert_header(jobs):
        actions.append("modify: app/api/schemas/jobs.py | add standard file header")

    api_ts = project / "web/src/lib/api.ts"
    api_text = _read(api_ts)
    if "movie_story_visual_focus_segments?: Array<Record<string, unknown>>;" not in api_text:
        _replace_if_present(
            api_ts,
            "  movie_story_mode?: 'two_round' | 'two_round_visual';\n  movie_story_strategy?: 'two_round' | 'two_round_visual' | string;\n  visual_mode?: string;\n",
            "  movie_story_mode?: 'two_round' | 'two_round_visual';\n  movie_story_feature_mode?: 'two_round' | 'two_round_visual';\n  movie_story_strategy?: 'two_round' | 'two_round_visual' | string;\n  movie_story_visual_focus_segments?: Array<Record<string, unknown>>;\n  visual_mode?: string;\n",
        )
        actions.append("modify: web/src/lib/api.ts | add official visual focus request field")
    api_text = _read(api_ts)
    if "const movieStoryMode = request.movie_story_mode || request.movie_story_feature_mode || normalizeMovieStoryStrategy(request.movie_story_strategy);" not in api_text:
        _replace_if_present(
            api_ts,
            "export async function createMovieStoryJob(request: MovieStoryRequest): Promise<JobAcceptedResponse> {\n  return requestJson<JobAcceptedResponse>('/api/v1/jobs/movie-story-script', {",
            "export async function createMovieStoryJob(request: MovieStoryRequest): Promise<JobAcceptedResponse> {\n  const movieStoryMode = request.movie_story_mode || request.movie_story_feature_mode || normalizeMovieStoryStrategy(request.movie_story_strategy);\n  return requestJson<JobAcceptedResponse>('/api/v1/jobs/movie-story-script', {",
        )
        actions.append("modify: web/src/lib/api.ts | resolve one explicit movie_story mode")
    if _replace_if_present(
        api_ts,
        "        movie_story_mode: request.movie_story_mode || 'two_round',\n        movie_story_feature_mode: request.movie_story_mode || 'two_round',\n        movie_story_strategy: normalizeMovieStoryStrategy(request.movie_story_strategy),\n",
        "        movie_story_mode: movieStoryMode,\n        movie_story_feature_mode: movieStoryMode,\n        movie_story_strategy: movieStoryMode,\n        movie_story_visual_focus_segments: request.movie_story_visual_focus_segments || [],\n",
    ):
        actions.append("modify: web/src/lib/api.ts | send official focus segments and avoid mode mismatch")

    if _replace_if_present(
        project / "app/services/movie_story/two_round_visual_narration.py",
        '        manual_segments=list(request.get("visual_focus_segments") or []),\n',
        '        manual_segments=list(request.get("movie_story_visual_focus_segments") or []),\n',
    ):
        actions.append("modify: app/services/movie_story/two_round_visual_narration.py | use official API field")

    if _replace_if_present(
        project / "web/src/pages/editor/Material.tsx",
        "        movie_story_strategy: normalizeMovieStoryStrategy(config.movieStoryStrategy),\n      movie_story_feature_mode: normalizeMovieStoryStrategy(config.movieStoryStrategy),\n        movie_story_mode: normalizeMovieStoryStrategy(config.movieStoryStrategy),\n",
        "        movie_story_strategy: normalizeMovieStoryStrategy(config.movieStoryStrategy),\n        movie_story_feature_mode: normalizeMovieStoryStrategy(config.movieStoryStrategy),\n        movie_story_mode: normalizeMovieStoryStrategy(config.movieStoryStrategy),\n",
    ):
        actions.append("modify: web/src/pages/editor/Material.tsx | normalize indentation")

    if _replace_if_present(
        project / "web/src/pages/editor/Analysis.tsx",
        "        movie_story_strategy: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),\n      movie_story_feature_mode: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),\n        movie_story_mode: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),\n",
        "        movie_story_strategy: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),\n        movie_story_feature_mode: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),\n        movie_story_mode: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),\n",
    ):
        actions.append("modify: web/src/pages/editor/Analysis.tsx | normalize indentation")

    _write(project / "app/services/movie_story/unified_entry.py", UNIFIED_ENTRY)
    actions.append("modify: app/services/movie_story/unified_entry.py | standard header, __CONTEXT__, explicit current mainflow only")

    _write(project / "tests/movie_story/test_two_round_visual_narration.py", TWO_ROUND_VISUAL_TEST)
    actions.append("modify: tests/movie_story/test_two_round_visual_narration.py | protect official focus field mapping")

    _write(project / "tests/movie_story/test_funasr_speaker_diarization.py", FUNASR_TEST)
    actions.append("modify: tests/movie_story/test_funasr_speaker_diarization.py | remove external E:/ wav dependency")

    _write(project / "tests/test_movie_story_unified_entry.py", UNIFIED_TEST)
    actions.append("modify: tests/test_movie_story_unified_entry.py | update tests to current movie_story mainflow")

    _write(project / "tests/movie_story/test_movie_story_mode_normalization.py", MODE_NORMALIZATION_TEST)
    actions.append("modify: tests/movie_story/test_movie_story_mode_normalization.py | reject old native/legacy labels")

    actions.append(f"backup_root: {backup_root}")
    return actions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    project = Path(args.project).resolve()
    actions = apply_patch(project, dry_run=args.dry_run)
    print(f"[{'DRY-RUN' if args.dry_run else 'APPLIED'}] project: {project}")
    for action in actions:
        print(f"- {action}")


if __name__ == "__main__":
    main()
