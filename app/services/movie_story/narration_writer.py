# -*- coding: utf-8 -*-
"""Compatibility layer for narration generation.

Final narration is implemented by ``narration_engine``. This module exists only
so older imports keep working; no simplified prompt or subtitle passthrough is
allowed here.
"""
from __future__ import annotations

from app.services.movie_story.narration_engine import (  # noqa: F401
    build_narration_script,
    build_scene_evidence,
    generate_from_selected_highlights,
    generate_narration_script,
    sort_timeline,
    write_narration_script,
    write_outputs,
)

__all__ = [
    "sort_timeline",
    "build_scene_evidence",
    "generate_from_selected_highlights",
    "generate_narration_script",
    "build_narration_script",
    "write_narration_script",
    "write_outputs",
]
