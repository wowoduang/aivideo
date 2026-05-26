# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger


def _strip_markdown_json_fence(value: str) -> str:
    """Return the JSON body when an LLM wraps JSON in a markdown fence."""

    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value.strip(), re.DOTALL | re.IGNORECASE)
    if not match:
        return value
    return match.group(1).strip()


def parse_and_fix_json(json_string: str) -> Any:
    """Parse common LLM JSON variants used by legacy callers.

    This helper intentionally returns None when no safe repair works. It does
    not hide failures in production chains that require strict parsing; those
    callers should raise their own explicit errors after receiving None.
    """

    if not json_string or not str(json_string).strip():
        return None

    normalized = _strip_markdown_json_fence(str(json_string).strip())

    for candidate in (
        normalized,
        normalized.replace("{{", "{").replace("}}", "}"),
    ):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.debug("JSON 解析失败: {}", exc)

    json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", str(json_string).strip(), re.DOTALL | re.IGNORECASE)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError as exc:
            logger.debug("JSON fenced 内容解析失败: {}", exc)

    return None
