import importlib
import sys
import types
import unittest
from unittest.mock import patch


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


def _stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


class _PromptManager:
    @staticmethod
    def get_prompt(*args, **kwargs):
        return "prompt"




class _PlotUnderstandingLoguruLoggerStub:
    """Small loguru-compatible stub for importing config during unit tests."""

    def remove(self, *args: object, **kwargs: object) -> None:
        return None

    def add(self, *args: object, **kwargs: object) -> int:
        return 1

    def bind(self, *args: object, **kwargs: object) -> "_PlotUnderstandingLoguruLoggerStub":
        return self

    def opt(self, *args: object, **kwargs: object) -> "_PlotUnderstandingLoguruLoggerStub":
        return self

    def debug(self, *args: object, **kwargs: object) -> None:
        return None

    def info(self, *args: object, **kwargs: object) -> None:
        return None

    def warning(self, *args: object, **kwargs: object) -> None:
        return None

    def error(self, *args: object, **kwargs: object) -> None:
        return None

    def exception(self, *args: object, **kwargs: object) -> None:
        return None


def _ensure_loguru_stub_supports_config_logger() -> None:
    """Ensure the test loguru stub supports app.config logger initialization.

    app.services.plot_understanding imports app.services.llm.runtime_config, which imports
    app.config. app.config calls logger.remove()/logger.add() during import.
    This test file may install a lightweight loguru stub, so the stub must expose
    the methods app.config uses.
    """
    import sys
    import types

    loguru_module = sys.modules.get("loguru")
    logger = getattr(loguru_module, "logger", None) if loguru_module is not None else None

    required = ("remove", "add", "debug", "info", "warning", "error", "exception")
    if logger is not None and all(hasattr(logger, name) for name in required):
        return

    sys.modules["loguru"] = types.SimpleNamespace(
        logger=_PlotUnderstandingLoguruLoggerStub()
    )

def _load_plot_understanding():
    stubbed_modules = {
        "loguru": _stub_module("loguru", logger=_Logger()),
        "app.services.llm_text_completion": _stub_module(
            "app.services.llm_text_completion",
            call_text_chat_completion=lambda *args, **kwargs: "",
        ),
        "app.services.prompts": _stub_module("app.services.prompts", PromptManager=_PromptManager),
    }
    with patch.dict(sys.modules, stubbed_modules):
        sys.modules.pop("app.services.plot_understanding", None)
        _ensure_loguru_stub_supports_config_logger()
        return importlib.import_module("app.services.plot_understanding")


class PlotUnderstandingCleanTests(unittest.TestCase):
    def test_build_full_subtitle_understanding_preserves_chunk_context_when_final_parse_fails(self):
        module = _load_plot_understanding()
        subtitle_segments = [
            {"start": 10.0, "end": 14.0, "text": "剧情开始反转"},
            {"start": 15.0, "end": 18.0, "text": "角色情绪爆发"},
        ]
        chunk_json = (
            '{"chunk_index": 1, "window_summary": "第一段", '
            '"highlight_windows": [{"start": "00:00:10,000", "end": "00:00:18,000", '
            '"category": "反转", "raw_voice_priority": "high", "reason": "关键冲突"}]}'
        )

        with patch.object(module, "_build_full_subtitle_text", return_value="x" * 20001), patch.object(
            module,
            "_split_subtitle_segments_for_llm",
            return_value=["chunk-1"],
        ), patch.object(
            module,
            "_call_chat_completion",
            side_effect=[chunk_json, "not-json"],
        ):
            result = module.build_full_subtitle_understanding(
                subtitle_segments,
                api_key="test-key",
                model="test-model",
            )

        self.assertEqual("chunked_full_subtitle", result["subtitle_input_mode"])
        self.assertTrue(str(result["subtitle_understanding_status"]).startswith("parse_failed"))
        self.assertEqual("chunk_summaries_fallback", result["highlight_windows_source"])
        self.assertEqual(1, len(result["subtitle_chunk_summaries"]))
        self.assertEqual(1, len(result["highlight_windows"]))
        self.assertEqual("00:00:10,000", result["highlight_windows"][0]["start"])
        self.assertEqual("00:00:18,000", result["highlight_windows"][0]["end"])


if __name__ == "__main__":
    unittest.main()
