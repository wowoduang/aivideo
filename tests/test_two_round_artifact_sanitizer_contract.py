# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path

from app.services.movie_story.two_round_feature_modes import _sanitize_two_round_artifact_payload
from app.services.narration_text_sanitizer import sanitize_deliverable_title_text


def test_title_sanitizer_removes_section_label_with_fallback() -> None:
    assert (
        sanitize_deliverable_title_text(
            "分论点一",
            fallback_text="朱重八最后一点信赖被稻种毁掉。",
        )
        == "朱重八最后一点信赖被稻种毁掉。"
    )


def test_two_round_artifact_payload_sanitizes_narration_text_and_titles() -> None:
    payload = [
        {
            "title": "分论点一",
            "section_title": "分论点一",
            "narration": "第一段正文。\n\n---\n\n第二段正文。",
            "text": "第一段正文。\n\n---\n\n第二段正文。",
        }
    ]

    cleaned = _sanitize_two_round_artifact_payload(payload)

    assert cleaned[0]["title"] == "第一段正文。 第二段正文。"
    assert cleaned[0]["section_title"] == "第一段正文。 第二段正文。"
    assert cleaned[0]["narration"] == "第一段正文。\n\n第二段正文。"
    assert cleaned[0]["text"] == "第一段正文。\n\n第二段正文。"


def test_two_round_write_json_sanitizes_its_payload_argument() -> None:
    source = Path("app/services/movie_story/two_round_feature_modes.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )
    tree = ast.parse(source)

    write_json = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_write_json":
            write_json = node
            break

    assert write_json is not None
    assert len(write_json.args.args) >= 2

    payload_name = write_json.args.args[1].arg
    function_source = ast.get_source_segment(source, write_json) or ""

    assert "_sanitize_two_round_artifact_payload" in function_source
    assert f"{payload_name} = _sanitize_two_round_artifact_payload({payload_name})" in function_source
