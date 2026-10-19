# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from app.services import task


def test_video_font_name_canonicalizes_legacy_simhei_alias() -> None:
    """旧 UI/旧构建产物传入 SimHei 时，应迁移成真实字体文件路径。"""
    assert task._canonicalize_video_font_name("SimHei") == "C:/Windows/Fonts/simhei.ttf"


def test_video_font_name_canonicalizes_blank_to_contract_default() -> None:
    """空字体值应使用视频合成合同中的真实默认字体路径。"""
    assert task._canonicalize_video_font_name("") == "C:/Windows/Fonts/simhei.ttf"
    assert task._canonicalize_video_font_name(None) == "C:/Windows/Fonts/simhei.ttf"


def test_video_font_name_keeps_explicit_font_path() -> None:
    """明确传入的其它字体路径不应被偷偷替换。"""
    font = "D:/fonts/custom.ttf"
    assert task._canonicalize_video_font_name(font) == font


def test_schema_video_font_default_is_real_windows_font_path() -> None:
    """schema 默认值不应再是无法打开的 SimHei stem。"""
    schema = Path("app/models/schema.py").read_text(encoding="utf-8")
    assert 'font_name: str = "C:/Windows/Fonts/simhei.ttf"' in schema
    assert 'font_name: str = "SimHei"' not in schema


def test_frontend_no_video_payload_hardcodes_simhei() -> None:
    """前端源码和构建产物不应再提交 font_name/fontName=SimHei。"""
    roots = [
        Path("web/src"),
        Path("web/dist"),
        Path("frontend/src"),
        Path("frontend/dist"),
    ]
    suffixes = {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".json"}
    violations: list[str] = []

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            compact = text.replace(" ", "")
            if 'font_name:"SimHei"' in compact or 'fontName:"SimHei"' in compact:
                violations.append(str(path).replace("\\", "/"))

    assert violations == []
