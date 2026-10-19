# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


TARGET_FUNCTIONS = {
    "app/services/movie_story/two_round_narration.py": {
        "write_debug",
        "response_to_text",
        "extract_raw_srt",
        "env_text",
        "build_analysis_prompt",
        "build_writer_prompt",
        "run_two_round_narration_from_prompt",
    },
    "app/services/movie_story/visual_focus_segments.py": {
        "_normalize_manual_segments",
        "_score_scenes",
        "_score_one_scene",
        "_subtitle_structure_score",
        "_select_candidates",
        "_select_top_candidates",
        "_select_coverage_candidates",
        "_first_non_overlapping",
        "_scene_to_focus_segment",
        "_scene_cut_score",
        "_duration_score",
        "_coverage_priority",
        "_audio_overlap_score",
        "_subtitle_gap_score",
        "_overlaps_any",
        "_overlap_ratio",
        "_overlap_seconds",
        "_coverage_bins",
        "_count_turn_markers",
        "_count_punctuation",
        "_sort_segments",
    },
    "app/services/movie_story/two_round_visual_input_packager.py": {
        "_format_scene_context",
        "_format_focus_context",
        "_format_frame_context",
        "build_two_round_visual_input_package",
    },
}


def _function_docstrings(relative_path: str) -> dict[str, str | None]:
    tree = ast.parse((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
    return {
        node.name: ast.get_docstring(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }


def test_active_support_docstring_targets_are_documented() -> None:
    """Round15 目标函数必须有职责 docstring，方便后续拆分引用。"""
    for relative_path, function_names in TARGET_FUNCTIONS.items():
        docstrings = _function_docstrings(relative_path)
        for function_name in function_names:
            assert function_name in docstrings, f"missing function: {relative_path}:{function_name}"
            assert docstrings[function_name], f"missing docstring: {relative_path}:{function_name}"


def test_visual_focus_docstrings_keep_subtitle_as_time_anchor() -> None:
    """视觉重点片段选择注释必须强调字幕是时间锚点，不在本地解读剧情。"""
    docstrings = _function_docstrings("app/services/movie_story/visual_focus_segments.py")
    joined = "\n".join(value or "" for value in docstrings.values())

    assert "时间锚点" in joined
    assert "不解析剧情" in joined or "不做剧情" in joined
    assert "人物关系" in joined


def test_visual_packager_docstrings_keep_first_round_boundary() -> None:
    """视觉输入打包注释必须说明这是第一轮前材料，不是第二轮后旧链路。"""
    docstrings = _function_docstrings("app/services/movie_story/two_round_visual_input_packager.py")
    joined = "\n".join(value or "" for value in docstrings.values())

    assert "第一轮" in joined
    assert "第二轮后" in joined
    assert "最终剪辑片段" in joined
