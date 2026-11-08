"""Weighted MLB regular-season league context from verified team totals."""
from datetime import datetime, timezone

import requests
from services.cache_manager import persistent, observe
import streamlit as st

from analytics.pitching import innings_to_outs, number, outs_to_innings, pitching_stats

BASE = "https://statsapi.mlb.com/api/v1"
LEAGUES = {0: "MLB 전체 (MLB Overall)", 103: "아메리칸리그 (AL)", 104: "내셔널리그 (NL)"}
HIT_KEYS = ("avg", "obp", "slg", "ops", "bbPercent", "kPercent")
PITCH_KEYS = ("era", "whip", "strikeoutsPer9Inn", "walksPer9Inn")
LABELS = {"avg": "AVG", "obp": "OBP", "slg": "SLG", "ops": "OPS", "bbPercent": "BB%", "kPercent": "K%",
          "era": "ERA", "whip": "WHIP", "strikeoutsPer9Inn": "K/9", "walksPer9Inn": "BB/9"}
LOWER = {"era", "whip", "walksPer9Inn", "kPercent"}


class LeagueDataError(ValueError):
    """Incomplete population must never masquerade as a league average."""


def count(value):
    value = number(value)
    return int(value) if value is not None and value.is_integer() else None


def ratio(numerator, denominator, scale=1):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator * scale


def rates_from_totals(totals, category):
    """No rounded team/player rate is ever averaged."""
    if category == "hitting":
        hits, ab, bb, hbp, sf, tb, pa, so = (totals.get(key) for key in (
            "hits", "atBats", "baseOnBalls", "hitByPitch", "sacFlies", "totalBases", "plateAppearances", "strikeOuts"))
        obp = None
        if all(value is not None for value in (hits, ab, bb, hbp, sf)):
            obp = ratio(hits + bb + hbp, ab + bb + hbp + sf)
        avg, slg = ratio(hits, ab), ratio(tb, ab)
        return {"avg": avg, "obp": obp, "slg": slg,
                "ops": obp + slg if obp is not None and slg is not None else None,
                "bbPercent": ratio(bb, pa, 100), "kPercent": ratio(so, pa, 100)}
    if category != "pitching":
        raise LeagueDataError("통계 범주를 확인해 주세요.")
    outs = totals.get("outs")
    bb, hits = totals.get("baseOnBalls"), totals.get("hits")
    return {"era": ratio(totals.get("earnedRuns"), outs, 27),
            "whip": ratio(bb + hits if bb is not None and hits is not None else None, outs, 3),
            "strikeoutsPer9Inn": ratio(totals.get("strikeOuts"), outs, 27),
            "walksPer9Inn": ratio(bb, outs, 27)}


def sum_teams(records, category):
    if not records:
        raise LeagueDataError("선택한 시즌·리그의 팀 합계가 없습니다.")
    keys = ("hits", "atBats", "baseOnBalls", "hitByPitch", "sacFlies", "totalBases", "plateAppearances", "strikeOuts",
            "homeRuns", "doubles", "triples", "intentionalWalks") if category == "hitting" else (
        "earnedRuns", "baseOnBalls", "hits", "strikeOuts", "outs", "homeRuns", "hitBatsmen", "battersFaced", "atBats", "sacFlies")
    normalized = []
    for stats in records:
        row = {key: count(stats.get(key)) for key in keys}
        if category == "pitching":
            ip_outs = innings_to_outs(stats.get("inningsPitched"))
            if ip_outs is not None and row["outs"] is not None and ip_outs != row["outs"]:
                raise LeagueDataError("투구 이닝과 아웃 수가 일치하지 않습니다.")
            row["outs"] = ip_outs if ip_outs is not None else row["outs"]
            if stats.get("inningsPitched") is not None and ip_outs is None:
                raise LeagueDataError("투구 이닝 표기를 검증할 수 없습니다.")
        elif row["totalBases"] is None:
            components = [count(stats.get(key)) for key in ("hits", "doubles", "triples", "homeRuns")]
            if all(value is not None for value in components):
                h, doubles, triples, hr = components
                if h >= doubles + triples + hr:
                    row["totalBases"] = h + doubles + 2 * triples + 3 * hr
        normalized.append(row)
    # Any missing component invalidates that total, not just the missing team's row.
    totals = {key: sum(row[key] for row in normalized) if all(row[key] is not None for row in normalized) else None
              for key in keys}
    return totals, rates_from_totals(totals, category)


