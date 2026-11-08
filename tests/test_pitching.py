from tests.test_support import fix_seasons
"""Synthetic test-only fixtures: production never uses these statistics."""
import unittest
from unittest.mock import Mock, patch

import requests
import streamlit as st

import components.dashboard as app
from services.player_stats import DataError
from tests.test_support import seeded_app
from analytics.pitching import innings_to_outs, outs_to_innings, pitching_stats, chart_value

RAW = {"inningsPitched": "6.1", "earnedRuns": 2, "hits": 4, "baseOnBalls": 2,
       "strikeOuts": 7, "wins": 1, "losses": 0, "homeRuns": 1, "gamesStarted": 1,
       "saves": 0, "battersFaced": 25}


def response_payload(category, year=2024, stats=None):
    if stats is None:
        stats = RAW if category == "pitching" else {"avg": ".250", "obp": ".350",
            "slg": ".500", "ops": ".850", "homeRuns": 10, "rbi": 30}
    return {"stats": [{"group": {"displayName": category}, "splits": [
        {"season": str(year), "gameType": "R", "sport": {"id": 1}, "stat": stats}]}]}


class InningsTests(unittest.TestCase):
    def test_baseball_not_decimal(self):
        for value, outs in [("6.1", 19), ("6.2", 20), ("0.1", 1), ("0.2", 2),
                            ("0.0", 0), ("200.0", 600), (6, 18), ("6", 18)]:
            with self.subTest(value=value):
                self.assertEqual(innings_to_outs(value), outs)
                self.assertEqual(innings_to_outs(outs_to_innings(outs)), outs)
        self.assertAlmostEqual(chart_value({"inningsPitched": "6.1"}, "inningsPitched"), 19 / 3)

    def test_invalid_notation(self):
        for value in (None, "", "6.3", "6.10", "-1.0", "NaN", "inf", True, "6.33"):
            self.assertIsNone(innings_to_outs(value))

    def test_missing_rates_derived_using_outs(self):
        stats = pitching_stats(RAW)
        self.assertEqual(stats["era"], "2.84")
        self.assertEqual(stats["whip"], "0.95")
        self.assertEqual(stats["strikeoutsPer9Inn"], "9.95")
        self.assertEqual(stats["walksPer9Inn"], "2.84")
        self.assertEqual(stats["strikeoutWalkRatio"], "3.50")
        self.assertEqual(len(stats["_derived"]), 5)
        self.assertNotIn("era", RAW)  # No mutation of source data.

    def test_existing_api_rates_preserved(self):
        stats = pitching_stats(dict(RAW, era="2.80", whip="0.94", strikeoutsPer9Inn="9.94"))
        self.assertEqual(stats["era"], "2.80")
        self.assertEqual(stats["whip"], "0.94")
        self.assertNotIn("era", stats["_derived"])

    def test_outs_fallback_and_missing_sources(self):
        stats = pitching_stats({"outs": 19, "strikeOuts": 7})
        self.assertEqual(stats["inningsPitched"], "6.1")
        self.assertEqual(stats["strikeoutsPer9Inn"], "9.95")
        self.assertIsNone(stats["whip"])
        self.assertIsNone(stats["walksPer9Inn"])
        self.assertIsNone(stats["strikeoutWalkRatio"])
        self.assertIsNone(pitching_stats({"outs": 1.5})["inningsPitched"])

    def test_zero_innings_and_zero_walks(self):
        stats = pitching_stats(dict(RAW, inningsPitched="0.0", era="0.00", whip="0.00"))
        for key in ("era", "whip", "strikeoutsPer9Inn", "walksPer9Inn"):
            self.assertIsNone(stats[key])
        stats = pitching_stats(dict(RAW, baseOnBalls=0, strikeoutWalkRatio="-.--"))
        self.assertIsNone(stats["strikeoutWalkRatio"])
        self.assertEqual(stats["walksPer9Inn"], "0.00")
        self.assertEqual(stats["baseOnBalls"], 0)

    def test_invalid_rates_can_be_derived_but_missing_data_not_invented(self):
        self.assertEqual(pitching_stats(dict(RAW, era="-.--"))["era"], "2.84")
        self.assertIsNone(pitching_stats({"inningsPitched": "6.1"})["era"])
        self.assertIsNone(pitching_stats({"strikeOuts": 7})["strikeoutsPer9Inn"])


class PitchingIntegrationTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        fix_seasons(self)

    def request(self, url, params, **kwargs):
        response = Mock()
        if url.endswith("/people/660271"):
            response.json.return_value = {"people": [{"id": 660271, "primaryPosition": {"abbreviation": "TWP"}}]}
        elif not url.endswith("/stats") and "/people/" in url and not url.endswith("people/search"):
            response.json.return_value = {"people": [{"id": int(url.rsplit("/", 1)[1]), "primaryPosition": {"abbreviation": "P"}}]}
        elif url.endswith("people/search"):
            response.json.return_value = {"people": [{"id": 660271, "fullName": "Shohei Ohtani",
                                                      "birthDate": "1994-07-05"}]}
        else:
            response.json.return_value = response_payload(params["group"])
        return response

    def test_category_routing_and_cache_isolation(self):
        with patch("requests.get", side_effect=self.request) as request:
            hitting, _ = app.fetch_stats(660271, 2024, "hitting")
            pitching, timestamp = app.fetch_stats(660271, 2024, "pitching")
            app.fetch_stats(660271, 2024, "pitching")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(hitting["_group"], "hitting")
        self.assertEqual(pitching["_group"], "pitching")
        self.assertIn("UTC", timestamp)
        self.assertNotIn("era", hitting)
        self.assertNotIn("avg", pitching)

    def test_mixed_comparison_rejected(self):
        with self.assertRaises(DataError):
            app.validate_comparison([{"_group": "hitting"}, {"_group": "pitching"}], "pitching")
        with self.assertRaises(DataError):
            app.fetch_stats(1, 2024, "invalid")

    def test_pitching_history_gaps_and_ip_hover(self):
        with patch("requests.get", side_effect=self.request):
            records, problems, timestamp = app.fetch_history(1, 2020, 2026, "pitching")
        self.assertFalse(problems)
        self.assertIsNone(records[2023])
        self.assertIn("UTC", timestamp)
        figure = app.history_figure(records, "pitching")
        self.assertEqual(len(figure.data), 5)
        ip = figure.data[3]
        self.assertAlmostEqual(ip.y[4], 19 / 3)
        self.assertEqual(ip.customdata[4], "6.1")
        self.assertIsNone(ip.y[3])
        self.assertFalse(ip.connectgaps)

    def test_comparison_charts_keep_zero_and_missing_distinct(self):
        players = [{"id": 1, "fullName": "Same Name"}, {"id": 2, "fullName": "Same Name"}]
        stats = pitching_stats(dict(RAW, strikeOuts=0))
        figure = app.comparison_figure(players, [stats, None], app.PITCH_COMPARE_KEYS, "pitching")
        self.assertEqual(len(figure.data), 12)
        self.assertEqual(figure.data[4].y[0], 0)
        self.assertEqual(figure.data[4].customdata[0], "0")
        self.assertIsNone(figure.data[5].y[0])
        self.assertNotEqual(figure.data[0].name, figure.data[1].name)
        self.assertAlmostEqual(figure.data[6].y[0], 19 / 3)

    def test_pitcher_dashboard_and_two_way_switch(self):
        with patch("requests.get", side_effect=self.request):
            ui = seeded_app()
            self.assertEqual(len(ui.metric), 6)
            ui.radio(key="dashboard_stats_category").set_value("pitching").run()
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.metric), 14)
            self.assertEqual(ui.selectbox(key="selected_season").options, [str(y) for y in range(2020, 2027)])
            self.assertEqual(len(ui.get("plotly_chart")), 3)  # Standard, advanced, trends.
            ui.radio(key="dashboard_stats_category").set_value("hitting").run()
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.metric), 6)
            self.assertEqual(ui.radio(key="dashboard_mode").options, ["이름 검색", "즐겨찾기"])

    def test_pitcher_comparison_and_small_sample_guidance(self):
        with patch("requests.get", side_effect=self.request):
            ui = seeded_app()
            ui.sidebar.radio[0].set_value("선수 비교").run()
            ui.session_state["compare_1_chosen"] = {"id": 543037, "fullName": "Gerrit Cole"}
            ui.radio(key="compare_0_stats_category").set_value("pitching").run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.table), 1)
        self.assertEqual(len(ui.table[0].value), 14)
        self.assertEqual(len(ui.get("plotly_chart")), 2)  # Includes advanced comparison.
        self.assertTrue(any("30이닝" in warning.value for warning in ui.warning))
        self.assertTrue(any("ERA" in info.value and "IP" in info.value for info in ui.info))

    def test_pitcher_missing_records_and_api_failure(self):
        def missing(url, params, **kwargs):
            response = Mock()
            response.json.return_value = {"stats": []}
            return response
        with patch("requests.get", side_effect=missing):
            ui = seeded_app()
            self.assertFalse(ui.exception)
            self.assertFalse(ui.metric)
            self.assertTrue(any("해당 시즌 기록 없음" in info.value for info in ui.info))
        st.cache_data.clear()
        with patch("requests.get", side_effect=requests.Timeout()):
            ui.run()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.error)

    def test_pitcher_search_and_comparison_partial_failure(self):
        with patch("requests.get", side_effect=self.request):
            ui = seeded_app()
            ui.radio(key="dashboard_stats_category").set_value("pitching").run()
            ui.radio(key="dashboard_mode").set_value("이름 검색")
            ui.session_state["dashboard_scope"] = "전체 시대 이름 검색"
            ui.run()
            ui.text_input(key="dashboard_query").set_value("Ohtani")
            next(button for button in ui.button if button.label == "선수 검색").click().run()
            self.assertFalse(ui.exception)
            ui.selectbox(key="dashboard_result").set_value(660271).run()
            self.assertEqual(len(ui.metric), 14)
            ui.sidebar.radio[0].set_value("선수 비교").run()
            ui.session_state["compare_1_chosen"] = {"id": 543037, "fullName": "Gerrit Cole"}
            ui.radio(key="compare_0_stats_category").set_value("pitching").run()
        st.cache_data.clear()
        def partial(url, **kwargs):
            if "543037" in url:
                raise requests.ConnectionError()
            return self.request(url, **kwargs)
        with patch("requests.get", side_effect=partial):
            ui.run()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.error)
        self.assertEqual(len(ui.table), 0)
        self.assertEqual(len(ui.get("plotly_chart")), 0)


if __name__ == "__main__":
    unittest.main()
