#!/usr/bin/env python
"""Audit native movie_story migration status."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.movie_story.architecture_guard import find_direct_legacy_imports
from app.services.movie_story.engine_status import get_engine_status


def main() -> int:
    root = ROOT
    report = {
        "engine_status": get_engine_status(),
        "legacy_imports": find_direct_legacy_imports(root / "app"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["legacy_imports"].get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
