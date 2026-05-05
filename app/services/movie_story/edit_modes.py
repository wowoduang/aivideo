from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

MOVIE_STORY = "movie_story"
HIGHLIGHT_RECUT = "highlight_recut"
NARRATED_HIGHLIGHT_EDIT = "narrated_highlight_edit"
RAW_HIGHLIGHT = "raw_highlight"
EXTERNAL_NARRATION = "external_narration"

ENTRY_MOVIE_STORY_SCRIPT = "movie_story_script"
ENTRY_HIGHLIGHT_SCRIPT = "highlight_script"

HIGHLIGHT_MODE_ALIASES = {
    "": HIGHLIGHT_RECUT,
    "highlight": HIGHLIGHT_RECUT,
    "highlight_edit": HIGHLIGHT_RECUT,
    "highlight_recut": HIGHLIGHT_RECUT,
    "recut": HIGHLIGHT_RECUT,
    "raw": RAW_HIGHLIGHT,
    "raw_highlight": RAW_HIGHLIGHT,
    "narrated": NARRATED_HIGHLIGHT_EDIT,
    "narrated_highlight": NARRATED_HIGHLIGHT_EDIT,
    "narrated_highlight_edit": NARRATED_HIGHLIGHT_EDIT,
    "external_narration": NARRATED_HIGHLIGHT_EDIT,
    "movie_story": MOVIE_STORY,
}

ENTRY_ALIASES = {
    "movie-story-script": ENTRY_MOVIE_STORY_SCRIPT,
    "movie_story_script": ENTRY_MOVIE_STORY_SCRIPT,
    "movie_story": ENTRY_MOVIE_STORY_SCRIPT,
    "subtitle_first": ENTRY_MOVIE_STORY_SCRIPT,
    "highlight-script": ENTRY_HIGHLIGHT_SCRIPT,
    "highlight_script": ENTRY_HIGHLIGHT_SCRIPT,
    "highlight": ENTRY_HIGHLIGHT_SCRIPT,
    "highlight_recut": ENTRY_HIGHLIGHT_SCRIPT,
}


@dataclass(frozen=True)
class UnifiedEditMode:
    """Normalized mode information for the unified movie-story/edit entry layer."""

    entry: str
    mode: str
    generates_narration: bool
    uses_external_narration: bool
    preserves_raw_audio: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "entry": self.entry,
            "mode": self.mode,
            "generates_narration": self.generates_narration,
            "uses_external_narration": self.uses_external_narration,
            "preserves_raw_audio": self.preserves_raw_audio,
        }


def normalize_entry(entry: str) -> str:
    raw = str(entry or "").strip().lower().replace(" ", "_")
    return ENTRY_ALIASES.get(raw, raw or ENTRY_HIGHLIGHT_SCRIPT)


def normalize_highlight_mode(mode: str, *, narration_text: str = "", narration_audio_path: str = "") -> str:
    raw = str(mode or "").strip().lower().replace(" ", "_").replace("-", "_")
    normalized = HIGHLIGHT_MODE_ALIASES.get(raw, raw or HIGHLIGHT_RECUT)
    if normalized == EXTERNAL_NARRATION:
        normalized = NARRATED_HIGHLIGHT_EDIT
    if normalized == HIGHLIGHT_RECUT and (str(narration_text or "").strip() or str(narration_audio_path or "").strip()):
        return NARRATED_HIGHLIGHT_EDIT
    return normalized


def resolve_unified_mode(entry: str, request: Dict[str, Any]) -> UnifiedEditMode:
    normalized_entry = normalize_entry(entry)
    if normalized_entry == ENTRY_MOVIE_STORY_SCRIPT:
        highlight_only = bool(request.get("highlight_only", False))
        return UnifiedEditMode(
            entry=ENTRY_MOVIE_STORY_SCRIPT,
            mode=MOVIE_STORY,
            generates_narration=not highlight_only,
            uses_external_narration=False,
            preserves_raw_audio=bool(highlight_only),
        )

    narration_text = str(request.get("narration_text", "") or "")
    narration_audio_path = str(request.get("narration_audio_path", "") or "")
    requested_mode = normalize_highlight_mode(
        str(request.get("mode", HIGHLIGHT_RECUT) or HIGHLIGHT_RECUT),
        narration_text=narration_text,
        narration_audio_path=narration_audio_path,
    )
    return UnifiedEditMode(
        entry=ENTRY_HIGHLIGHT_SCRIPT,
        mode=requested_mode,
        generates_narration=requested_mode == NARRATED_HIGHLIGHT_EDIT,
        uses_external_narration=bool(narration_text.strip() or narration_audio_path.strip()),
        preserves_raw_audio=bool(request.get("prefer_raw_audio", True)) or requested_mode == RAW_HIGHLIGHT,
    )


def engine_mode_for_highlight(normalized_mode: str) -> str:
    """Return the canonical mode accepted by highlight edit engines."""

    if normalized_mode == RAW_HIGHLIGHT:
        return HIGHLIGHT_RECUT
    if normalized_mode == EXTERNAL_NARRATION:
        return NARRATED_HIGHLIGHT_EDIT
    if normalized_mode == MOVIE_STORY:
        return HIGHLIGHT_RECUT
    return normalized_mode or HIGHLIGHT_RECUT
