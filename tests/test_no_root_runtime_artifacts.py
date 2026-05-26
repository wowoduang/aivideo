# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from app.repositories.workbench_state_repository import WorkbenchStateRepository
from app.services.movie_story import prompt_strategy_archive
from app.services.movie_story.two_round_narration import debug_dir
from app.utils import workspace


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_default_runtime_paths_do_not_point_to_project_root_artifact_dirs() -> None:
    """默认运行产物路径不能再指向项目根目录 workspace/reports/storage/.-workspace。"""
    project = _project_root()
    forbidden = {
        project / "workspace",
        project / "reports",
        project / "storage",
        project / ".-workspace",
    }

    candidates = [
        WorkbenchStateRepository().base_dir,
        debug_dir(),
        prompt_strategy_archive.strategy_archive_path().parent,
        Path(workspace.workspace_dir(create=True)),
        Path(workspace.temp_dir("contract_guard", create=True)),
        Path(workspace.analysis_dir("contract_guard", create=True)),
    ]

    for candidate in candidates:
        resolved = candidate.resolve()
        assert all(
            resolved != root.resolve() and root.resolve() not in resolved.parents
            for root in forbidden
        ), f"runtime path still points inside project root artifact dir: {resolved}"
