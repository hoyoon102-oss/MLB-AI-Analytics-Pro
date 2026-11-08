"""MLB regular-season requests and response validation; preserves API semantics."""
from datetime import datetime, timezone
from services.cache_manager import persistent, observe
import requests
from utils.i18n import st
from analytics.pitching import pitching_stats
API_BASE = "https://statsapi.mlb.com/api/v1"
class DataError(Exception):
    """The API returned an unexpected or ambiguous response."""


def extract_stats(payload, season, category="hitting", player_id=None):
    """Select MLB regular-season totals without inventing or summing rates."""
    if not isinstance(payload, dict) or not isinstance(payload.get("stats"), list):
        raise DataError("MLB API 응답 형식이 올바르지 않습니다.")
    validate_category(category)
    candidates = []
    for group in payload["stats"]:
        if not isinstance(group, dict):
            raise DataError("MLB API 통계 형식을 확인할 수 없습니다.")
        if group.get("group", {}).get("displayName") != category:
            continue
        splits = group.get("splits", [])
        if not isinstance(splits, list):
            raise DataError("MLB API 시즌 기록 형식이 올바르지 않습니다.")
        for split in splits:
            if not isinstance(split, dict):
                raise DataError("MLB API 기록 형식이 올바르지 않습니다.")
            if player_id is not None and (split.get('player') or {}).get('id', player_id) != player_id:
                raise DataError('Player ID mismatch')
            if (str(split.get("season")) == str(season)
                    and split.get("gameType", "R") == "R"
                    and split.get("sport", {}).get("id", 1) == 1):
                candidates.append(split)
    if not candidates:
        return None
    # A traded player may have team splits plus one combined total.
    totals = [split for split in candidates if not split.get("team")]
    if len(totals) == 1:
        selected = totals[0]
    elif len(candidates) == 1:
        selected = candidates[0]
    else:
        raise DataError("시즌 합계 기록을 확실히 구분할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    stats = selected.get("stat")
    if not isinstance(stats, dict):
        raise DataError("MLB API에 선수 기록이 올바르게 포함되어 있지 않습니다.")
    if not stats:
        return None
    return pitching_stats(stats) if category == "pitching" else dict(stats, _group="hitting")


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('player_stats')
def fetch_stats(player_id, season, category="hitting"):
    """Cache successful API requests for 15 minutes; always use regular season."""
    validate_category(category)
    response = requests.get(
        f"{API_BASE}/people/{player_id}/stats",
        params={"stats": "season", "group": category, "season": season,
                "gameType": "R", "sportIds": 1},
        timeout=(5, 20),
    )
    response.raise_for_status()
    stats = extract_stats(response.json(), season, category, player_id)
    return stats, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def api_json(path, params):
    response = requests.get(f"{API_BASE}/{path}", params=params, timeout=(5, 20))
    response.raise_for_status()
    return response.json()


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('search')
def search_players(query):
    query = query.strip()
    if not query:
        return []
    payload = api_json("people/search", {"names": query, "sportIds": 1, "hydrate": "currentTeam"})
    if not isinstance(payload, dict) or not isinstance(payload.get("people"), list):
        raise DataError("선수 검색 응답 형식이 올바르지 않습니다.")
    players = {}
    for person in payload["people"]:
        if (not isinstance(person, dict) or not isinstance(person.get("id"), int)
                or not isinstance(person.get("fullName"), str)):
            raise DataError("선수 정보를 읽을 수 없습니다.")
        players[person["id"]] = person
    return sorted(players.values(), key=lambda person: (person["fullName"], person["id"]))


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('history')
def fetch_history(player_id, start, end, category="hitting"):
    validate_category(category)
    payload = api_json(f"people/{player_id}/stats", {"stats": "yearByYear", "group": category,
                       "gameType": "R", "sportIds": 1})
    if not isinstance(payload, dict) or not isinstance(payload.get("stats"), list):
        raise DataError("시즌별 응답 형식이 올바르지 않습니다.")
    records, problems = {}, []
    for year in range(start, end + 1):
        try:
            records[year] = extract_stats(payload, year, category, player_id)
        except DataError:
            records[year] = None
            problems.append(year)
    return records, problems, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def validate_category(category):
    if category not in ("hitting", "pitching"):
        raise DataError("타자 또는 투수 유형을 선택해 주세요.")


def validate_comparison(records, category):
    validate_category(category)
    if any(record and record.get("_group", category) != category for record in records):
        raise DataError("타격 기록과 투구 기록을 서로 비교할 수 없습니다.")


API_ERRORS = (requests.RequestException, ValueError, DataError, TypeError, AttributeError)
