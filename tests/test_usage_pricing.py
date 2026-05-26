from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import auth_store, usage_meter, usage_pricing


def _user(email: str = "alice@example.com"):
    now = datetime.now(timezone.utc).isoformat()
    try:
        return auth_store.register_user("Alice", email, "secret123", now)
    except ValueError:
        return auth_store.get_user(email)


def test_usage_pricing_env_rules_are_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("AIVIDEO_USAGE_PRICES_JSON", '{"llm_prompt_tokens:openai:tokens": 0.5, "tts_characters:*:characters": 0.1}')
    usage_pricing.clear_cache()
    _user()

    usage_meter.record_llm_usage(owner="alice@example.com", provider="openai", model="gpt-4o", prompt_tokens=2, completion_tokens=0)
    usage_meter.record_tts_usage(owner="alice@example.com", provider="edge_tts", voice_name="v", characters=3)

    summary = usage_meter.summarize_usage("alice@example.com")
    rows = {(row["event_type"], row["provider"], row["unit_name"]): row for row in summary["summary"]}
    assert rows[("llm_prompt_tokens", "openai", "tokens")]["total_cost"] == 1.0
    assert rows[("tts_characters", "edge_tts", "characters")]["total_cost"] == pytest.approx(0.3)
    assert summary["pricing"]["configured"] is True
    usage_pricing.clear_cache()
