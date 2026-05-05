"""API routers with lazy imports to avoid unrelated heavy dependencies during partial use."""
from __future__ import annotations

from importlib import import_module

__all__ = ["auth", "health", "jobs", "projects", "system", "tts", "uploads", "workbench_state"]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    module = import_module(f"{__name__}.{name}")
    return getattr(module, "router")
