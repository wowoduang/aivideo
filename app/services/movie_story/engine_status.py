"""Engine status and policy introspection for movie_story.

This module gives API routes, diagnostics, tests, and support tools a stable way
of seeing which backend would be selected for each product mode without running
an actual video job.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

from app.services.movie_story.engine_policy import (
    BACKEND_AUTO,
    ENGINE_KIND_HIGHLIGHT_EDIT,
    ENGINE_KIND_MOVIE_STORY,
    decide_engine_backend,
    native_ready_for,
    normalize_backend,
)

_ENGINE_COMPATIBILITY = {
    ENGINE_KIND_MOVIE_STORY: "subtitle_first_pipeline",
    ENGINE_KIND_HIGHLIGHT_EDIT: "highlight_edit_pipeline",
}


def explain_engine_policy(*, engine_kind: str, requested_backend: Any = BACKEND_AUTO) -> Dict[str, Any]:
    """Return the policy decision for one engine kind as a plain dictionary."""

    compatibility_engine = _ENGINE_COMPATIBILITY.get(engine_kind, "")
    decision = decide_engine_backend(
        engine_kind=engine_kind,
        requested_backend=normalize_backend(requested_backend),
        compatibility_engine=compatibility_engine,
    )
    return {
        "engine_kind": decision.engine_kind,
        "requested_backend": decision.requested_backend,
        "selected_backend": decision.selected_backend,
        "fallback_backend": decision.fallback_backend,
        "native_ready": decision.native_ready,
        "reason": decision.reason,
        "compatibility_engine": decision.compatibility_engine,
    }


def get_engine_status(*, requested_backend: Any = BACKEND_AUTO) -> Dict[str, Any]:
    """Return a compact status report for all product engines."""

    engines = {
        ENGINE_KIND_MOVIE_STORY: explain_engine_policy(
            engine_kind=ENGINE_KIND_MOVIE_STORY,
            requested_backend=requested_backend,
        ),
        ENGINE_KIND_HIGHLIGHT_EDIT: explain_engine_policy(
            engine_kind=ENGINE_KIND_HIGHLIGHT_EDIT,
            requested_backend=requested_backend,
        ),
    }
    return {
        "success": True,
        "requested_backend": normalize_backend(requested_backend),
        "native_ready": {
            ENGINE_KIND_MOVIE_STORY: native_ready_for(ENGINE_KIND_MOVIE_STORY),
            ENGINE_KIND_HIGHLIGHT_EDIT: native_ready_for(ENGINE_KIND_HIGHLIGHT_EDIT),
        },
        "engines": engines,
        "legacy_policy": {
            "legacy_engines_are_fallback_only": True,
            "allowed_direct_legacy_import_module": "app.services.movie_story.legacy_engines",
        },
    }


__all__ = [
    "explain_engine_policy",
    "get_engine_status",
]
