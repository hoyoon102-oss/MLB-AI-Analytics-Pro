from tests.test_support import fix_seasons
"""Offline checks for missing data, API failures, and UI controls."""
import unittest
from unittest.mock import Mock, patch

import requests
import streamlit as st

import components.dashboard as app
from services.player_stats import DataError, extract_stats
from tests.test_support import seeded_app, choose_restored


class DashboardTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        fix_seasons(self)

    def run_ui(self, payload=None, error=None):
        response = Mock()
        response.json.return_value = payload
        with patch("requests.get", return_value=response, side_effect=error):
            ui = seeded_app()
        self.assertEqual(len(ui.exception), 0)
        return ui

    def test_empty_season(self):
        ui = self.run_ui({"stats": []})
        self.assertGreaterEqual(len(ui.info), 1)
        self.assertEqual(len(ui.metric), 0)
        self.assertEqual(ui.radio(key="dashboard_mode").options, ["이름 검색", "즐겨찾기"])
        self.assertEqual(ui.selectbox(key="selected_season").options, [str(year) for year in range(2020, 2027)])

    def test_missing_fields_and_real_zero(self):
        # Synthetic fixture only for error handling, never dashboard data.
        ui = self.run_ui({"stats": [{"group": {"displayName": "hitting"},
            "splits": [{"season": "2024", "stat": {"homeRuns": 0}}]}]})
        self.assertEqual(len(ui.metric), 6)
        self.assertEqual(ui.metric[0].value, "—")
        self.assertEqual(ui.metric[4].value, "0")
        self.assertGreaterEqual(len(ui.warning), 1)

    def test_network_errors(self):
        for error in (requests.Timeout(), requests.ConnectionError(), requests.HTTPError()):
            with self.subTest(error=type(error).__name__):
                st.cache_data.clear()
                ui = self.run_ui(error=error)
                self.assertGreaterEqual(len(ui.error), 1)
                self.assertEqual(len(ui.metric), 0)

    def test_invalid_response(self):
        for payload in (None, {}, {"stats": "invalid"}, {"stats": [None]}):
            with self.subTest(payload=payload):
                st.cache_data.clear()
                self.assertGreaterEqual(len(self.run_ui(payload).error), 1)

    def test_invalid_json(self):
        response = Mock()
        response.json.side_effect = ValueError("Invalid JSON")
        with patch("requests.get", return_value=response):
            ui = seeded_app()
        self.assertEqual(len(ui.exception), 0)
        self.assertGreaterEqual(len(ui.error), 1)


# Synthetic fixtures are restricted to tests; production always queries MLB.
PEOPLE = [
    {"id": 1, "fullName": "Same Name", "birthDate": "1980-01-01"},
    {"id": 2, "fullName": "Same Name", "birthDate": "1990-01-01"},
]


def season_payload(stat=None):
    return {"stats": [{"group": {"displayName": "hitting"}, "splits": [
        {"season": "2024", "gameType": "R", "sport": {"id": 1},
         "stat": stat or {"avg": ".250", "obp": ".350", "slg": ".500",
                          "ops": ".850", "homeRuns": 10, "rbi": 30}}
    ]}]}


class NewFeatureTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        fix_seasons(self)

    def request(self, url, params, **kwargs):
        response = Mock()
        response.json.return_value = ({"people": PEOPLE + [PEOPLE[0]]}
                                      if url.endswith("people/search") else season_payload())
        return response

    def test_search_preserves_names_and_deduplicates_ids(self):
        with patch("requests.get", side_effect=self.request) as request:
            people = app.search_players(" Same Name ")
        self.assertEqual([person["id"] for person in people], [1, 2])
        self.assertNotEqual(app.player_label(people[0]), app.player_label(people[1]))
        self.assertEqual(request.call_args.kwargs["params"]["names"], "Same Name")
        self.assertEqual(request.call_args.kwargs["params"]["sportIds"], 1)

    def test_empty_search_and_invalid_search(self):
        with patch("requests.get") as request:
            self.assertEqual(app.search_players("  "), [])
            request.assert_not_called()
        response = Mock()
        response.json.return_value = {"people": [{"fullName": "Missing ID"}]}
        with patch("requests.get", return_value=response), self.assertRaises(DataError):
            app.search_players("Name")

    def test_history_missing_season_is_gap(self):
        with patch("requests.get", side_effect=self.request) as request:
            records, problems, _ = app.fetch_history(1, 2024, 2026)
        self.assertFalse(problems)
        self.assertIsNone(records[2025])
        figure = app.history_figure(records)
        self.assertEqual(list(figure.data[0].y), [.25, None, None])
        self.assertFalse(figure.data[0].connectgaps)
        self.assertEqual(request.call_args.kwargs["params"]["gameType"], "R")
        self.assertEqual(len(figure.data), 4)

    def test_combined_team_total_and_regular_season_filter(self):
        payload = season_payload()
        split = payload["stats"][0]["splits"][0]
        payload["stats"][0]["splits"] += [
            dict(split, team={"id": 1}, stat={"avg": ".100"}),
            dict(split, team={"id": 2}, stat={"avg": ".900"}),
            dict(split, gameType="P", stat={"avg": ".999"}),
        ]
        self.assertEqual(extract_stats(payload, 2024)["avg"], ".250")
        payload["stats"][0]["splits"].pop(0)
        with self.assertRaises(DataError):
            extract_stats(payload, 2024)

    def test_comparison_same_names_do_not_overwrite_and_missing_is_not_zero(self):
        figure = app.comparison_figure(PEOPLE, [{"avg": ".250"}, None], app.RATE_KEYS)
        self.assertNotEqual(figure.data[0].name, figure.data[1].name)
        self.assertEqual(list(figure.data[1].y), [None] * 4)

    def test_search_ui_and_result_selection(self):
        with patch("requests.get", side_effect=self.request):
            ui = seeded_app()
            ui.radio(key="dashboard_mode").set_value("이름 검색")
            ui.session_state["dashboard_scope"] = "전체 시대 이름 검색"
            ui.run()
            ui.text_input(key="dashboard_query").set_value("Same Name")
            next(button for button in ui.button if button.label == "선수 검색").click().run()
            self.assertEqual(len(ui.selectbox(key="dashboard_result").options), 2)
            ui.selectbox(key="dashboard_result").set_value(2).run()
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.metric), 6)
            # A new empty search must clear the old selection and data.
            ui.text_input(key="dashboard_query").set_value("")
            next(button for button in ui.button if button.label == "선수 검색").click().run()
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.metric), 0)
            self.assertTrue(ui.warning)

    def test_search_error_ui(self):
        with patch("requests.get", side_effect=self.request):
            ui = seeded_app()
            ui.radio(key="dashboard_mode").set_value("이름 검색")
            ui.session_state["dashboard_scope"] = "전체 시대 이름 검색"
            ui.run()
        with patch("requests.get", side_effect=requests.Timeout()):
            ui.text_input(key="dashboard_query").set_value("Name")
            next(button for button in ui.button if button.label == "선수 검색").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.error)
        self.assertFalse(ui.metric)

    def test_comparison_ui_same_player_and_partial_failure(self):
        with patch("requests.get", side_effect=self.request):
            ui = seeded_app()
            ui.sidebar.radio[0].set_value("선수 비교").run()
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.table), 1)
            self.assertEqual(len(ui.get("plotly_chart")), 3)  # Includes advanced comparison.
            choose_restored(ui, "compare_1", "Shohei Ohtani")
            self.assertTrue(ui.warning)
            self.assertFalse(ui.table)
        st.cache_data.clear()
        def partial_request(url, **kwargs):
            if "592450" in url:
                raise requests.ConnectionError()
            return self.request(url, **kwargs)
        with patch("requests.get", side_effect=partial_request):
            choose_restored(ui, "compare_1", "Aaron Judge")
        self.assertFalse(ui.exception)
        self.assertTrue(ui.error)
        self.assertEqual(len(ui.table), 0)
        self.assertEqual(len(ui.get("plotly_chart")), 0)


if __name__ == "__main__":
    unittest.main()
