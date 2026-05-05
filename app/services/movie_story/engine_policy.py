"""Backend selection policy for movie_story engines.

Stage-P introduces an explicit engine boundary:

- legacy: call the current compatibility pipeline files
- native: call the new movie_story-native implementation when it becomes ready
- auto: select the safest available implementation

At Stage-P, native engines are intentionally marked not ready. Requests for
native are therefore recorded and safely routed to legacy instead of silently
running incomplete code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from app.services.movie_story.engine_result import EngineBackendInfo

BACKEND_AUTO = "auto"
BACKEND_LEGACY = "legacy"
BACKEND_NATIVE = "native"

ENGINE_KIND_MOVIE_STORY = "movie_story"
ENGINE_KIND_HIGHLIGHT_EDIT = "highlight_edit"

_ALLOWED_BACKENDS = {
    BACKEND_AUTO,
    BACKEND_LEGACY,
    BACKEND_NATIVE,
}


@dataclass(frozen=True)
class EnginePolicyDecision:
    engine_kind: str
    requested_backend: str
    selected_backend: str
    fallback_backend: str
    native_ready: bool
    reason: str
    compatibility_engine: str

    def backend_info(self) -> EngineBackendInfo:
        return EngineBackendInfo(
            engine_kind=self.engine_kind,
            requested_backend=self.requested_backend,
            selected_backend=self.selected_backend,
            fallback_backend=self.fallback_backend,
            native_ready=self.native_ready,
            reason=self.reason,
            compatibility_engine=self.compatibility_engine,
        )


def normalize_backend(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    if raw in {"", "default"}:
        return BACKEND_AUTO
    if raw not in _ALLOWED_BACKENDS:
        return BACKEND_AUTO
    return raw


def _mapping_get(mapping: Any, key: str, default: Any = None) -> Any:
    if isinstance(mapping, Mapping):
        return mapping.get(key, default)
    return default


def backend_from_kwargs(kwargs: Mapping[str, Any], *, engine_kind: str) -> str:
    """Resolve requested backend from explicit kwargs or environment."""

    scene_overrides = _mapping_get(kwargs, "scene_overrides", {})

    if engine_kind == ENGINE_KIND_MOVIE_STORY:
        explicit = (
            _mapping_get(kwargs, "engine_backend")
            or _mapping_get(kwargs, "movie_story_engine_backend")
            or _mapping_get(scene_overrides, "engine_backend")
            or _mapping_get(scene_overrides, "movie_story_engine_backend")
        )
    else:
        explicit = (
            _mapping_get(kwargs, "engine_backend")
            or _mapping_get(kwargs, "edit_engine_backend")
            or _mapping_get(kwargs, "highlight_engine_backend")
        )

    env_value = os.getenv("MOVIE_STORY_ENGINE_BACKEND", "")
    return normalize_backend(explicit or env_value or BACKEND_AUTO)


def native_ready_for(engine_kind: str) -> bool:
    """Return whether a native engine is ready for production use."""

    # Final migration promotes both product engines to native entry points.
    # Legacy engines remain as fallback for auto mode and explicit compatibility.
    return engine_kind in {ENGINE_KIND_HIGHLIGHT_EDIT, ENGINE_KIND_MOVIE_STORY}


def decide_engine_backend(
    *,
    engine_kind: str,
    requested_backend: str,
    compatibility_engine: str,
) -> EnginePolicyDecision:
    requested = normalize_backend(requested_backend)
    native_ready = native_ready_for(engine_kind)

    if requested == BACKEND_LEGACY:
        return EnginePolicyDecision(
            engine_kind=engine_kind,
            requested_backend=requested,
            selected_backend=BACKEND_LEGACY,
            fallback_backend=BACKEND_LEGACY,
            native_ready=native_ready,
            reason="explicit_legacy_requested",
            compatibility_engine=compatibility_engine,
        )

    if requested == BACKEND_NATIVE:
        if native_ready:
            return EnginePolicyDecision(
                engine_kind=engine_kind,
                requested_backend=requested,
                selected_backend=BACKEND_NATIVE,
                fallback_backend=BACKEND_LEGACY,
                native_ready=native_ready,
                reason="explicit_native_requested",
                compatibility_engine=compatibility_engine,
            )
        return EnginePolicyDecision(
            engine_kind=engine_kind,
            requested_backend=requested,
            selected_backend=BACKEND_LEGACY,
            fallback_backend=BACKEND_LEGACY,
            native_ready=native_ready,
            reason="native_requested_but_not_ready_fallback_legacy",
            compatibility_engine=compatibility_engine,
        )

    if native_ready:
        return EnginePolicyDecision(
            engine_kind=engine_kind,
            requested_backend=requested,
            selected_backend=BACKEND_NATIVE,
            fallback_backend=BACKEND_LEGACY,
            native_ready=native_ready,
            reason="auto_selected_native",
            compatibility_engine=compatibility_engine,
        )

    return EnginePolicyDecision(
        engine_kind=engine_kind,
        requested_backend=requested,
        selected_backend=BACKEND_LEGACY,
        fallback_backend=BACKEND_LEGACY,
        native_ready=native_ready,
        reason="auto_fallback_legacy_until_native_ready",
        compatibility_engine=compatibility_engine,
    )


__all__ = [
    "BACKEND_AUTO",
    "BACKEND_LEGACY",
    "BACKEND_NATIVE",
    "ENGINE_KIND_MOVIE_STORY",
    "ENGINE_KIND_HIGHLIGHT_EDIT",
    "EnginePolicyDecision",
    "backend_from_kwargs",
    "decide_engine_backend",
    "native_ready_for",
    "normalize_backend",
]
