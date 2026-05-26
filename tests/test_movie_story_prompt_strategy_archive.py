import json
from pathlib import Path

from app.utils import workspace

from app.services.movie_story import prompt_strategy_archive as archive


def test_get_prompt_strategy_uses_movie_category_default():
    strategy = archive.get_prompt_strategy(movie_category="历史宫廷")

    assert strategy["strategy_id"] == "historical_pressure"
    assert "do_write" in strategy
    assert "do_not_write" in strategy


def test_score_narration_items_penalizes_repetition_and_cliche():
    report = archive.score_narration_items(
        [
            {"narration": "这一段主要交代，局面继续升级。"},
            {"narration": "这一段主要交代，局面继续升级。"},
        ],
        source_text="局面继续升级",
    )

    assert report["score"] < 0.78
    assert report["duplicate_ratio"] > 0
    assert report["cliche_hits"] == 2
    assert report["passed"] is False


def test_record_and_select_prompt_strategy_by_category_score(monkeypatch):
    path = Path(workspace.temp_dir("tests/prompt_strategy_archive", create=True)) / "strategy_scores.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    monkeypatch.setattr(archive, "strategy_archive_path", lambda: path)

    archive.record_prompt_strategy_result(
        movie_category="历史宫廷",
        strategy_id="character_growth",
        stage="subtitle_draft",
        score_report={"score": 0.62},
    )
    archive.record_prompt_strategy_result(
        movie_category="历史宫廷",
        strategy_id="character_growth",
        stage="subtitle_draft",
        score_report={"score": 0.66},
    )
    archive.record_prompt_strategy_result(
        movie_category="历史宫廷",
        strategy_id="historical_pressure",
        stage="subtitle_draft",
        score_report={"score": 0.91},
        sample={"items_preview": [{"narration": "ok"}]},
    )
    archive.record_prompt_strategy_result(
        movie_category="历史宫廷",
        strategy_id="historical_pressure",
        stage="subtitle_draft",
        score_report={"score": 0.87},
    )

    selected = archive.select_prompt_strategy("历史宫廷", stage="subtitle_draft", min_samples=2)

    assert selected["strategy_id"] == "historical_pressure"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[2]["sample"]["items_preview"][0]["narration"] == "ok"
