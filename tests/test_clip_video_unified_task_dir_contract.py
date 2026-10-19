# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _legacy_repo_clip_dir() -> Path:
    return PROJECT_ROOT / "storage" / "temp" / "clip_video_unified"


def test_task_pipeline_passes_clip_output_dir_under_job_task_dir() -> None:
    source = (PROJECT_ROOT / "app/services/task.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert 'video_clip_output_dir = utils.task_dir(os.path.join(task_id, "clip_video_unified"))' in source
    assert "output_dir=video_clip_output_dir" in source
    assert "task_id=task_id" in source


def test_clip_video_unified_default_uses_workspace_temp_not_repo_storage() -> None:
    source = (PROJECT_ROOT / "app/services/clip_video.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    old_tuple = ", ".join([repr(part) for part in ("storage", "temp", "clip_video_unified")])
    assert old_tuple not in source
    assert 'utils.temp_dir(os.path.join("clip_video_unified", task_id))' in source


def test_legacy_repo_clip_video_unified_temp_dir_is_removed() -> None:
    assert not _legacy_repo_clip_dir().exists()
