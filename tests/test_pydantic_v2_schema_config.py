# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import warnings

from pydantic.warnings import PydanticDeprecatedSince20


def test_material_info_dataclass_uses_pydantic_v2_configdict() -> None:
    """MaterialInfo 的 dataclass config 不应再触发 Pydantic v2 class-based config 警告。"""
    import app.models.schema as schema

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        reloaded = importlib.reload(schema)
        reloaded.MaterialInfo()

    deprecated = [item for item in captured if issubclass(item.category, PydanticDeprecatedSince20)]
    assert deprecated == []
