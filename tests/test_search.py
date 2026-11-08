from utils.paths import PROJECT_ROOT
from tests.test_support import fix_seasons
"""Offline tests using synthetic roster fixtures only."""
import unittest
from unittest.mock import Mock, patch

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

import services.player_search as search
from tests.test_pitching import response_payload

TEAMS = [{"id": 2, "name": "Beta Club"}, {"id": 1, "name": "Alpha Club"}]


def roster(team_id=1, year=2024):
    return search.normalize_roster({"roster": [
        {"person": {"id": 10, "fullName": "Sho Example", "birthDate": "1994-01-01",
                    "currentTeam": {"id": 999, "name": "Wrong Current Team"}},
         "position": {"abbreviation": "TWP"}},
        {"person": {"id": 20, "fullName": "Same Name", "birthDate": "1980-01-01"},
         "position": {"abbreviation": "RF"}},
        {"person": {"id": 21, "fullName": "Same Name", "birthDate": "1990-01-01"},
         "position": {"abbreviation": "P"}},
    ]}, {"id": team_id, "name": "Alpha Club" if team_id == 1 else "Beta Club"}, year)


class SearchTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        fix_seasons(self)

    def test_teams_sorted_deduplicated_and_season_requested(self):
        response = Mock()
        response.json.return_value = {"teams": TEAMS + [TEAMS[0]]}
        with patch("requests.get", return_value=response) as request:
            teams = search.fetch_teams(2024)
            search.fetch_teams(2024)
            search.fetch_teams(2025)
        self.assertEqual([team["name"] for team in teams], ["Alpha Club", "Beta Club"])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.kwargs["params"], {"sportId": 1, "season": 2025})

    def test_roster_full_season_never_current_roster(self):
        response = Mock()
        response.json.return_value = {"roster": [{"person": {"id": 10, "fullName": "Player"},
                                                 "position": {"abbreviation": "DH"}}]}
        with patch("requests.get", return_value=response) as request:
            search.fetch_roster(1, 2020, "Historic Name")
        self.assertEqual(request.call_args.kwargs["params"]["season"], 2020)
        self.assertEqual(request.call_args.kwargs["params"]["rosterType"], "fullSeason")

    def test_current_team_not_used_as_historical_team(self):
        person = next(player for player in roster() if player["id"] == 10)
        self.assertEqual(person["memberships"][0]["team"], "Alpha Club")
        self.assertNotIn("Wrong Current Team", search.suggestion_label(person))

    def test_traded_player_preserves_both_teams_without_duplicates(self):
        merged = search.merge_players(roster(1) + roster(2) + roster(1))
        self.assertEqual(len(merged), 3)
        self.assertEqual(len(merged[0]["memberships"]), 2)
        filtered = search.filter_players(merged, 2, "P")
        self.assertEqual({p["id"] for p in filtered}, {10, 21})
        self.assertTrue(all(m["teamId"] == 2 for p in filtered for m in p["memberships"]))

    def test_partial_case_insensitive_and_limit(self):
        self.assertEqual(search.autocomplete(roster(), "sHo")[0][1], 10)
        self.assertEqual(search.autocomplete(roster(), "NAME")[0][1], 20)
        self.assertEqual(search.autocomplete(roster(), ""), [])
        self.assertEqual(search.autocomplete(roster(), "no match"), [])
        many = [dict(roster()[0], id=index, fullName=f"Test Player {index}") for index in range(20)]
        self.assertEqual(len(search.autocomplete(many, "test")), 10)

    def test_duplicate_names_have_unique_ids_and_labels(self):
        suggestions = search.autocomplete(roster(), "Same Name")
        self.assertEqual(len(suggestions), 2)
        self.assertNotEqual(suggestions[0][0], suggestions[1][0])
        self.assertEqual({value for label, value in suggestions}, {20, 21})
        self.assertIn("Alpha Club", suggestions[0][0])
        self.assertIn("1980-01-01", suggestions[0][0])

    def test_outfield_and_two_way_positions(self):
        self.assertEqual([p["id"] for p in search.filter_players(roster(), position="OF")], [20])
        self.assertIn(10, [p["id"] for p in search.filter_players(roster(), position="P")])
        self.assertIn(10, [p["id"] for p in search.filter_players(roster(), position="DH")])
        self.assertEqual(search.filter_players(roster(), position="C"), [])

    def test_season_union_reports_partial_failures(self):
        with patch.object(search, "fetch_teams", return_value=TEAMS), patch.object(
                search, "fetch_roster", side_effect=lambda team_id, season, name:
                roster(1, season) if team_id == 1 else (_ for _ in ()).throw(requests.Timeout())):
            players, failures = search.fetch_season_players(2024)
        self.assertEqual(len(players), 3)
        self.assertEqual(failures, ["Beta Club"])

    def test_empty_and_malformed_responses(self):
        self.assertEqual(search.normalize_roster({"roster": []}, TEAMS[0], 2024), [])
        for payload in ({}, {"roster": [None]}, {"roster": [{"person": {"fullName": "No ID"}}]}):
            with self.assertRaises(search.SearchDataError):
                search.normalize_roster(payload, TEAMS[0], 2024)
        response = Mock()
        response.json.return_value = {}
        with patch("requests.get", return_value=response), self.assertRaises(search.SearchDataError):
            search.fetch_teams(2024)


