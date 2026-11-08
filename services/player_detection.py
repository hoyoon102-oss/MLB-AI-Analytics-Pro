"""Data-based role inference; thresholds are transparent UI rules, not official status."""
import requests
from services.cache_manager import persistent, observe
import streamlit as st
from analytics.pitching import innings_to_outs, number


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('profile')
def fetch_profile(player_id):
    response = requests.get(f"https://statsapi.mlb.com/api/v1/people/{player_id}", params={"hydrate": "currentTeam"}, timeout=(5, 20))
    response.raise_for_status()
    payload = response.json()
    people = payload.get("people") if isinstance(payload, dict) else None
    if not isinstance(people, list) or not people or people[0].get("id") != player_id:
        raise ValueError("선수 프로필 응답 오류")
    return people[0]


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('team_profile')
def fetch_current_team_details(team_id):
    """Optional current team metadata; never substitute it for a historical team."""
    response = requests.get(f"https://statsapi.mlb.com/api/v1/teams/{int(team_id)}",
                            params={}, timeout=(3, 8))
    response.raise_for_status()
    payload = response.json()
    teams = payload.get("teams") if isinstance(payload, dict) else None
    if not isinstance(teams, list) or not teams or teams[0].get("id") != team_id:
        raise ValueError("현재 팀 정보 응답 오류")
    return teams[0]


def has_record(stats, category):
    if not stats:
        return False
    keys = ("plateAppearances", "atBats", "gamesPlayed") if category == "hitting" else (
        "outs", "gamesPitched", "gamesPlayed", "battersFaced")
    counts = [number(stats.get(key)) for key in keys if number(stats.get(key)) is not None]
    if category == "pitching":
        outs = innings_to_outs(stats.get("inningsPitched"))
        if outs is not None:
            counts.append(outs)
    if counts:
        return any(value > 0 for value in counts)
    # Some responses omit appearance counts; a published numeric metric is still a record.
    fields = ("avg", "obp", "slg", "ops", "homeRuns", "rbi") if category == "hitting" else (
        "era", "whip", "wins", "strikeOuts", "baseOnBalls")
    return any(number(stats.get(key)) is not None for key in fields)


def detect_role(records, profile=None, errors=None):
    profile, errors = profile or {}, errors or {}
    available = [category for category in ("hitting", "pitching") if has_record(records.get(category), category)]
    position = profile.get("primaryPosition") or {}
    official = (position.get("code") == "Y" or position.get("abbreviation") == "TWP"
                or profile.get("isTwoWayPlayer") is True or profile.get("twoWayPlayer") is True)
    hitting, pitching = records.get("hitting") or {}, records.get("pitching") or {}
    pa = number(hitting.get("plateAppearances"))
    if pa is None:
        pa = number(hitting.get("atBats")) or 0
    outs = innings_to_outs(pitching.get("inningsPitched"))
    if outs is None:
        outs = number(pitching.get("outs")) or 0
    meaningful = ("hitting" in available and "pitching" in available and pa >= 100 and outs >= 60)
    if official or meaningful:
        options = ["hitting", "pitching"]
        preferred = available[0] if available else "hitting"
        reason = "MLB 프로필의 공식 겸업 표기 (과거 시즌 지정 여부와 별개)" if official else "해당 시즌 100타석 이상·20이닝 이상 기록"
    elif len(available) == 1:
        options, preferred = available, available[0]
        reason = "해당 시즌 확인된 기록"
    elif len(available) == 2:
        # Ordinary historical pitchers may bat; occasional position-player pitching is not a two-way role.
        preferred = "pitching" if outs / 60 > pa / 100 else "hitting"
        options = [preferred]
        reason = "해당 시즌의 상대적 출전량 (타석·투구 아웃 수)"
    else:
        options, preferred, reason = [], None, "해당 시즌 기록 없음" if not errors else "일부 기록 조회 실패로 판별 불가"
    if errors and options:
        reason += " · 조회 성공한 기록만 임시 표시 (역할 확정 아님)"
    return {"uncertain": bool(errors), "available": available, "options": options, "preferred": preferred,
            "two_way": bool(official or meaningful), "official": official, "reason": reason}
