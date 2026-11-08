"""Season-specific MLB roster search; currentTeam is deliberately never used."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import unicodedata

import requests
from services.cache_manager import persistent, observe
import streamlit as st

BASE = "https://statsapi.mlb.com/api/v1"


class SearchDataError(ValueError):
    """Unexpected team or roster response."""


def get_json(path, params):
    response = requests.get(f"{BASE}/{path}", params=params, timeout=(5, 20))
    response.raise_for_status()
    return response.json()


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('teams')
def fetch_teams(season):
    payload = get_json("teams", {"sportId": 1, "season": season})
    if not isinstance(payload, dict) or not isinstance(payload.get("teams"), list):
        raise SearchDataError("팀 목록 응답 형식 오류")
    teams = {}
    for team in payload["teams"]:
        if not isinstance(team, dict) or not isinstance(team.get("id"), int) or not team.get("name"):
            raise SearchDataError("팀 정보 형식 오류")
        if (team.get("sport") or {}).get("id", 1) == 1:
            teams[team["id"]] = {"id": team["id"], "name": team["name"]}
    return sorted(teams.values(), key=lambda team: team["name"].casefold())


def normalize_roster(payload, team, season):
    if not isinstance(payload, dict) or not isinstance(payload.get("roster"), list):
        raise SearchDataError("로스터 응답 형식 오류")
    players = []
    for entry in payload["roster"]:
        person = entry.get("person") if isinstance(entry, dict) else None
        if not isinstance(person, dict) or not isinstance(person.get("id"), int) or not person.get("fullName"):
            raise SearchDataError("로스터 선수 정보 형식 오류")
        position = (entry.get("position") or {}).get("abbreviation") or "미상"
        players.append({"id": person["id"], "fullName": person["fullName"],
                        "birthDate": person.get("birthDate", "미상"), "season": season,
                        "memberships": [{"teamId": team["id"], "team": team["name"],
                                         "position": position}]})
    return merge_players(players)


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('roster')
def fetch_roster(team_id, season, team_name):
    payload = get_json(f"teams/{team_id}/roster",
                       {"rosterType": "fullSeason", "season": season, "hydrate": "person"})
    return normalize_roster(payload, {"id": team_id, "name": team_name}, season)


def merge_players(players):
    result = {}
    for person in players:
        if person["id"] not in result:
            result[person["id"]] = dict(person, memberships=[])
        for membership in person["memberships"]:
            if membership not in result[person["id"]]["memberships"]:
                result[person["id"]]["memberships"].append(dict(membership))
    for person in result.values():
        person["memberships"].sort(key=lambda member: (member["team"].casefold(), member["position"]))
    return sorted(result.values(), key=lambda person: (person["fullName"].casefold(), person["id"]))


@st.cache_data(ttl=900, show_spinner=False)
def fetch_season_players(season):
    """Union full-season rosters, retaining all team memberships for traded players."""
    teams = fetch_teams(season)
    players, failures = [], []
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = {executor.submit(fetch_roster, team["id"], season, team["name"]): team for team in teams}
        for job in as_completed(jobs):
            try:
                players.extend(job.result())
            except (requests.RequestException, ValueError, TypeError, AttributeError):
                failures.append(jobs[job]["name"])
    return merge_players(players), sorted(failures)


def folded(text):
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


def position_matches(actual, selected):
    if selected == "전체 포지션":
        return True
    if selected == "OF":
        return actual in ("OF", "LF", "CF", "RF")
    if selected in ("P", "DH") and actual in ("TWP", "Y"):
        return True
    return actual == selected


def filter_players(players, team_id=None, position="전체 포지션"):
    result = []
    for person in players:
        memberships = [member for member in person["memberships"]
                       if (team_id is None or member["teamId"] == team_id)
                       and position_matches(member["position"], position)]
        if memberships:
            result.append(dict(person, memberships=memberships))
    return result


def suggestion_label(person):
    memberships = " / ".join(f"{member['team']} · {member['position']}" for member in person["memberships"])
    return (f"{person['fullName']} — {memberships} — {person['season']}"
            f" · 생년월일 {person.get('birthDate', '미상')} · ID {person['id']}")


def autocomplete(players, query, limit=10):
    needle = folded(query.strip())
    if not needle:
        return []
    matches = [person for person in players if needle in folded(person["fullName"])]
    def rank(person):
        name = folded(person["fullName"])
        return (0 if name == needle else 1 if name.startswith(needle) else
                2 if any(word.startswith(needle) for word in name.split()) else 3,
                name, person["id"])
    return [(suggestion_label(person), person["id"]) for person in sorted(matches, key=rank)[:min(limit, 10)]]


def clear_autocomplete(key):
    state = st.session_state.pop(f"{key}_auto", None)
    if isinstance(state, dict) and state.get("key_react"):
        st.session_state.pop(state["key_react"], None)
    st.session_state.pop(f"{key}_selected", None)
    st.session_state.pop(f"{key}_chosen", None)


def reset_filters(key):
    clear_autocomplete(key)
    # Assign widget defaults explicitly so the browser also resets its selection.
    st.session_state[f"{key}_team"] = 0
    st.session_state[f"{key}_position"] = "전체 포지션"
    st.session_state.pop(f"{key}_context", None)
