"""Normalize actual MLB award responses; never infer awards from performance."""
from collections import Counter
from datetime import datetime, timezone

import plotly.graph_objects as go
import requests
from services.cache_manager import persistent, observe
from utils.i18n import st
from components.ui_components import style_chart

MAJOR = {
    "ALMVP": "MVP", "NLMVP": "MVP", "ALCY": "사이영상", "NLCY": "사이영상",
    "ALROY": "신인왕", "NLROY": "신인왕", "ALGG": "골드글러브", "NLGG": "골드글러브",
    "ALSS": "실버슬러거", "NLSS": "실버슬러거", "ALAS": "올스타 선정 시즌", "NLAS": "올스타 선정 시즌",
    "MLBAFIRST": "All-MLB 선정 항목", "MLBSECOND": "All-MLB 선정 항목",
    "ALHAA": "행크 애런상", "NLHAA": "행크 애런상",
}
POSITION_AWARDS = {"ALGG", "NLGG", "ALSS", "NLSS", "MLBAFIRST", "MLBSECOND"}
PRIMARY_CATEGORIES = tuple(dict.fromkeys(MAJOR.values()))


def normalize_awards(payload, player_id):
    if not isinstance(payload, dict) or not isinstance(payload.get("awards"), list):
        raise ValueError("수상 응답 형식 오류")
    unique, invalid, excluded = {}, 0, 0
    for raw in payload["awards"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            invalid += 1
            continue
        person = raw.get("player") or {}
        if not isinstance(person, dict) or person.get("id", player_id) != player_id:
            invalid += 1
            continue
        name = raw["name"].strip()
        code = str(raw.get("id") or "").strip()
        if code == "WSCHAMP" or "world series championship" in name.casefold():
            excluded += 1
            continue
        value = str(raw.get("season") or "")
        season = int(value) if value.isdigit() and len(value) == 4 else None
        announced = str(raw.get("date") or "")
        position = person.get("primaryPosition") or {}
        position = position.get("abbreviation", "") if isinstance(position, dict) else ""
        if position in ("SP", "RP", "LHS", "RHS", "LHR", "RHR"):
            position = "P"
        team = raw.get("team") or {}
        league = raw.get("league") or {}
        if not isinstance(team, dict) or not isinstance(league, dict):
            invalid += 1
            continue
        league_label = league.get("abbreviation") or league.get("name")
        if not league_label and (code in MAJOR or code in {"ALPOW", "NLPOW", "ALPOM", "NLPOM", "ALPITOM", "NLPITOM", "ALROM", "NLROM", "ALCSMVP", "NLCSMVP"}):
            league_label = code[:2] if code[:2] in ("AL", "NL") else None
        category = MAJOR.get(code)
        if category:
            scope = "MLB 주요 수상"
        elif code in {"ALPOW", "NLPOW", "ALPOM", "NLPOM", "ALPITOM", "NLPITOM", "ALROM", "NLROM"}:
            category, scope = "주간·월간상", "MLB 주간·월간"
        elif code in {"ALCSMVP", "NLCSMVP", "WSMVP"}:
            category, scope = "포스트시즌 개인상", "MLB 포스트시즌"
        elif code.startswith("WBC"):
            category, scope = "국제대회", "국제대회 기록"
        else:
            category, scope = "기타 공식 API 기록", "기타 (마이너·외부상·추가 MLB 기록 포함)"
        award = {"id": code or None, "name": name, "season": season, "date": announced or None,
                 "league": league_label, "team": team.get("name") or team.get("teamName"),
                 "position": position or None, "category": category, "scope": scope}
        # Annual awards ignore publication-date/team duplicates. Repeated weekly awards retain dates.
        annual = code in MAJOR and season is not None
        identity = code or name.casefold()
        key = (identity, season, None if annual else announced, None if annual else league_label,
               position if code in POSITION_AWARDS else None)
        if key not in unique:
            unique[key] = award
        else:
            # Enrich an identical event without adding a second count.
            for field in ("team", "league", "date", "position"):
                conflict = f"_{field}_conflict"
                if field in ("team", "league") and unique[key].get(field) and award.get(field) and unique[key][field] != award[field]:
                    unique[key][field] = None
                    unique[key][conflict] = True
                elif not unique[key].get(field) and award.get(field) and not unique[key].get(conflict):
                    unique[key][field] = award[field]
    return {"records": list(unique.values()), "invalid": invalid, "excluded": excluded,
            "received": len(payload["awards"])}


@observe
@st.cache_data(ttl=60, show_spinner=False)
@persistent('awards')
def fetch_awards(player_id):
    response = requests.get(f"https://statsapi.mlb.com/api/v1/people/{player_id}/awards", params={}, timeout=(5, 20))
    response.raise_for_status()
    result = normalize_awards(response.json(), player_id)
    result["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return result


def category_counts(records):
    counts = Counter()
    all_star_seasons = set()
    for award in records:
        if award["id"] in MAJOR:
            if award["category"] == "올스타 선정 시즌":
                if award["season"] is not None:
                    all_star_seasons.add(award["season"])
            else:
                counts[award["category"]] += 1
    if all_star_seasons:
        counts["올스타 선정 시즌"] = len(all_star_seasons)
    return dict(counts)


def season_awards(records, season):
    return [award for award in records if award["season"] == season]


def award_rows(records):
    return [{"시즌": str(a["season"]) if a["season"] else "미확인", "공식 수상명": a["name"],
             "분류": a["category"], "범위": a["scope"], "리그": a["league"] or "미확인",
             "당시 팀 (수상 API)": a["team"] or "미확인", "포지션": a["position"] or "미확인",
             "발표일": a["date"] or "미확인", "수상 ID": a["id"] or "미제공"} for a in records]


def render_awards(player, season, force_open=False):
    st.subheader("🏆 수상·업적")
    if not force_open and not st.toggle("수상·업적 열기", key="awards_open", persist_state="session"):
        return
    try:
        result = fetch_awards(player["id"])
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        st.warning("수상 기록을 조회할 수 없습니다. 수상 0회라는 뜻이 아닙니다. 잠시 후 기록 새로고침으로 다시 시도해 주세요.")
        return
    records = result["records"]
    st.caption(f"통산 수상 · MLB ID {player['id']} · 조회 시각 {result['fetched_at']} · 1시간 저장")
    st.caption("MLB API에 반환된 확인 기록만 집계합니다. 누락된 역사 기록이 있을 수 있어 실제 통산 전체를 보장하지 않습니다.")
    if result["invalid"]:
        st.warning(f"형식이 불완전한 {result['invalid']}개 항목을 제외했습니다. 아래 집계는 확인 가능한 기록에 한합니다.")
    if result["excluded"]:
        st.caption("월드시리즈 우승 항목은 팀·포스트시즌 별도 검증 없이 개인 수상으로 집계하지 않습니다.")
    if not records:
        st.info("표시할 개인 수상 기록이 반환되지 않았습니다. 실제로 수상 경력이 없다는 뜻은 아닙니다.")
        return
    st.markdown("**통산 주요 수상 요약 (현재 선택 시즌과 독립)**")
    counts = category_counts(records)
    items = list(counts.items())
    for offset in range(0, len(items), 4):
        for column, (name, count) in zip(st.columns(4), items[offset:offset + 4]):
            with column.container(key=f"award_kpi_{offset}_{name}"):
                st.metric(name, count, border=True)
    if not counts:
        st.caption("주요 수상 ID에 해당하는 기록은 없지만, 아래에 추가 기록을 표시합니다.")
    st.caption("올스타는 중복 없는 선정 시즌 수, All-MLB는 팀·포지션별 확인 항목 수입니다. 주간·월간·포스트시즌 MVP는 정규시즌 MVP에 합산하지 않습니다.")
    view = st.radio("수상 조회 범위", ["통산 수상", "선택 시즌 수상"], horizontal=True,
                    key=f"awards_view_{player['id']}", persist_state="session")
    visible = records if view == "통산 수상" else season_awards(records, season)
    order = st.selectbox("연도 정렬", ["최신 연도 먼저", "오래된 연도 먼저"], key="awards_sort", persist_state="session")
    with st.expander("수상 필터 · 연도와 분류"):
        years_available = sorted({a["season"] for a in visible if a["season"] is not None}, reverse=True)
        categories_available = sorted({a["category"] for a in visible})
        selected_year = st.selectbox("수상 연도", [None, *years_available], format_func=lambda y: "전체 연도" if y is None else str(y), key=f"award_year_{player['id']}_{view}_{season}")
        selected_category = st.selectbox("수상 분류", ["전체 분류", *categories_available], key=f"award_category_{player['id']}_{view}")
    visible = [a for a in visible if (selected_year is None or a["season"] == selected_year)
               and (selected_category == "전체 분류" or a["category"] == selected_category)]
    if view == "선택 시즌 수상":
        st.caption(f"{season} 시즌 표기가 있는 수상만 표시합니다. 시즌 종료 후 또는 다음 해에 발표된 상도 시즌 필드로 연결합니다.")
    if not visible:
        st.info(f"{season} 시즌에 연결된 수상 기록이 반환되지 않았습니다. 미발표·미수록일 수 있습니다.")
        return
    groups = Counter((a["id"], a["name"]) for a in visible)
    with st.expander("수상별 횟수 · 공식 명칭과 ID"):
        st.dataframe([{"수상 ID": code or "미제공", "공식 수상명": name, "확인 횟수": count}
                      for (code, name), count in sorted(groups.items(), key=lambda item: (-item[1], item[0][1]))], hide_index=True)
    st.markdown("**연도별 수상 타임라인**")
    years = sorted({a["season"] for a in visible if a["season"] is not None}, reverse=order == "최신 연도 먼저")
    for year in [*years, *([None] if any(a["season"] is None for a in visible) else [])]:
        with st.container(border=True):
            st.markdown(f"**● {year if year else '시즌 미확인'}**")
            for award in sorted([a for a in visible if a["season"] == year], key=lambda a: (a["date"] or "", a["name"])):
                st.write(f"🏅 {award['name']} · {award['category']}")
                st.caption(f"{award['league'] or '리그 미확인'} · {award['team'] or '당시 팀 미확인'} · {award['position'] or '포지션 미확인'} · 발표 {award['date'] or '미확인'} · {award['scope']}")
    with st.expander("전체 수상 이력 표" if view == "통산 수상" else "선택 시즌 수상 이력 표"):
        st.dataframe(award_rows(visible), hide_index=True)


def render_award_comparison(players):
    if not st.checkbox("통산 수상 비교 보기 (시즌 성적과 별도)", key="compare_awards", persist_state="session"):
        return
    st.subheader("🏆 통산 수상 비교")
    results = []
    for player in players:
        try:
            result = fetch_awards(player["id"])
            results.append(result)
            st.caption(f"{player['fullName']} · 조회 {result['fetched_at']}")
            if result["invalid"]:
                st.warning(f"{player['fullName']}: 불완전한 항목을 제외한 부분 집계입니다.")
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            results.append(None)
            st.warning(f"{player['fullName']}: 수상 조회 실패. 0회로 처리하지 않습니다.")
    rows = []
    figure = go.Figure()
    for category in PRIMARY_CATEGORIES:
        row = {"수상 분류": category}
        for player, result in zip(players, results):
            value = category_counts(result["records"]).get(category, 0) if result and result["records"] else None
            row[f"{player['fullName']} (ID {player['id']})"] = str(value) if value is not None else "— (반환 기록 없음/조회 실패)"
        rows.append(row)
    st.table(rows)
    for player, result in zip(players, results):
        if result and result["records"]:
            counts = category_counts(result["records"])
            figure.add_trace(go.Bar(name=f"{player['fullName']} (ID {player['id']})",
                                   x=list(PRIMARY_CATEGORIES), y=[counts.get(c, 0) for c in PRIMARY_CATEGORIES]))
    if figure.data:
        figure.update_layout(barmode="group", yaxis_title="API 확인 기록 수", xaxis_title="통산 주요 수상 분류")
        st.plotly_chart(style_chart(figure, height=420), width="stretch", key="awards_comparison_chart")
    st.caption("0은 조회된 이력에서 해당 상을 확인하지 못했다는 뜻이며 실제 통산 무수상을 확정하지 않습니다. —는 전체 기록 없음 또는 조회 실패입니다. 월드시리즈 우승은 제외합니다. 수상 수만으로 선수의 우열을 판정하지 않습니다.")
