"""Regression checks for navigation/state and truthful presentation."""
from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import streamlit as st

import components.dashboard as app
import tests.test_smart as test_smart
from tests.test_support import fix_seasons, seeded_app
from components.ui_components import PAGES, ai_status, select_player


class PresentationTests(unittest.TestCase):
    def test_connection_status_requires_real_check_and_expires(self):
        state = {"ai_enabled": True, "ai_models": ["test"], "ai_model": "test"}
        with patch("components.ui_components.st.session_state", state):
            self.assertEqual(ai_status()[0], "연결 미확인")
            state["ai_connection_check"] = {"ok": True, "at": datetime.now(timezone.utc)}
            self.assertEqual(ai_status()[0], "Ollama 확인됨")
            state["ai_connection_check"]["at"] -= timedelta(minutes=2)
            self.assertEqual(ai_status()[0], "연결 재확인 필요")
            state["ai_enabled"] = False
            self.assertEqual(ai_status()[0], "AI 꺼짐")

    def test_plot_theme_preserves_missing_data(self):
        figure = app.history_figure({2023: {"ops": ".800"}, 2024: None})
        self.assertEqual(figure.layout.paper_bgcolor, "rgba(0,0,0,0)")
        self.assertEqual(figure.data[3].y[1], None)
        self.assertFalse(figure.data[3].connectgaps)

    def test_sidebar_favorite_callback_clears_stale_widget_selection(self):
        state = {"dashboard_auto": {"result": 2}, "dashboard_result": 2,
                 "dashboard_favorite_choice": 2, "selected_season": 2024}
        with patch("components.ui_components.st.session_state", state):
            select_player({"id": 1, "fullName": "Selected"})
        self.assertEqual(state["dashboard_chosen"]["id"], 1)
        self.assertNotIn("dashboard_auto", state)
        self.assertNotIn("dashboard_favorite_choice", state)
        self.assertEqual(state["selected_season"], 2024)
        self.assertEqual(state["pro_page"], "선수 기록")


class NavigationTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        fix_seasons(self)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(os.environ, {"MLB_ANALYTICS_DATA_DIR": directory.name})
        environment.start()
        self.addCleanup(environment.stop)
        request = patch("requests.get", side_effect=self.request)
        request.start()
        self.addCleanup(request.stop)

    def request(self, url, params, **kwargs):
        if url.endswith("/teams"):
            response = Mock()
            response.json.return_value = {"teams": []}
            return response
        return test_smart.SmartUITests.request(self, url, params, **kwargs)

    def test_navigation_keeps_player_and_season_without_generating_ai(self):
        with patch("components.ai_ui.generate") as generate:
            ui = seeded_app()
            for page in PAGES:
                ui.sidebar.radio[0].set_value(page).run()
                self.assertFalse(ui.exception, page)
                self.assertEqual(ui.session_state["selected_season"], 2024)
                self.assertEqual(ui.session_state["dashboard_chosen"]["id"], 660271)
            generate.assert_not_called()

    def test_sidebar_favorite_selects_saved_player(self):
        ui = seeded_app()
        ui.button(key="dashboard_star").click().run()
        self.assertEqual(len(ui.session_state["_favorites"]), 1)
        ui.sidebar.radio[0].set_value("선수 비교").run()
        ui.button(key="sidebar_favorite_660271").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["pro_page"], "선수 기록")
        self.assertEqual(ui.session_state["dashboard_chosen"]["id"], 660271)
        self.assertEqual(len(ui.metric), 6)


if __name__ == "__main__":
    unittest.main()
