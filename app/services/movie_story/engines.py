"""Switchable engine boundary for movie_story unified entry.

Stage-R adds production-safe native rollout behavior:

- movie_story still resolves to legacy by default
- highlight_edit resolves to native in auto mode
- auto-selected native failures fall back to legacy
- explicit native requests expose native failures instead of hiding them
- engine-selection kwargs are stripped before concrete engine calls
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.movie_story.engine_failover import (
    explicit_native_failure_payload,
    failover_backend_info,
    should_failover_to_legacy,
    strip_engine_backend_kwargs,
)
from app.services.movie_story.engine_policy import (
    BACKEND_LEGACY,
    BACKEND_NATIVE,
    ENGINE_KIND_HIGHLIGHT_EDIT,
    ENGINE_KIND_MOVIE_STORY,
    backend_from_kwargs,
    decide_engine_backend,
)
from app.services.movie_story.engine_result import attach_engine_backend_info
from app.services.movie_story.legacy_engines import (
    run_legacy_highlight_edit_engine,
    run_legacy_movie_story_engine,
)
from app.services.movie_story.native_engines import (
    NativeEngineNotReady,
    run_native_highlight_edit_engine,
    run_native_movie_story_engine,
)


def run_movie_story_engine(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the selected movie-story backend."""

    requested_backend = backend_from_kwargs(kwargs, engine_kind=ENGINE_KIND_MOVIE_STORY)
    decision = decide_engine_backend(
        engine_kind=ENGINE_KIND_MOVIE_STORY,
        requested_backend=requested_backend,
        compatibility_engine="subtitle_first_pipeline",
    )
    engine_kwargs = strip_engine_backend_kwargs(kwargs)

    logger.info(
        "movie_story engine backend: requested={} selected={} reason={}",
        decision.requested_backend,
        decision.selected_backend,
        decision.reason,
    )

    if decision.selected_backend == BACKEND_NATIVE:
        try:
            payload = run_native_movie_story_engine(*args, **engine_kwargs)
        except NativeEngineNotReady as exc:
            if should_failover_to_legacy(decision, error=exc):
                logger.warning("native movie_story engine not ready; falling back to legacy")
                legacy_payload = run_legacy_movie_story_engine(*args, **engine_kwargs)
                info = failover_backend_info(decision, reason="native_not_ready_auto_failover_legacy")
                return attach_engine_backend_info(dict(legacy_payload or {}), info)
            payload = explicit_native_failure_payload(decision, error=exc)
        except Exception as exc:  # pragma: no cover - defensive production guard
            if should_failover_to_legacy(decision, error=exc):
                logger.exception("native movie_story engine failed; falling back to legacy")
                legacy_payload = run_legacy_movie_story_engine(*args, **engine_kwargs)
                info = failover_backend_info(decision, reason="native_exception_auto_failover_legacy")
                result = attach_engine_backend_info(dict(legacy_payload or {}), info)
                result["native_error"] = str(exc)
                return result
            raise
    else:
        payload = run_legacy_movie_story_engine(*args, **engine_kwargs)

    return attach_engine_backend_info(dict(payload or {}), decision.backend_info())


def run_highlight_edit_engine(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the selected highlight-edit backend with safe native failover."""

    requested_backend = backend_from_kwargs(kwargs, engine_kind=ENGINE_KIND_HIGHLIGHT_EDIT)
    decision = decide_engine_backend(
        engine_kind=ENGINE_KIND_HIGHLIGHT_EDIT,
        requested_backend=requested_backend,
        compatibility_engine="highlight_edit_pipeline",
    )
    engine_kwargs = strip_engine_backend_kwargs(kwargs)

    logger.info(
        "highlight_edit engine backend: requested={} selected={} reason={}",
        decision.requested_backend,
        decision.selected_backend,
        decision.reason,
    )

    if decision.selected_backend == BACKEND_NATIVE:
        try:
            native_payload = run_native_highlight_edit_engine(*args, **engine_kwargs)
        except NativeEngineNotReady as exc:
            if should_failover_to_legacy(decision, error=exc):
                logger.warning("native highlight_edit engine not ready; falling back to legacy")
                legacy_payload = run_legacy_highlight_edit_engine(*args, **engine_kwargs)
                info = failover_backend_info(decision, reason="native_not_ready_auto_failover_legacy")
                return attach_engine_backend_info(dict(legacy_payload or {}), info)
            native_payload = explicit_native_failure_payload(decision, error=exc)
        except Exception as exc:  # pragma: no cover - defensive production guard
            if should_failover_to_legacy(decision, error=exc):
                logger.exception("native highlight_edit engine failed; falling back to legacy")
                legacy_payload = run_legacy_highlight_edit_engine(*args, **engine_kwargs)
                info = failover_backend_info(decision, reason="native_exception_auto_failover_legacy")
                result = attach_engine_backend_info(dict(legacy_payload or {}), info)
                result["native_error"] = str(exc)
                return result
            raise

        if should_failover_to_legacy(decision, payload=native_payload):
            logger.warning("native highlight_edit payload failed; falling back to legacy")
            legacy_payload = run_legacy_highlight_edit_engine(*args, **engine_kwargs)
            info = failover_backend_info(decision, reason="native_payload_failed_auto_failover_legacy")
            result = attach_engine_backend_info(dict(legacy_payload or {}), info)
            result["native_failure_payload"] = dict(native_payload or {}) if isinstance(native_payload, dict) else native_payload
            return result

        if decision.requested_backend == BACKEND_NATIVE and isinstance(native_payload, dict) and native_payload.get("success") is False:
            native_payload = explicit_native_failure_payload(decision, payload=native_payload)

        return attach_engine_backend_info(dict(native_payload or {}), decision.backend_info())

    payload = run_legacy_highlight_edit_engine(*args, **engine_kwargs)
    return attach_engine_backend_info(dict(payload or {}), decision.backend_info())


__all__ = [
    "run_movie_story_engine",
    "run_highlight_edit_engine",
    "BACKEND_LEGACY",
    "BACKEND_NATIVE",
]
