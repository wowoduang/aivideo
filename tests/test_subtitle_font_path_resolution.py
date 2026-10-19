# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import generate_video


def test_resolve_subtitle_font_path_accepts_absolute_existing_font(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实绝对字体路径应原样通过校验，避免被拼到 workspace/fonts 下。"""
    font_file = tmp_path / "simhei.ttf"
    font_file.write_bytes(b"fake-font-content")

    calls: list[str] = []

    def fake_truetype(font: str, size: int) -> object:
        calls.append(font)
        return object()

    monkeypatch.setattr(generate_video.ImageFont, "truetype", fake_truetype)

    resolved = generate_video._resolve_subtitle_font_path(str(font_file))

    assert resolved == str(font_file).replace("\\", "/")
    assert calls == [str(font_file).replace("\\", "/")]


def test_resolve_subtitle_font_path_accepts_workspace_stem_font(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """短字体名 SimHei 应只解析到 workspace fonts 中实际存在的同 stem 字体文件。"""
    font_file = tmp_path / "SimHei.ttf"
    font_file.write_bytes(b"fake-font-content")

    calls: list[str] = []

    def fake_truetype(font: str, size: int) -> object:
        calls.append(font)
        return object()

    monkeypatch.setattr(generate_video.utils, "font_dir", lambda: str(tmp_path))
    monkeypatch.setattr(generate_video.ImageFont, "truetype", fake_truetype)

    resolved = generate_video._resolve_subtitle_font_path("SimHei")

    assert resolved == str(font_file).replace("\\", "/")
    assert calls == [str(font_file).replace("\\", "/")]


def test_resolve_subtitle_font_path_rejects_missing_workspace_stem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """短字体名没有对应真实字体文件时应明确报错。"""
    monkeypatch.setattr(generate_video.utils, "font_dir", lambda: str(tmp_path))

    with pytest.raises(FileNotFoundError):
        generate_video._resolve_subtitle_font_path("SimHei")


def test_schema_default_font_points_to_windows_font_file() -> None:
    """视频合成请求默认字体不应再是 workspace 中不存在的 SimHei stem。"""
    schema_path = Path("app/models/schema.py")
    text = schema_path.read_text(encoding="utf-8")

    assert 'font_name: str = "C:/Windows/Fonts/simhei.ttf"' in text
    assert 'font_name: str = "SimHei"' not in text
