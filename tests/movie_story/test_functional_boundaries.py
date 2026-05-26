# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.movie_story.functional_boundaries import (
    assert_contract_table_is_consistent,
    assert_new_code_may_reference,
    classify_module_boundary,
    mainflow_modules,
    migration_review_modules,
    module_to_source_path,
    modules_blocked_for_new_runtime,
    source_path_to_module,
    support_modules,
)


def test_contract_table_is_consistent() -> None:
    """契约表不能同时把同一模块标成 active 和 retired。"""
    assert_contract_table_is_consistent()


def test_current_mainflow_modules_are_explicit_and_small() -> None:
    """当前 movie_story 正式主流程只保留基础双轮链和视觉增强链。"""
    assert set(mainflow_modules()) == {
        "app.services.movie_story.two_round_narration",
        "app.services.movie_story.two_round_visual_narration",
    }


def test_visual_support_modules_are_allowed_for_new_code() -> None:
    """视觉增强支撑模块允许被后续重构代码引用。"""
    assert "app.services.movie_story.visual_focus_segments" in support_modules()
    assert "app.services.movie_story.visual_frame_sampler" in support_modules()

    assert_new_code_may_reference(
        "app.services.movie_story.visual_focus_segments",
        reason="视觉增强第一轮前证据选择正式支撑模块",
    )


def test_old_native_movie_story_module_is_blocked_for_new_runtime() -> None:
    """旧 movie_story native 主流程是待退休对象，不能作为新 runtime 依赖。"""
    module = "app.services.movie_story.movie_story_native_engine"
    boundary = classify_module_boundary(module)

    assert module in modules_blocked_for_new_runtime()
    assert boundary.must_not_use_as_fallback
    assert not boundary.can_reference_from_new_code

    with pytest.raises(ValueError, match="movie_story_module_reference_not_allowed"):
        assert_new_code_may_reference(module, reason="不要允许旧主流程回流")


def test_unknown_module_requires_contract_before_new_reference() -> None:
    """未知模块不能无契约接入，必须先说明生产者/消费者和维护边界。"""
    with pytest.raises(ValueError, match="movie_story_module_reference_not_allowed"):
        assert_new_code_may_reference(
            "app.services.movie_story.some_future_module",
            reason="未来新增模块必须先登记契约",
        )


def test_reference_reason_is_required() -> None:
    """引用理由不能为空，避免补丁脚本无说明地接入依赖。"""
    with pytest.raises(ValueError, match="reference_reason_required"):
        assert_new_code_may_reference(
            "app.services.movie_story.two_round_narration",
            reason="",
        )


def test_migration_review_modules_are_not_retired() -> None:
    """长视频拆短视频相关模块先审查，不作为旧 native 主流程直接删除。"""
    review = set(migration_review_modules())

    assert "app.services.movie_story.timeline_runtime" in review
    assert "app.services.movie_story.highlight_edit_selection" in review
    assert "app.services.movie_story.movie_story_native_engine" not in review


def test_module_path_conversion_is_deterministic() -> None:
    """审计工具可以在源码路径和 dotted module 之间稳定转换。"""
    module = "app.services.movie_story.two_round_visual_narration"
    path = module_to_source_path(module)

    assert str(path).replace("\\", "/") == "app/services/movie_story/two_round_visual_narration.py"
    assert source_path_to_module(path) == module


def test_source_path_to_module_rejects_non_python_file() -> None:
    """路径转换只接受 Python 源码，避免把文档/JSON 当模块引用。"""
    with pytest.raises(ValueError, match="source_path_must_be_python_file"):
        source_path_to_module("docs/status/example.md")
