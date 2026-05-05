from pathlib import Path

paths = [
    Path(r"E:\aivideo-v5\tests\test_movie_story_native_movie_story_engine.py"),
    Path(r"E:\aivideo-v5-workspace\patches\m\changed_files\tests\test_movie_story_native_movie_story_engine.py"),
]

for path in paths:
    if not path.exists():
        continue

    text = path.read_text(encoding="utf-8")

    old_import = 'import app.services.movie_story.movie_story_native_engine as native_module'
    new_import = (
        'import app.services.movie_story.movie_story_native_engine as native_module\n'
        '    import app.services.movie_story.native_engines as native_engines'
    )

    if old_import in text and 'import app.services.movie_story.native_engines as native_engines' not in text:
        text = text.replace(old_import, new_import, 1)

    text = text.replace(
        'monkeypatch.setattr(native_module, "run_subtitle_first_pipeline", fake_run)',
        (
            'monkeypatch.setattr(native_module, "run_movie_story_native_engine", fake_run, raising=False)\n'
            '    monkeypatch.setattr(native_engines, "run_movie_story_native_engine", fake_run, raising=False)'
        ),
    )

    path.write_text(text, encoding="utf-8")
    print("patched", path)
