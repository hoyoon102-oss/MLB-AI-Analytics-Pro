"""Resolve MLB seasons from schedule metadata and games that actually began."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

BASE = "https://statsapi.mlb.com/api/v1"


def current_date():
    return datetime.now(ZoneInfo("America/Toronto")).date()


def get_json(path, params):
    response = requests.get(f"{BASE}/{path}", params=params, timeout=(5, 20))
    response.raise_for_status()
    return response.json()


def choose_season(rows, today, has_data):
    eligible = []
    for row in rows:
        try:
            year = int(row["seasonId"])
            start = date.fromisoformat(row["regularSeasonStartDate"])
            end = date.fromisoformat(row["regularSeasonEndDate"])
            if start <= today and year <= today.year:
                eligible.append((year, start, end))
        except (KeyError, ValueError, TypeError):
            continue
    for year, start, end in sorted(eligible, reverse=True)[:3]:
        if has_data(year, min(today, end)):
            return year
    raise ValueError("정규시즌 경기 기록을 확인할 수 없습니다.")


def has_regular_data(year, through):
    payload = get_json("schedule", {"sportId": 1, "gameTypes": "R",
        "startDate": f"{year}-01-01", "endDate": through.isoformat(),
        "fields": "dates,games,status,abstractGameState"})
    if not isinstance(payload, dict) or not isinstance(payload.get("dates"), list):
        raise ValueError("경기 일정 응답 오류")
    return any(game.get("status", {}).get("abstractGameState") in ("Final", "Live")
               for day in payload["dates"] for game in day.get("games", []))


@st.cache_data(ttl=3600, show_spinner=False)
def resolve_seasons(today_iso):
    today = date.fromisoformat(today_iso)
    warning = None
    try:
        payload = get_json("seasons/all", {"sportId": 1})
        rows = payload["seasons"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("시즌 목록 없음")
        latest = choose_season(rows, today, has_regular_data)
        years = sorted({int(row["seasonId"]) for row in rows
                        if str(row.get("seasonId", "")).isdigit() and int(row["seasonId"]) <= latest})
        return {"latest": latest, "years": years, "warning": warning}
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        # A previous calendar year cannot be an upcoming season. Mark it unverified.
        latest = today.year - 1
        return {"latest": latest, "years": list(range(1876, latest + 1)),
                "warning": "MLB 최신 시즌을 확인하지 못해 전년도 시즌을 임시로 선택했습니다. 시즌을 직접 확인·선택하거나 기록 새로고침으로 재시도해 주세요."}
