# -*- coding: utf-8 -*-
from __future__ import annotations

"""
narration_contract.py

统一叙事链路的数据契约。
- 每个阶段只接受明确输入结构
- 每个阶段必须返回明确输出结构
- 任何非法输入都直接 raise
"""

from typing import Any, Mapping


def require_mapping(value: Any, *, stage: str, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{stage}:{field}:expected_mapping")
    return value


def require_text(value: Any, *, stage: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{stage}:{field}:expected_text")
    return value


def require_list(value: Any, *, stage: str, field: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{stage}:{field}:expected_list")
    return value


def validate_fact_segment(obj: Mapping[str, Any]) -> None:
    require_mapping(obj, stage="fact_segment", field="segment")
    require_text(obj.get("segment_id"), stage="fact_segment", field="segment_id")
    require_text(obj.get("title"), stage="fact_segment", field="title")
    require_text(obj.get("summary"), stage="fact_segment", field="summary")
    require_text(obj.get("time_range"), stage="fact_segment", field="time_range")


def validate_narrative_beat(obj: Mapping[str, Any]) -> None:
    require_mapping(obj, stage="narrative_beat", field="beat")
    require_text(obj.get("beat_id"), stage="narrative_beat", field="beat_id")
    require_text(obj.get("phase"), stage="narrative_beat", field="phase")
    require_text(obj.get("hook"), stage="narrative_beat", field="hook")
    require_text(obj.get("content"), stage="narrative_beat", field="content")
    require_text(obj.get("time_range"), stage="narrative_beat", field="time_range")


def validate_narration_item(obj: Mapping[str, Any]) -> None:
    require_mapping(obj, stage="narration_item", field="item")
    require_text(obj.get("item_id"), stage="narration_item", field="item_id")
    require_text(obj.get("script_text"), stage="narration_item", field="script_text")
    require_text(obj.get("time_range"), stage="narration_item", field="time_range")


def validate_stage_result(stage: str, payload: Mapping[str, Any]) -> None:
    if stage == "fact_segment":
        for item in require_list(payload.get("facts"), stage=stage, field="facts"):
            validate_fact_segment(require_mapping(item, stage=stage, field="facts"))
        return

    if stage == "narrative_beat":
        for item in require_list(payload.get("beats"), stage=stage, field="beats"):
            validate_narrative_beat(require_mapping(item, stage=stage, field="beats"))
        return

    if stage == "narration_item":
        for item in require_list(payload.get("script_items"), stage=stage, field="script_items"):
            validate_narration_item(require_mapping(item, stage=stage, field="script_items"))
        return

    raise ValueError(f"unsupported_contract_stage:{stage}")


def validate_structured_movie_story_result(payload: Mapping[str, Any]) -> None:
    require_mapping(payload, stage="movie_story", field="root")
    if "facts" in payload:
        validate_stage_result("fact_segment", payload)
    if "beats" in payload:
        validate_stage_result("narrative_beat", payload)
    if "script_items" in payload:
        validate_stage_result("narration_item", payload)
