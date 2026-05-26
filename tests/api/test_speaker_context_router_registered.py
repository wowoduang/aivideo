# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_speaker_context_router_registered.py

测试 speaker_context router 已挂载到主 FastAPI app。
"""

import unittest

from fastapi.routing import APIRoute

from app.api.main import app


class TestSpeakerContextRouterRegistered(unittest.TestCase):
    """speaker_context router 挂载测试。"""

    def test_speaker_context_routes_are_registered_under_api_v1(self) -> None:
        """主应用必须包含 speaker_context 三个接口。"""
        paths = {
            route.path
            for route in app.routes
            if isinstance(route, APIRoute)
        }

        self.assertIn("/api/v1/speaker-context/preview", paths)
        self.assertIn("/api/v1/speaker-context/bound-context", paths)
        self.assertIn("/api/v1/speaker-context/context", paths)


if __name__ == "__main__":
    unittest.main()
