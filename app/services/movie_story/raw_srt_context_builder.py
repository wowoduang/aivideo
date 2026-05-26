# -*- coding: utf-8 -*-
from __future__ import annotations

"""
raw_srt_context_builder.py

构建 raw_srt 第一轮提示词输入区。
仅负责把原始字幕、说话人标注、场景边界事实拼成稳定上下文。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.raw_srt_context",
    "entry_points": ["build_first_round_input"],
    "called_by": ["movie_story/two_round_narration.py", "movie_story/raw_srt_narration.py"],
    "decisions": [
        "2026-05: 第一轮输入从裸 raw_srt_text 扩展为原始字幕 + 说话人标注 + 场景边界。",
        "2026-05: 原始字幕仍是主要语义依据，辅助上下文不能覆盖字幕事实。",
    ],
    "pending": ["接入 two_round_narration.py 的第一轮 prompt 模板。"],
    "ai_constraints": [
        "禁止把 scene_boundary_context 写成剧情解读。",
        "禁止删除原始字幕输入区。",
        "禁止把低置信度说话人当成确定事实。",
    ],
}

import json
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger


FIRST_ROUND_CONTEXT_INSTRUCTIONS = """\
注意：
1. 【原始字幕】是主要语义依据。
2. 【说话人标注】是辅助证据，低置信度或“存疑”的说话人不得作为确定事实。
3. 【场景边界】只提供客观事实和时间边界，不是剧情解读。
4. 故事段划分仍由你根据叙事完整性判断。
5. 如果辅助证据和原始字幕冲突，以原始字幕为准，并标注辅助证据存疑。
"""


def build_first_round_input(
    raw_srt_text: str,
    *,
    speaker_context: Mapping[str, Any] | str | None = None,
    scene_boundary_context: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | None = None,
) -> str:
    """
    构建 raw_srt 第一轮输入区。

    意图：
        两轮链的弱点是只看字幕，缺少说话人和场景边界事实。
        本函数只负责拼接三类输入，不负责解释剧情，也不负责调用 LLM。

    注意（AI 不得修改以下行为）：
        - 必须保留【原始字幕】输入区。
        - 必须保留【说话人标注】和【场景边界】标题。
        - 空上下文必须显式写“暂无可靠数据”，不能伪造。
    """
    sections = [
        FIRST_ROUND_CONTEXT_INSTRUCTIONS.strip(),
        "【原始字幕】\n{}".format((raw_srt_text or "").strip()),
        "【说话人标注】\n{}".format(_serialize_context(speaker_context)),
        "【场景边界】\n{}".format(_serialize_context(scene_boundary_context)),
    ]
    result = "\n\n".join(sections).strip()
    logger.info("raw_srt 第一轮输入区构建完成: chars={}", len(result))
    return result


def _serialize_context(value: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | None) -> str:
    """把上下文对象序列化成 prompt 可读文本。"""
    if value is None:
        return "暂无可靠数据。"
    if isinstance(value, str):
        return value.strip() or "暂无可靠数据。"
    if isinstance(value, Mapping):
        if not value:
            return "暂无可靠数据。"
        return json.dumps(value, ensure_ascii=False, indent=2)
    if isinstance(value, Sequence):
        items = list(value)
        if not items:
            return "暂无可靠数据。"
        return json.dumps(items, ensure_ascii=False, indent=2)
    return "暂无可靠数据。"
