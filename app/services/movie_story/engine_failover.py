"""Failover helpers for movie_story engine boundary.

Stage-R makes native highlight-edit rollout safer:

- auto-selected native failures can fall back to legacy
- explicitly requested native failures remain visible
- engine-selection kwargs are stripped before calling concrete engines
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.movie_story.engine_policy import BACKEND_AUTO, BACKEND_LEGACY, BACKEND_NATIVE, EnginePolicyDecision
from app.services.movie_story.engine_result import EngineBackendInfo

_ENGINE_BACKEND_KEYS = (
    "engine_backend",
    "movie_story_engine_backend",
    "edit_engine_backend",
    "highlight_engine_backend",
)


def strip_engine_backend_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Remove engine-selection kwargs before delegating to concrete engines."""

    cleaned = dict(kwargs)

    for key in _ENGINE_BACKEND_KEYS:
        cleaned.pop(key, None)

    scene_overrides = cleaned.get("scene_overrides")
    if isinstance(scene_overrides, dict):
        copied_overrides = dict(scene_overrides)
        for key in _ENGINE_BACKEND_KEYS:
            copied_overrides.pop(key, None)
        cleaned["scene_overrides"] = copied_overrides

    return cleaned


def payload_failed(payload: Any) -> bool:
    """Return True when a concrete engine payload clearly represents failure."""

    if payload is None:
        return True
    if not isinstance(payload, Mapping):
        return False
    return payload.get("success") is False


def should_failover_to_legacy(decision: EnginePolicyDecision, payload: Any = None, error: BaseException | None = None) -> bool:
    """Decide whether a native failure should fall back to legacy.

    Only auto-selected native requests fall back. Explicit native requests are
    considered diagnostic/proving mode and should expose native failures.
    """

    if decision.selected_backend != BACKEND_NATIVE:
        return False
    if decision.requested_backend != BACKEND_AUTO:
        return False
    if error is not None:
        return True
    return payload_failed(payload)


def failover_backend_info(decision: EnginePolicyDecision, *, reason: str) -> EngineBackendInfo:
    """Build backend metadata for a native-to-legacy failover result."""

    return EngineBackendInfo(
        engine_kind=decision.engine_kind,
        requested_backend=decision.requested_backend,
        selected_backend=BACKEND_LEGACY,
        fallback_backend=BACKEND_LEGACY,
        native_ready=decision.native_ready,
        reason=reason,
        compatibility_engine=decision.compatibility_engine,
    )


def explicit_native_failure_payload(decision: EnginePolicyDecision, *, error: BaseException | None = None, payload: Any = None) -> dict[str, Any]:
    """Normalize explicit native failure into a normal payload."""

    message = str(error) if error is not None else "native engine returned unsuccessful payload"
    result: dict[str, Any]
    if isinstance(payload, Mapping):
        result = dict(payload)
        result.setdefault("success", False)
        result.setdefault("error", message)
    else:
        result = {"success": False, "error": message}
    result["native_failure_payload"] = payload if isinstance(payload, Mapping) else None
    return result


__all__ = [
    "strip_engine_backend_kwargs",
    "payload_failed",
    "should_failover_to_legacy",
    "failover_backend_info",
    "explicit_native_failure_payload",
]