def extract_population(payload, teams_payload, season, league_id, category):
    if league_id not in LEAGUES or category not in ("hitting", "pitching"):
        raise LeagueDataError("리그 또는 통계 범주가 올바르지 않습니다.")
    teams = teams_payload.get("teams") if isinstance(teams_payload, dict) else None
    if not isinstance(teams, list) or not teams:
        raise LeagueDataError("시즌별 팀 소속 정보를 확인할 수 없습니다.")
    membership = {}
    for team in teams:
        if (not isinstance(team, dict) or count(team.get("id")) is None
                or str(team.get("season")) != str(season) or (team.get("sport") or {}).get("id") != 1
                or count((team.get("league") or {}).get("id")) is None or team["id"] in membership):
            raise LeagueDataError("시즌별 팀 소속 응답이 불완전합니다.")
        membership[team["id"]] = team["league"]["id"]
    groups = payload.get("stats") if isinstance(payload, dict) else None
    if not isinstance(groups, list):
        raise LeagueDataError("팀별 통계 응답이 올바르지 않습니다.")
    matching = [group for group in groups if isinstance(group, dict)
                and (group.get("group") or {}).get("displayName") == category
                and (group.get("type") or {}).get("displayName") == "season"]
    if len(matching) != 1:
        raise LeagueDataError("정규시즌 팀 합계를 구분할 수 없습니다.")
    group = matching[0]
    splits = group.get("splits")
    if not isinstance(splits, list) or group.get("totalSplits") != len(splits):
        raise LeagueDataError("팀별 통계가 일부만 반환되었습니다.")
    records = {}
    for split in splits:
        team_id = (split.get("team") or {}).get("id") if isinstance(split, dict) else None
        if (team_id not in membership or team_id in records or str(split.get("season")) != str(season)
                or split.get("gameType", "R") != "R" or not isinstance(split.get("stat"), dict)):
            raise LeagueDataError("팀 중복·누락 또는 다른 시즌 통계가 포함되어 있습니다.")
        records[team_id] = split["stat"]
    if set(records) != set(membership):
        raise LeagueDataError("팀 합계와 해당 시즌 MLB 팀 목록이 일치하지 않습니다.")
    selected = {team_id: stats for team_id, stats in records.items()
                if league_id == 0 or membership[team_id] == league_id}
    totals, rates = sum_teams(list(selected.values()), category)
    return {"season": int(season), "league_id": league_id, "category": category, "game_type": "R",
            "team_ids": sorted(selected), "team_count": len(selected), "totals": totals, "rates": rates,
            "innings_pitched": outs_to_innings(totals["outs"]) if category == "pitching" and totals.get("outs") is not None else None,
            "method": "합계의 비율 (선수·팀 비율의 단순 평균 아님)",
            "population": "해당 시즌 소속팀의 전체 정규시즌 기록; 인터리그 포함; 선수 기록은 시즌 전체 합계",
            "limitations": "리그·구장·상대 보정, 통계적 유의성 검정, 출장량 조정 순위가 아님"}


def get_json(path, params):
    response = requests.get(f"{BASE}/{path}", params=params, timeout=(5, 25))
    response.raise_for_status()
    return response.json(), response.url


@st.cache_data(ttl=900, show_spinner=False)
def season_membership(season):
    return get_json("teams", {"sportId": 1, "season": season})


@st.cache_data(ttl=900, show_spinner=False)
def team_totals(season, category):
    payload, source = get_json("teams/stats", {"stats": "season", "group": category,
        "season": season, "sportIds": 1, "gameType": "R", "limit": 1000})
    return payload, source, datetime.now(timezone.utc).isoformat(timespec="seconds")


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('league_average')
def fetch_league_average(season, league_id=0, category="hitting"):
    if league_id not in LEAGUES or category not in ("hitting", "pitching"):
        raise LeagueDataError("리그 또는 통계 범주가 올바르지 않습니다.")
    payload, source, at = team_totals(season, category)
    membership, membership_source = season_membership(season)
    result = extract_population(payload, membership, season, league_id, category)
    result.update(source=source, membership_source=membership_source, retrieved_at=at)
    return result


def player_rates(stats, category):
    stats = stats or {}
    if stats.get("_group", category) != category:
        raise LeagueDataError("타격·투구 기록을 섞어 비교할 수 없습니다.")
    if category == "pitching":
        source = pitching_stats(stats)
        return {key: number(source.get(key)) for key in PITCH_KEYS}
    result = {key: number(stats.get(key)) for key in HIT_KEYS}
    result["bbPercent"] = ratio(number(stats.get("baseOnBalls")), number(stats.get("plateAppearances")), 100)
    result["kPercent"] = ratio(number(stats.get("strikeOuts")), number(stats.get("plateAppearances")), 100)
    return result


def differences(stats, aggregate, category):
    if aggregate["category"] != category:
        raise LeagueDataError("타격·투구 기록을 섞어 비교할 수 없습니다.")
    rates = player_rates(stats, category)
    return {key: round(value - aggregate["rates"][key], 6)
            for key, value in rates.items() if value is not None and aggregate["rates"].get(key) is not None}
