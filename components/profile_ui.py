"""Verified profile fields and a browser-side headshot fallback."""
from utils.i18n import st
from html import escape
from io import BytesIO

import requests
from PIL import Image
from services.player_detection import fetch_current_team_details


def profile_fields(player, profile):
    profile = profile if isinstance(profile, dict) else {}
    def field(key):
        value = profile.get(key)
        return value if isinstance(value, dict) else {}
    side_names = {"L": "좌", "R": "우", "S": "양"}
    return {
        "선수 이름": profile.get("fullName") or player["fullName"], "MLB ID": str(player["id"]),
        "현재 소속팀 (프로필 조회 기준)": field("currentTeam").get("name") or "미확인",
        "주 포지션 (현재 프로필)": field("primaryPosition").get("name") or field("primaryPosition").get("abbreviation") or "미확인",
        "MLB 데뷔": profile.get("mlbDebutDate") or "미확인",
        "활동 상태 (프로필)": "활동" if profile.get("active") is True else "비활동" if profile.get("active") is False else "미확인",
        "타격 손": side_names.get(field("batSide").get("code"), "미확인"),
        "투구 손": side_names.get(field("pitchHand").get("code"), "미확인"),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_headshot(player_id):
    try:
        response = requests.get(
            f"https://img.mlbstatic.com/mlb-photos/image/upload/w_180,q_auto:best/v1/people/{int(player_id)}/headshot/67/current",
            params={}, timeout=(3, 8))
        response.raise_for_status()
        content = response.content
        with Image.open(BytesIO(content)) as picture:
            picture.verify()
        return content
    except (requests.RequestException, OSError, ValueError, TypeError):
        return None


def render_profile(player, profile, season=None, favorite_action=None, favorite=False, key="player_profile"):
    fields = profile_fields(player, profile)
    with st.container(border=True, key=key):
        photo, details = st.columns([1, 5], vertical_alignment="center")
        with photo:
            headshot = fetch_headshot(player["id"])
            if headshot:
                st.image(headshot, width=100)
            else:
                st.markdown("⚾ **사진 없음**")
        with details:
            st.caption("선수 프로필")
            name, star = st.columns([7, 1])
            name.markdown(f'<div class="pro-profile-name">{escape(str(fields["선수 이름"]))}</div>', unsafe_allow_html=True)
            if favorite_action:
                star.button("★" if favorite else "☆", key="dashboard_star",
                            help="즐겨찾기에서 제거" if favorite else "즐겨찾기에 추가",
                            on_click=favorite_action, args=(player,))
            team = (profile or {}).get("currentTeam") or {}
            if team.get("id") and not team.get("abbreviation"):
                try:
                    team = fetch_current_team_details(team["id"])
                except (requests.RequestException, ValueError, TypeError, AttributeError):
                    pass
            abbreviation = team.get("abbreviation") or "약칭 미제공"
            st.write(f"현재 소속팀 (프로필 조회 기준): {fields['현재 소속팀 (프로필 조회 기준)']} · {abbreviation}")
            st.caption(f"주 포지션 (현재 프로필): {fields['주 포지션 (현재 프로필)']} · MLB ID {player['id']} · {fields['활동 상태 (프로필)']}")
            st.caption(f"MLB 데뷔: {fields['MLB 데뷔']} · 타격 손: {fields['타격 손']} · 투구 손: {fields['투구 손']}")
            memberships = player.get("memberships", []) if player.get("season") == season else []
            if memberships:
                st.caption(f"{season} 시즌 로스터 소속: " + " / ".join(dict.fromkeys(m["team"] for m in memberships)))
            elif season:
                st.caption(f"{season} 시즌 소속: 이 프로필에서 미확인")
        st.caption("현재 팀·포지션은 과거 시즌 소속을 뜻하지 않습니다. 비활동 선수는 마지막 등록 팀일 수 있습니다.")
