from utils.paths import PROJECT_ROOT
"""Bilingual rendering, persistence, and AI language regression checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services.ai_analyst import generate
from utils.i18n import catalog, load_language, save_language, t, tr
from tests.test_ai_ui import PANEL_APP
from tests.test_support import seeded_app
import tests.test_pro_ui as test_pro_ui
from tests.test_league_stats import fixtures
from services.league_stats import extract_population


class TranslationTests(unittest.TestCase):
    def test_catalogs_have_matching_keys_and_fallbacks(self):
        self.assertEqual(set(catalog("ko")), set(catalog("en")))
        self.assertEqual(t("player_statistics", locale="en"), "Player Statistics")
        self.assertEqual(t("player_statistics", locale="ko"), "선수 기록")
        self.assertEqual(t("player_statistics", locale="missing"), "선수 기록")
        self.assertEqual(t("unknown_key", locale="en"), "unknown_key")
        self.assertEqual(tr("Shohei Ohtani", "en"), "Shohei Ohtani")
        self.assertEqual(tr("ERA · 평균자책점", "en"), "ERA · Earned run average")

    def test_language_persistence_without_changing_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertEqual(load_language(path), "ko")
            path.write_text(json.dumps({"other": 123}), encoding="utf-8")
            save_language("en", path)
            self.assertEqual(load_language(path), "en")
            self.assertEqual(json.loads(path.read_text())["other"], 123)
            save_language("ko", path)
            self.assertEqual(load_language(path), "ko")
            path.write_text("invalid JSON", encoding="utf-8")
            self.assertEqual(load_language(path), "ko")
            with self.assertRaises(ValueError):
                save_language("xx", path)

    @patch("services.ai_analyst.list_models", return_value=["small"])
    @patch("services.ai_analyst._request", return_value={"message": {"content": "English analysis"}})
    def test_english_prompt_and_verified_context(self, request, models):
        context = {"category": "hitting", "league_comparison": {"rates": {"ops": .7}}}
        generate("small", context, "Explain", language="en")
        body = request.call_args.kwargs["json"]
        self.assertIn("exclusively in English", body["messages"][0]["content"])
        self.assertIn("HITTING ONLY", body["messages"][0]["content"])
        self.assertIn("BENCHMARK", body["messages"][0]["content"])
        self.assertIn("league_comparison", body["messages"][1]["content"])

    @patch("components.ai_ui.generate", return_value="한국어 원본 보고서")
    def test_language_switch_retains_old_report_without_generation(self, generate):
        source = PANEL_APP + '\nst.selectbox("Language", ["ko", "en"], key="ui_language")\n'
        ui = AppTest.from_string(source).run()
        ui.button(key="ai_prepare").click().run()
        ui.button(key="ai_scout_generate").click().run()
        self.assertFalse(ui.exception)
        generate.assert_called_once()
        ui.selectbox(key="ui_language").set_value("en").run()
        self.assertFalse(ui.exception)
        generate.assert_called_once()
        self.assertTrue(any("generated in" in item.value for item in ui.info))
        self.assertTrue(any(item.value == "한국어 원본 보고서" for item in ui.markdown))

    @patch("components.ai_ui.generate")
    def test_scouting_requires_verified_selected_season(self, generate):
        source = PANEL_APP.replace('"hitting", {"ops": ".900"}, "time", history, awards)',
                                   '"hitting", None, "time", history, awards)')
        ui = AppTest.from_string(source).run()
        ui.button(key="ai_prepare").click().run()
        self.assertFalse(ui.exception)
        self.assertFalse(any(button.key == "ai_scout_generate" for button in ui.button))
        self.assertTrue(any("확인된 시즌 통계가 없어" in item.value for item in ui.info))
        generate.assert_not_called()


class BilingualUITests(unittest.TestCase):
    setUp = test_pro_ui.NavigationTests.setUp
    request = test_pro_ui.NavigationTests.request

    def test_enabled_league_and_two_way_switch_use_matching_category(self):
        def aggregate(season, league_id, category):
            result = extract_population(*fixtures(category), season, league_id, category)
            result.update(source="https://statsapi.mlb.com/api/v1/teams/stats", membership_source="test", retrieved_at="time")
            return result
        with patch("components.league_ui.fetch_league_average", side_effect=aggregate) as fetch:
            ui = seeded_app()
            ui.toggle(key="league_enabled").set_value(True).run()
            self.assertFalse(ui.exception)
            self.assertEqual(fetch.call_args.args[2], "hitting")
            self.assertEqual(len(ui.get("plotly_chart")), 4)  # Includes advanced comparison and trends.
            ui.radio(key="dashboard_stats_category").set_value("pitching").run()
            self.assertFalse(ui.exception)
            self.assertEqual(fetch.call_args.args[2], "pitching")

    def test_league_timeout_keeps_player_statistics(self):
        import requests
        with patch("components.league_ui.fetch_league_average", side_effect=requests.Timeout()):
            ui = seeded_app()
            ui.toggle(key="league_enabled").set_value(True).run()
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.metric), 6)
            self.assertTrue(any("리그 평균을 확인할 수 없습니다" in item.value for item in ui.warning))
    def test_english_ui_keeps_player_season_and_internal_categories(self):
        ui = seeded_app()
        ui.selectbox(key="ui_language").set_value("en").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["dashboard_chosen"]["id"], 660271)
        self.assertEqual(ui.session_state["selected_season"], 2024)
        self.assertEqual(ui.selectbox(key="selected_season").label, "Season")
        self.assertIn("Name search", ui.radio(key="dashboard_mode").options)
        ui.sidebar.radio[0].set_value("선수 기록").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["pro_page"], "선수 기록")
        # A new Streamlit session reads the persisted preference.
        restarted = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        self.assertEqual(restarted.selectbox(key="ui_language").value, "en")
        self.assertEqual(restarted.selectbox(key="selected_season").label, "Season")


if __name__ == "__main__":
    unittest.main()
