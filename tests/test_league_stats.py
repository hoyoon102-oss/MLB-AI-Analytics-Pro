"""Synthetic fixtures only; league production data always comes from MLB."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from services.league_stats import (LeagueDataError, differences, extract_population, fetch_league_average,
                          player_rates, rates_from_totals, sum_teams)
from components.league_ui import ai_league_context, comparison_figure
from services.ai_analyst import player_context


def fixtures(category="hitting"):
    teams = {"teams": [{"id": 1, "season": 2024, "sport": {"id": 1}, "league": {"id": 103}},
                       {"id": 2, "season": 2024, "sport": {"id": 1}, "league": {"id": 104}}]}
    records = [{"hits": 2, "atBats": 10, "baseOnBalls": 1, "hitByPitch": 1, "sacFlies": 1,
                "totalBases": 4, "plateAppearances": 13, "strikeOuts": 3},
               {"hits": 40, "atBats": 100, "baseOnBalls": 10, "hitByPitch": 0, "sacFlies": 0,
                "totalBases": 60, "plateAppearances": 110, "strikeOuts": 10}]
    if category == "pitching":
        records = [{"inningsPitched": "6.1", "outs": 19, "earnedRuns": 2, "baseOnBalls": 1, "hits": 4, "strikeOuts": 7},
                   {"inningsPitched": "6.2", "outs": 20, "earnedRuns": 1, "baseOnBalls": 3, "hits": 5, "strikeOuts": 8}]
    payload = {"stats": [{"type": {"displayName": "season"}, "group": {"displayName": category},
                           "totalSplits": 2, "splits": [{"season": "2024", "team": {"id": i + 1}, "stat": record}
                                                         for i, record in enumerate(records)]}]}
    return payload, teams


class AggregateTests(unittest.TestCase):
    def test_weighted_hitting_rates(self):
        payload, teams = fixtures()
        result = extract_population(payload, teams, 2024, 0, "hitting")
        rates = result["rates"]
        self.assertAlmostEqual(rates["avg"], 42 / 110)
        self.assertNotAlmostEqual(rates["avg"], (.2 + .4) / 2)
        self.assertAlmostEqual(rates["obp"], 54 / 123)
        self.assertAlmostEqual(rates["slg"], 64 / 110)
        self.assertAlmostEqual(rates["ops"], 54 / 123 + 64 / 110)
        self.assertAlmostEqual(rates["bbPercent"], 11 / 123 * 100)
        self.assertAlmostEqual(rates["kPercent"], 13 / 123 * 100)

    def test_leagues_and_season_specific_affiliations(self):
        payload, teams = fixtures()
        self.assertEqual(extract_population(payload, teams, 2024, 103, "hitting")["team_ids"], [1])
        self.assertEqual(extract_population(payload, teams, 2024, 104, "hitting")["team_ids"], [2])
        teams["teams"][0]["league"]["id"] = 104
        self.assertEqual(extract_population(payload, teams, 2024, 104, "hitting")["team_count"], 2)

    def test_pitching_uses_outs_before_aggregation(self):
        payload, teams = fixtures("pitching")
        result = extract_population(payload, teams, 2024, 0, "pitching")
        self.assertEqual(result["totals"]["outs"], 39)
        self.assertAlmostEqual(result["rates"]["era"], 3 * 9 / 13)
        self.assertAlmostEqual(result["rates"]["whip"], 13 / 13)
        self.assertAlmostEqual(result["rates"]["strikeoutsPer9Inn"], 15 * 9 / 13)
        self.assertAlmostEqual(result["rates"]["walksPer9Inn"], 4 * 9 / 13)

    def test_missing_component_is_not_partial_total(self):
        payload, teams = fixtures()
        del payload["stats"][0]["splits"][1]["stat"]["hitByPitch"]
        result = extract_population(payload, teams, 2024, 0, "hitting")
        self.assertIsNone(result["rates"]["obp"])
        self.assertIsNone(result["rates"]["ops"])
        self.assertIsNotNone(result["rates"]["avg"])

    def test_zero_denominators_and_real_zero(self):
        result = rates_from_totals({"hits": 0, "atBats": 10, "baseOnBalls": 0, "hitByPitch": 0,
                                  "sacFlies": 0, "totalBases": 0, "plateAppearances": 10, "strikeOuts": 0}, "hitting")
        self.assertEqual(result["avg"], 0)
        self.assertEqual(result["ops"], 0)
        self.assertTrue(all(value is None for value in rates_from_totals({}, "hitting").values()))
        self.assertIsNone(rates_from_totals({"outs": 0, "earnedRuns": 0}, "pitching")["era"])

    def test_total_bases_derivation_and_invalid_innings(self):
        totals, _ = sum_teams([{"hits": 10, "doubles": 2, "triples": 1, "homeRuns": 1, "atBats": 30}], "hitting")
        self.assertEqual(totals["totalBases"], 17)
        for stats in ({"inningsPitched": "6.3"}, {"inningsPitched": "6.1", "outs": 20}):
            with self.assertRaises(LeagueDataError):
                sum_teams([stats], "pitching")

    def test_invalid_population_is_rejected(self):
        payload, teams = fixtures()
        mutations = []
        for change in ("duplicate", "season", "category", "partial", "postseason"):
            bad = deepcopy(payload)
            group = bad["stats"][0]
            if change == "duplicate": group["splits"][1]["team"]["id"] = 1
            if change == "season": group["splits"][0]["season"] = "2023"
            if change == "category": group["group"]["displayName"] = "pitching"
            if change == "partial": group["splits"].pop()
            if change == "postseason": group["splits"][0]["gameType"] = "W"
            mutations.append(bad)
        for bad in mutations:
            with self.assertRaises(LeagueDataError):
                extract_population(bad, teams, 2024, 0, "hitting")

    def test_python_player_percentages_and_missing_chart_value(self):
        stats = {"baseOnBalls": 5, "plateAppearances": 100, "strikeOuts": 20, "ops": ".900"}
        self.assertEqual(player_rates(stats, "hitting")["bbPercent"], 5)
        aggregate = extract_population(*fixtures(), 2024, 0, "hitting")
        aggregate.update(source="https://statsapi.mlb.com", retrieved_at="time")
        context = player_context({"id": 3, "fullName": "Test"}, 2024, "hitting", stats, "time")
        result = ai_league_context(context, aggregate)
        self.assertIn("player_minus_league", result["league_comparison"])
        self.assertIsNone(ai_league_context(dict(context, season=2023), aggregate)["league_comparison"])
        figure = comparison_figure([{"id": 3, "fullName": "Test"}], [None], aggregate, "hitting", "ops")
        self.assertIsNone(figure.data[0].y[0])
        self.assertEqual(figure.data[1].marker.color, "#94A3B8")
        with self.assertRaises(LeagueDataError):
            differences(stats, aggregate, "pitching")

    @patch("services.league_stats.season_membership")
    @patch("services.league_stats.team_totals")
    def test_aggregate_cache_separates_scope(self, totals, membership):
        st_payload, teams = fixtures()
        totals.return_value = st_payload, "source", "time"
        membership.return_value = teams, "memberships"
        fetch_league_average.clear()
        first = fetch_league_average(2024, 103, "hitting")
        fetch_league_average(2024, 103, "hitting")
        second = fetch_league_average(2024, 104, "hitting")
        self.assertEqual(totals.call_count, 2)
        self.assertNotEqual(first["rates"]["avg"], second["rates"]["avg"])
        self.assertEqual(first["retrieved_at"], "time")
        fetch_league_average.clear()


if __name__ == "__main__":
    unittest.main()
