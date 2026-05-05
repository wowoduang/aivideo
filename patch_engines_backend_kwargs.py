from pathlib import Path
import re

path = Path(r"E:\aivideo-v5\app\services\movie_story\engines.py")
text = path.read_text(encoding="utf-8")

helper = r'''
def _strip_engine_backend_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Remove engine-selection kwargs before delegating to concrete engines."""

    cleaned = dict(kwargs)

    for key in (
        "engine_backend",
        "movie_story_engine_backend",
        "edit_engine_backend",
        "highlight_engine_backend",
    ):
        cleaned.pop(key, None)

    scene_overrides = cleaned.get("scene_overrides")
    if isinstance(scene_overrides, dict):
        copied_overrides = dict(scene_overrides)
        copied_overrides.pop("engine_backend", None)
        copied_overrides.pop("movie_story_engine_backend", None)
        copied_overrides.pop("edit_engine_backend", None)
        copied_overrides.pop("highlight_engine_backend", None)
        cleaned["scene_overrides"] = copied_overrides

    return cleaned


'''

if "_strip_engine_backend_kwargs" not in text:
    text = text.replace(
        "\ndef run_movie_story_engine(",
        "\n" + helper + "\ndef run_movie_story_engine(",
        1,
    )

# Add clean kwargs after each policy decision block if missing.
text = text.replace(
    '    logger.info(\n        "movie_story engine backend: requested={} selected={} reason={}",\n        decision.requested_backend,\n        decision.selected_backend,\n        decision.reason,\n    )\n\n    if decision.selected_backend',
    '    logger.info(\n        "movie_story engine backend: requested={} selected={} reason={}",\n        decision.requested_backend,\n        decision.selected_backend,\n        decision.reason,\n    )\n\n    engine_kwargs = _strip_engine_backend_kwargs(kwargs)\n\n    if decision.selected_backend',
)

text = text.replace(
    '    logger.info(\n        "highlight_edit engine backend: requested={} selected={} reason={}",\n        decision.requested_backend,\n        decision.selected_backend,\n        decision.reason,\n    )\n\n    if decision.selected_backend',
    '    logger.info(\n        "highlight_edit engine backend: requested={} selected={} reason={}",\n        decision.requested_backend,\n        decision.selected_backend,\n        decision.reason,\n    )\n\n    engine_kwargs = _strip_engine_backend_kwargs(kwargs)\n\n    if decision.selected_backend',
)

# Replace concrete engine calls to use cleaned kwargs.
text = text.replace("run_native_movie_story_engine(*args, **kwargs)", "run_native_movie_story_engine(*args, **engine_kwargs)")
text = text.replace("run_legacy_movie_story_engine(*args, **kwargs)", "run_legacy_movie_story_engine(*args, **engine_kwargs)")
text = text.replace("run_native_highlight_edit_engine(*args, **kwargs)", "run_native_highlight_edit_engine(*args, **engine_kwargs)")
text = text.replace("run_legacy_highlight_edit_engine(*args, **kwargs)", "run_legacy_highlight_edit_engine(*args, **engine_kwargs)")

path.write_text(text, encoding="utf-8")
print("patched engines.py")
