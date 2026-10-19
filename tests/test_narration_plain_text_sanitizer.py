# -*- coding: utf-8 -*-
from __future__ import annotations

from app.services.generate_narration_script import _raw_srt_clean_narration
from app.services.narration_text_sanitizer import sanitize_deliverable_narration_text


def test_sanitizer_removes_markdown_separators() -> None:
    text = "第一段正文。\n\n---\n\n第二段正文。\n--\n第三段正文。"

    assert sanitize_deliverable_narration_text(text) == "第一段正文。\n\n第二段正文。\n第三段正文。"


def test_sanitizer_strips_structural_prefixes() -> None:
    text = "\n".join(
        [
            "分论点一：朱重八最后一点信赖被稻种毁掉。",
            "开场：皇帝为寿礼发愁，苦难从金殿传到乡下。",
            "收尾：他终于明白，守法不等于能活。",
        ]
    )

    assert sanitize_deliverable_narration_text(text) == "\n".join(
        [
            "朱重八最后一点信赖被稻种毁掉。",
            "皇帝为寿礼发愁，苦难从金殿传到乡下。",
            "他终于明白，守法不等于能活。",
        ]
    )


def test_sanitizer_drops_structure_only_lines() -> None:
    text = "\n".join(
        [
            "【分论点二】",
            "住持把朱重八从法册上除名。",
            "当下回响：",
            "这不是劝退，是体制对失败者的最终否定。",
        ]
    )

    assert sanitize_deliverable_narration_text(text) == "\n".join(
        [
            "住持把朱重八从法册上除名。",
            "这不是劝退，是体制对失败者的最终否定。",
        ]
    )


def test_raw_srt_clean_narration_uses_final_sanitizer() -> None:
    text = "\n".join(
        [
            "**分论点三：**",
            "濠州城不是什么正义营垒，它是一座丛林。",
            "---",
            "收尾：被人认得，本身就是一种反常的秩序。",
        ]
    )

    assert _raw_srt_clean_narration(text) == "\n".join(
        [
            "濠州城不是什么正义营垒，它是一座丛林。",
            "被人认得，本身就是一种反常的秩序。",
        ]
    )
