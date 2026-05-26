from __future__ import annotations

from pathlib import Path

from app.services.movie_story.architecture_guard import find_direct_legacy_imports, find_direct_runtime_imports


ROOT = Path(__file__).resolve().parents[1]


def test_direct_legacy_pipeline_imports_are_isolated():
    report = find_direct_legacy_imports(ROOT / "app")
    assert report["success"] is True
    assert report["violations"] == []
    allowed_paths = {hit["path"] for hit in report["allowed_hits"]}
    assert allowed_paths == {"services/movie_story/legacy_engines.py"}


def test_direct_runtime_imports_do_not_escape_legacy_family():
    report = find_direct_runtime_imports(ROOT / "app")
    assert report["success"] is True
    assert report["violations"] == []
    assert report["allowed_hits"]