class SearchUITests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        fix_seasons(self)
        self.patchers = [
            patch("components.dashboard.fetch_teams", return_value=sorted(TEAMS, key=lambda t: t["name"])),
            patch("components.dashboard.fetch_season_players", side_effect=lambda season: (search.merge_players(roster(1, season)+roster(2, season)), [])),
            patch("components.dashboard.fetch_roster", side_effect=lambda tid, season, name: roster(tid, season)),
            patch("components.dashboard.st_searchbox", side_effect=self.component),
            patch("requests.get", side_effect=self.request),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def request(self, url, params, **kwargs):
        response = Mock()
        if url.endswith("/people/10"):
            response.json.return_value = {"people": [{"id": 10, "primaryPosition": {"abbreviation": "TWP"}}]}
        elif "/people/" in url and not url.endswith("/stats"):
            response.json.return_value = {"people": [{"id": int(url.rsplit("/", 1)[1]), "primaryPosition": {"abbreviation": "OF"}}]}
        elif params.get("group") == "pitching" and "/10/" not in url:
            response.json.return_value = {"stats": []}
        else:
            response.json.return_value = response_payload(params.get("group", "hitting"))
        return response

    def component(self, callback, **kwargs):
        key = kwargs["key"]
        state = st.session_state.setdefault(key, {"search": "", "result": None})
        command = st.session_state.get("test_commands", {}).pop(key, None)
        if command:
            query, selected = command
            suggestions = callback(query)
            state.update(search=query, result=selected if selected in [value for _, value in suggestions] else None)
        return state["result"]

    def select(self, ui, key, query="sho", player_id=10):
        ui.session_state["test_commands"] = {f"{key}_auto": (query, player_id)}
        ui.run()
        self.assertFalse(ui.exception)

    def test_team_roster_autocomplete_selection_stable_and_reset(self):
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        ui.radio(key="dashboard_mode").set_value("이름 검색").run()
        self.assertEqual(ui.selectbox(key="dashboard_team").options,
                         ["전체 팀 (All Teams)", "Alpha Club", "Beta Club"])
        ui.selectbox(key="dashboard_team").set_value(1).run()
        self.select(ui, "dashboard")
        self.assertEqual(len(ui.metric), 6)
        self.assertEqual(ui.session_state["dashboard_selected"], 10)
        ui.slider(key="history_range").set_value((2023, 2024)).run()
        self.assertEqual(ui.session_state["dashboard_selected"], 10)
        ui.radio(key="dashboard_stats_category").set_value("pitching").run()
        self.assertEqual(len(ui.metric), 14)
        self.assertEqual(ui.session_state["dashboard_selected"], 10)
        ui.button(key="dashboard_reset").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox(key="dashboard_team").value, 0)
        self.assertFalse(ui.metric)

    def test_season_or_position_change_clears_stale_selection(self):
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        ui.radio(key="dashboard_mode").set_value("이름 검색").run()
        self.select(ui, "dashboard", "same", 20)
        ui.selectbox(key="dashboard_position").set_value("P").run()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.metric)
        self.select(ui, "dashboard")
        ui.selectbox(key="selected_season").set_value(2020).run()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.metric)
        self.assertIn("2020", ui.expander[0].label)

    def test_comparison_filters_are_independent(self):
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        ui.sidebar.radio[0].set_value("선수 비교").run()
        for key in ("compare_0", "compare_1"):
            ui.radio(key=f"{key}_mode").set_value("이름 검색").run()
        ui.selectbox(key="compare_0_team").set_value(1).run()
        ui.selectbox(key="compare_1_team").set_value(2).run()
        self.select(ui, "compare_0", "same", 20)
        self.select(ui, "compare_1", "same", 21)
        self.assertEqual(ui.selectbox(key="compare_0_team").value, 1)
        self.assertEqual(ui.selectbox(key="compare_1_team").value, 2)
        self.assertEqual(len(ui.table), 1)
        self.assertEqual(len(ui.get("plotly_chart")), 3)  # Includes advanced comparison.
        def pitchers(url, params, **kwargs):
            response = Mock()
            if url.endswith("/stats"):
                response.json.return_value = response_payload("pitching") if params.get("group") == "pitching" else {"stats": []}
            else:
                response.json.return_value = {"people": [{"id": int(url.rsplit("/", 1)[1])}]}
            return response
        st.cache_data.clear()
        with patch("requests.get", side_effect=pitchers):
            ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.table[0].value), 14)
        self.assertEqual(len(ui.get("plotly_chart")), 2)  # Includes advanced pitcher comparison.

    def test_api_failure_and_empty_roster_ui(self):
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        with patch("components.dashboard.fetch_teams", side_effect=requests.Timeout()):
            ui.radio(key="dashboard_mode").set_value("이름 검색").run()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.error)
        self.assertFalse(ui.metric)
        with patch("components.dashboard.fetch_season_players", return_value=([], [])):
            ui.run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("조건에 맞는" in item.value for item in ui.info))


if __name__ == "__main__":
    unittest.main()
