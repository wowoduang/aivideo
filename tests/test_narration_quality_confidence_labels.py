# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.narration_quality import _normalize_evidence_confidence


def test_evidence_confidence_accepts_known_asr_label() -> None:
    """ASR 来源标签应明确映射为数值置信度。"""
    confidence = _normalize_evidence_confidence(
        {"confidence": "asr_high"},
        source="audit.audio",
        index=0,
    )

    assert confidence == pytest.approx(0.90)


def test_evidence_confidence_accepts_numeric_string() -> None:
    """数值字符串仍按数值置信度处理。"""
    confidence = _normalize_evidence_confidence(
        {"confidence": "0.81"},
        source="audit.visual",
        index=1,
    )

    assert confidence == pytest.approx(0.81)


def test_evidence_confidence_uses_existing_default_when_missing() -> None:
    """缺失置信度时保留既有默认值。"""
    confidence = _normalize_evidence_confidence({}, source="script_items", index=2)

    assert confidence == pytest.approx(0.72)


def test_evidence_confidence_rejects_unknown_label() -> None:
    """未知字符串标签必须直接报错，避免静默吞掉数据契约问题。"""
    with pytest.raises(ValueError, match="Unsupported evidence confidence label"):
        _normalize_evidence_confidence(
            {"confidence": "unknown_high"},
            source="audit.audio",
            index=3,
        )


def test_evidence_confidence_rejects_out_of_range_value() -> None:
    """置信度必须在 0~1 范围内。"""
    with pytest.raises(ValueError, match="Evidence confidence out of range"):
        _normalize_evidence_confidence(
            {"confidence": 1.5},
            source="audit.audio",
            index=4,
        )

def test_build_evidence_pack_uses_default_confidence_without_idx_scope_error() -> None:
    """script evidence 缺失 confidence 时应正常构建，不应出现 idx/index 变量错误。"""
    from app.services.narration_quality import build_evidence_pack

    evidence = build_evidence_pack(
        script_items=[
            {
                "id": "s1",
                "timestamp": "00:00:01,000-00:00:06,000",
                "originalSubtitle": "男主走进地下室，听到门后有声音。",
                "narration": "男主进入地下室后发现异常。",
            }
        ],
        highlights=[],
        audit={},
    )

    assert evidence
    assert evidence[0]["confidence"] == pytest.approx(0.72)

