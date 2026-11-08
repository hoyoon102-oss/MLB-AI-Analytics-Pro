"""Validate real API totals, historical populations and weighted league rates."""
import requests

from services.league_stats import (BASE, fetch_league_average, season_membership, sum_teams)


def main():
    for season in (2024, 2025):
        for category in ("hitting", "pitching"):
            values = {league: fetch_league_average(season, league, category) for league in (0, 103, 104)}
            for key, total in values[0]["totals"].items():
                assert total is not None, (season, category, key, "missing component")
                assert total == values[103]["totals"][key] + values[104]["totals"][key], (season, category, key)
            for league in (103, 104):
                response = requests.get(f"{BASE}/teams/stats", params={"stats": "season", "group": category,
                    "season": season, "sportIds": 1, "gameType": "R", "leagueIds": league, "limit": 1000}, timeout=30)
                response.raise_for_status()
                group = response.json()["stats"][0]
                assert group["totalSplits"] == len(values[league]["team_ids"])
                rows = group["splits"]
                assert sorted(row["team"]["id"] for row in rows) == values[league]["team_ids"]
                totals, rates = sum_teams([row["stat"] for row in rows], category)
                assert totals == values[league]["totals"]
                # Validate per-team component formulas against published API rates.
                for row in rows:
                    _, team_rates = sum_teams([row["stat"]], category)
                    for key, value in team_rates.items():
                        if key in row["stat"]:
                            tolerance = .0011 if category == "hitting" else .0051
                            assert abs(value - float(row["stat"][key])) <= tolerance, (season, category, row["team"], key)
            print("PASS:", season, category, "AL + NL = MLB; independent league filter; official team rates", values[0]["rates"], flush=True)
    membership, _ = season_membership(2012)
    astros = next(team for team in membership["teams"] if team["id"] == 117)
    assert astros["league"]["id"] == 104, "Historical membership must not use the current league"
    print("PASS: historical season affiliations (2012 Astros NL)", flush=True)


if __name__ == "__main__":
    main()
