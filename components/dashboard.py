"""Custom navigation and player screens composed from services and components."""
from services.player_stats import (API_ERRORS, fetch_stats, search_players, fetch_history,
                                   validate_comparison)
from analytics.standard import METRICS, RATE_KEYS, numeric
from components.stat_charts import history_figure, comparison_figure


from analytics.pitching import (PITCHING_METRICS, PITCH_HISTORY_KEYS, PITCH_COMPARE_KEYS,
                      chart_value)
import requests
from utils.i18n import st, tr, t, language_selector
from streamlit_searchbox import st_searchbox
from utils.favorites import load_favorites, toggle_favorite
from components.awards import fetch_awards, render_awards, render_award_comparison
from components.profile_ui import render_profile, fetch_headshot
from services.season_selection import current_date, resolve_seasons
from services.player_detection import fetch_profile, fetch_current_team_details, detect_role, has_record
import components.ai_ui as ai_ui
import components.ui_components as ui
import components.league_ui as league_ui
import components.advanced_stats_ui as advanced_ui
import components.statcast_ui as statcast_ui
import components.rankings_ui as rankings_ui
import components.career_ui as career_ui
import components.leaderboard_ui as leaderboard_ui
from services.league_stats import fetch_league_average, season_membership, team_totals
from services.player_search import (fetch_teams, fetch_roster, fetch_season_players, filter_players,
                           autocomplete, suggestion_label, reset_filters, clear_autocomplete)


def player_label(person):
    position = (person.get("primaryPosition") or {}).get("abbreviation", "미상")
    return (f"{person['fullName']} · 생년월일 {person.get('birthDate', '미상')}"
            f" · {position} · MLB ID {person['id']}")


def show_api_error(context, error):
    if isinstance(error, requests.Timeout):
        st.error(f"{context}: MLB API 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.")
    elif isinstance(error, requests.RequestException):
        st.error(f"{context}: MLB API에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.")
    else:
        st.error(f"{context}: MLB API 응답을 읽을 수 없습니다. 잠시 후 다시 시도해 주세요.")


def favorite_mark(player_id):
    return "★ " if any(p["id"] == player_id for p in st.session_state.get("_favorites", [])) else "☆ "


def change_favorite(person):
    try:
        players, added = toggle_favorite(person)
        st.session_state["_favorites"] = players
        st.session_state["_favorite_notice"] = "즐겨찾기에 추가했습니다." if added else "즐겨찾기에서 제거했습니다. 현재 선수 기록은 유지됩니다."
    except (OSError, ValueError):
        st.session_state["_favorite_error"] = "즐겨찾기를 저장하지 못했습니다. 폴더 접근 권한을 확인해 주세요. 현재 선수 선택은 유지됩니다."


def selected_player_header(key, person):
    if key == "dashboard":
        return  # The profile card owns the dashboard favorite control.
    label, button = st.columns([8, 1])
    label.markdown(f"**{person['fullName']}** · MLB ID {person['id']}")
    saved = favorite_mark(person["id"]).strip() == "★"
    button.button("★" if saved else "☆", key=f"{key}_star",
                  help="즐겨찾기에서 제거" if saved else "즐겨찾기에 추가",
                  on_click=change_favorite, args=(person,))


def favorite_picker(key, season):
    people = st.session_state.get("_favorites", [])
    chosen = st.session_state.get(f"{key}_chosen")
    if not people:
        st.info("저장한 즐겨찾기가 없습니다. 이름 검색에서 선수를 선택하고 ☆를 눌러 추가해 주세요.")
        return chosen
    by_id = {person["id"]: person for person in people}
    if st.session_state.get(f"{key}_favorite_choice") not in by_id:
        st.session_state[f"{key}_favorite_choice"] = None
    selected = st.selectbox("즐겨찾기 선수", list(by_id), index=None,
        format_func=lambda value: "★ " + player_label(by_id[value]),
        key=f"{key}_favorite_choice", placeholder="즐겨찾기에서 선수를 선택하세요", persist_state="session")
    if selected is not None:
        # Keep only durable identity; always resolve affiliations for the selected season.
        chosen = dict(by_id[selected])
    if chosen:
        try:
            players, failures = fetch_season_players(season)
            match = next((player for player in players if player["id"] == chosen["id"]), None)
            if match:
                st.caption(suggestion_label(match))
            else:
                st.caption(f"{season}년 소속팀·포지션을 로스터에서 확인할 수 없습니다. 시즌 통계는 별도로 조회합니다.")
            if failures:
                st.warning("일부 팀의 시즌 소속 정보를 확인하지 못했습니다.")
        except API_ERRORS:
            st.caption(f"{season}년 소속팀·포지션 조회를 할 수 없습니다. 저장된 이름과 ID로 통계를 조회합니다.")
    return chosen


def player_picker(key, season):
    method_area, scope_area = st.columns(2)
    mode = method_area.radio("선수 선택 방법", ["이름 검색", "즐겨찾기"], horizontal=True,
                    key=f"{key}_mode", persist_state="session")
    filter_area = st.container()
    if mode == "즐겨찾기":
        person = favorite_picker(key, season)
    else:
        scope = scope_area.radio("이름 검색 범위", ["선택 시즌 로스터", "전체 시대 이름 검색"],
                         horizontal=True, key=f"{key}_scope", persist_state="session")
        person = (legacy_player_picker(key) if scope == "전체 시대 이름 검색"
                  else advanced_player_picker(key, season, filter_area))
    if person:
        st.session_state[f"{key}_chosen"] = dict(person)
    if person is None:
        person = st.session_state.get(f"{key}_chosen")
    if person:
        selected_player_header(key, person)
    return person


def legacy_player_picker(key):
    with st.form(f"{key}_form"):
        query = st.text_input("선수 이름 (영문)", placeholder="예: Shohei Ohtani", key=f"{key}_query")
        submitted = st.form_submit_button("선수 검색")
    result_key = f"{key}_results"
    if submitted:
        st.session_state[result_key] = []
        st.session_state.pop(f"{key}_chosen", None)
        st.session_state.pop(f"{key}_result", None)
        if not query.strip():
            st.warning("검색할 선수 이름을 입력해 주세요.")
        else:
            try:
                with st.spinner("선수를 검색하는 중입니다…"):
                    st.session_state[result_key] = search_players(query)
                if not st.session_state[result_key]:
                    st.info("검색 결과가 없습니다. 영문 이름을 확인해 주세요.")
            except API_ERRORS as error:
                show_api_error("선수 검색", error)
    results = st.session_state.get(result_key, [])
    if not results:
        return None
    by_id = {person["id"]: person for person in results}
    selected = st.selectbox("검색 결과 (동명이인은 생년월일과 ID로 구분)", list(by_id),
                            format_func=lambda value: favorite_mark(value) + player_label(by_id[value]), key=f"{key}_result",
                            index=None, placeholder="검색 결과에서 선수를 선택하세요", persist_state="session")
    return by_id.get(selected)


def advanced_player_picker(key, season, filter_area=None):
    with (filter_area if filter_area is not None else st.container()):
        team_column, position_column, reset_column = st.columns([3, 2, 2], vertical_alignment="bottom")
        reset_column.button("검색 필터 초기화", key=f"{key}_reset", on_click=reset_filters, args=(key,))
        try:
            with st.spinner(f"{season}년 팀 목록을 불러오는 중입니다…"):
                teams = fetch_teams(season)
            if not teams:
                st.info("선택한 시즌의 팀 정보가 없습니다.")
                return None
            if len(teams) != 30:
                st.warning(f"이 시즌 API에서 확인된 MLB 팀은 {len(teams)}개입니다.")
            by_team = {team["id"]: team for team in teams}
            if st.session_state.get(f"{key}_team") not in [0, *by_team]:
                st.session_state.pop(f"{key}_team", None)
            team_value = team_column.selectbox("팀 (이름을 입력해 검색)", [0, *by_team],
                format_func=lambda value: "전체 팀 (All Teams)" if value == 0 else by_team[value]["name"],
                filter_mode="contains", key=f"{key}_team", persist_state="session")
            team_id = team_value or None
            with st.spinner(f"{season}년 시즌 로스터를 불러오는 중입니다…"):
                if team_id is None:
                    players, failures = fetch_season_players(season)
                    if failures:
                        st.warning("일부 팀 조회에 실패해 목록이 불완전합니다: " + ", ".join(failures)
                                   + ". 기록 새로고침으로 다시 시도해 주세요.")
                else:
                    players = fetch_roster(team_id, season, by_team[team_id]["name"])
        except API_ERRORS as error:
            show_api_error("팀·시즌 로스터 검색", error)
            return None
        positions = sorted({member["position"] for player in players for member in player["memberships"]})
        if any(position in positions for position in ("LF", "CF", "RF")) and "OF" not in positions:
            positions.append("OF")
            positions.sort()
        options = ["전체 포지션", *positions]
        if st.session_state.get(f"{key}_position", "전체 포지션") not in options:
            st.session_state.pop(f"{key}_position", None)
        position = position_column.selectbox("포지션", options, key=f"{key}_position", persist_state="session")
        filtered = filter_players(players, team_id, position)
        context = (season, team_id, position)
        if st.session_state.get(f"{key}_context") != context:
            previous = st.session_state.get(f"{key}_chosen") if f"{key}_context" not in st.session_state else None
            clear_autocomplete(key)
            if previous:
                st.session_state[f"{key}_chosen"] = previous
            st.session_state[f"{key}_context"] = context
    st.caption(f"{season}년 시즌 로스터 · 필터 결과 {len(filtered)}명 · 최대 10개 이름 추천")
    if not filtered:
        st.info("조건에 맞는 시즌 로스터 선수가 없습니다. 필터를 바꾸거나 기존 이름 검색을 사용해 주세요.")
        return None
    by_id = {person["id"]: person for person in filtered}
    with st.container(key=f"{key}_search_{season}_{team_id or 0}_{options.index(position)}"):
        selected = st_searchbox(lambda query: [(favorite_mark(value) + tr(label), value) for label, value in autocomplete(filtered, query)],
            key=f"{key}_auto", label=tr("선수 이름 자동완성 (영문 일부 입력)"),
            placeholder=tr("예: Sho / Jud · 검색 후 후보를 선택하세요"), debounce=250,
            edit_after_submit="option", default_options=[],
            style_overrides={"searchbox": {"optionEmpty": "hidden"}},
            help=tr("대소문자 구분 없이 검색합니다. ↑↓로 이동하고 Enter로 선택할 수 있습니다."))
    query = st.session_state.get(f"{key}_auto", {}).get("search", "")
    if query.strip() and not autocomplete(filtered, query):
        st.info("일치하는 선수가 없습니다. 이름이나 필터를 바꿔 주세요.")
    with st.expander(f"{season}년 로스터 보기 ({len(filtered)}명)"):
        st.dataframe([{"선수": person["fullName"],
                       "팀": " / ".join(dict.fromkeys(member["team"] for member in person["memberships"])),
                       "포지션": "/".join(sorted({member["position"] for member in person["memberships"]})),
                       "MLB ID": person["id"]} for person in filtered], hide_index=True)
        st.caption("선택 시즌의 fullSeason 등록 자료로, 특정 날짜 소속이나 출전을 보장하지 않습니다. 포지션은 검색 필터이며 분석 범주는 실제 기록으로 자동 판별합니다. 통계는 시즌 전체 합계입니다.")
    if selected not in by_id:
        return None
    person = by_id[selected]
    st.session_state[f"{key}_selected"] = selected
    st.success("선택한 선수: " + suggestion_label(person))
    return person


def show_metrics(stats, category="hitting", league=None):
    metrics = PITCHING_METRICS if category == "pitching" else METRICS
    primary = ("era", "whip", "strikeOuts", "inningsPitched", "wins", "losses") if category == "pitching" else tuple(METRICS.values())
    missing = []
    def cards(items):
        for row_start in range(0, len(items), 3):
            for column, (label, key) in zip(st.columns(3), items[row_start:row_start + 3]):
                value = stats.get(key)
                if value is None or value == "":
                    value = "—"
                    missing.append(label)
                with column.container(key=f"kpi_{category}_{key}"):
                    st.metric(label, str(value), border=True)
                    league_ui.card_context(stats, league, category, key)
    cards([(label, key) for key in primary for label, value in metrics.items() if value == key])
    extra = [(label, key) for label, key in metrics.items() if key not in primary]
    if extra:
        with st.expander("상세 통계 · 추가 투구 지표"):
            cards(extra)
    if category == "hitting":
        with st.expander("상세 통계 · 출전량과 추가 타격 지표"):
            labels = {"gamesPlayed": "경기", "plateAppearances": "타석", "atBats": "타수", "baseOnBalls": "볼넷", "strikeOuts": "삼진", "hits": "안타", "stolenBases": "도루"}
            st.dataframe([{"지표": label, "기록": str(stats[key]) if stats.get(key) is not None else "—"}
                          for key, label in labels.items()], hide_index=True, width="stretch")
            if league:
                values = league_ui.player_rates(stats, category)
                for column, key in zip(st.columns(2), ("bbPercent", "kPercent")):
                    with column:
                        st.metric(league_ui.LABELS[key], league_ui.formatted(values[key], key), border=True)
                        league_ui.card_context(stats, league, category, key)
    if missing:
        st.warning("제공되지 않은 항목은 —로 표시됩니다: " + ", ".join(missing))


def season_selector(label):
    info = resolve_seasons(current_date().isoformat())
    if info["warning"]:
        st.warning(info["warning"])
    years = info["years"]
    current = st.session_state.get("selected_season", info["latest"])
    if current not in years:
        years = sorted(set(years + [current]))
    return st.selectbox(label, years, index=years.index(info["latest"]),
                        key="selected_season", persist_state="session")


def inspect_player(player, season):
    records, errors, timestamps = {}, {}, {}
    for category in ("hitting", "pitching"):
        try:
            records[category], timestamps[category] = fetch_stats(player["id"], season, category)
        except API_ERRORS as error:
            records[category] = None
            errors[category] = error
    try:
        profile = fetch_profile(player["id"])
    except API_ERRORS:
        profile = player
        if any(member.get("position") in ("TWP", "Y") for member in player.get("memberships", [])):
            profile = dict(player, primaryPosition={"abbreviation": "TWP"})
        st.caption("선수 프로필을 확인하지 못해 확인된 시즌 기록으로 분석합니다.")
    result = detect_role(records, profile, errors)
    result.update(records=records, errors=errors, timestamps=timestamps, profile=profile)
    for category, error in errors.items():
        show_api_error(f"{player['fullName']} · {'타격' if category == 'hitting' else '투구'} 기록 (없음으로 단정하지 않음)", error)
    return result


def detected_category(key, player, season, analysis, preferred=None):
    options = analysis["options"]
    if len(options) == 2:
        context = (player["id"], season)
        choice_key = f"{key}_stats_category"
        if st.session_state.get(f"{key}_stats_context") != context:
            st.session_state[choice_key] = preferred if preferred in options else analysis["preferred"]
            st.session_state[f"{key}_stats_context"] = context
        st.caption("타격·투구 전환 제공: " + analysis["reason"])
        return st.radio("표시할 기록", options, format_func=lambda value: "타격 기록 (Hitting)" if value == "hitting" else "투구 기록 (Pitching)",
                        key=choice_key, horizontal=True, persist_state="session")
    if options:
        category = options[0]
        st.caption(f"자동 분석: {'투구' if category == 'pitching' else '타격'} 기록 · {analysis['reason']}")
        if len(analysis["available"]) == 2:
            st.caption("다른 종류의 기록도 있으나 겸업 출전량 기준에 미달해 주된 기록을 표시합니다.")
        return category
    return None


def pitching_notes(stats):
    labels = {value: label.split(" · ")[0] for label, value in PITCHING_METRICS.items()}
    if stats.get("_derived"):
        st.caption("원자료로 계산한 항목: " + ", ".join(labels.get(key, key) for key in stats["_derived"]))
    st.caption("IP의 .1은 1아웃, .2는 2아웃입니다. 예: 6.1 = 6⅓이닝. 차트 높이는 실제 이닝으로 환산하고 툴팁은 야구 표기로 표시합니다.")
    if stats.get("_outs") == 0:
        st.info("기록된 아웃이 0이므로 이닝을 분모로 하는 비율 지표는 표시하지 않습니다.")
    if numeric(stats.get("baseOnBalls")) == 0:
        st.caption("볼넷이 0이면 K/BB는 분모가 0이므로 —로 표시합니다.")


def dashboard(view="선수 기록"):
    season = season_selector("시즌")
    st.caption("이름을 검색한 뒤 선수를 선택하세요. ☆로 저장한 선수는 모든 화면의 즐겨찾기에서 사용할 수 있습니다.")
    player = player_picker("dashboard", season=season)
    if player is None:
        st.info("선수를 검색하고 결과에서 선택해 주세요.")
        return
    ui.remember_player(player)
    analysis = inspect_player(player, season)
    render_profile(player, analysis["profile"], season, change_favorite, favorite_mark(player["id"]).strip() == "★")
    if view == "수상 경력":
        render_awards(player, season, force_open=True)
    elif view == '커리어 분석':
        default='pitching' if (analysis['profile'].get('primaryPosition') or {}).get('abbreviation')=='P' else 'hitting'
        career_ui.panel(player,analysis['profile'],default)
    elif view == 'Statcast 분석':
        category = detected_category('dashboard',player,season,analysis)
        if category:
            statcast_ui.panel(player,season,category)
    elif view == '백분위·유사 선수':
        category=detected_category('dashboard',player,season,analysis)
        if category:
            rankings_ui.panel(player,season,category,change_favorite)
    elif view == "AI 분석":
        category = detected_category("dashboard", player, season, analysis)
        mode = st.radio(t('sc_ai_mode'),['standard','statcast','career'],
                        format_func=lambda v:t('career_ai') if v=='career' else t('sc_mode_standard' if v == 'standard' else 'sc_ai'),
                        horizontal=True,key='ai_analysis_mode')
        if mode=='career':
            default='pitching' if (analysis['profile'].get('primaryPosition') or {}).get('abbreviation')=='P' else 'hitting'
            career_ui.panel(player,analysis['profile'],default)
            return
        if mode == 'statcast':
            if category:
                statcast_ui.panel(player,season,category,prefix='statcast_ai')
            return
        if category is None:
            st.info("이 시즌에서 분석 가능한 기록을 확인하지 못했습니다. 다른 시즌을 선택하세요.")
        elif not st.session_state.get("ai_enabled"):
            st.info("왼쪽의 로컬 AI 사용을 켜고 모델 목록을 확인하세요.")
        else:
            league = league_ui.load_comparison(season, category)
            with st.container(border=True, key="ai_analyst_panel"):
                ai_ui.player_panel(player, season, category, analysis["records"].get(category),
                                   analysis["timestamps"].get(category), fetch_history, fetch_awards, league=league)
    else:
        render_season_analysis(player, season, analysis)


def render_season_analysis(player, season, analysis):
    category = detected_category("dashboard", player, season, analysis)
    if category is None:
        st.info("해당 시즌 기록 없음" if not analysis["errors"] else "기록 조회 오류로 선수 역할을 확인할 수 없습니다.")
        if analysis["errors"]:
            return
        # Historical charts remain available even when the selected season has no records.
        category = "pitching" if (analysis["profile"].get("primaryPosition") or {}).get("abbreviation") == "P" else "hitting"
        st.caption("선택 시즌 기록이 없어 프로필을 참고해 이전 시즌 차트만 조회합니다.")
    kind = "투구" if category == "pitching" else "타격"
    st.subheader(f"{player['fullName']} · {season} 정규시즌 {kind} 기록")
    st.caption(f"MLB ID {player['id']} · {kind} 기록만 표시")
    league = league_ui.load_comparison(season, category)
    standard_tab, advanced_tab, trends_tab, awards_tab = st.tabs([
        t('standard_section'), t('advanced_section'), t('trends_section'), '수상 경력'])
    with advanced_tab:
        if has_record(analysis['records'].get(category), category):
            advanced_ui.cards(analysis['records'].get(category), season, category, player['id'],
                              analysis['timestamps'].get(category), league)
            advanced_ui.player_chart(analysis['records'].get(category), season, category, player,
                                     analysis['timestamps'].get(category), league)
    with awards_tab:
        render_awards(player, season)
    with standard_tab:
        render_standard_analysis(player, season, analysis, category, league)
    with trends_tab:
        render_history_analysis(player, season, analysis, category, league)


def render_standard_analysis(player, season, analysis, category, league):
    kind = '투구' if category == 'pitching' else '타격'
    try:
        with st.spinner("MLB 공식 기록을 불러오는 중입니다…"):
            stats = analysis["records"].get(category)
            fetched_at = analysis["timestamps"].get(category, "조회 실패")
        st.caption(f"데이터 조회 시각: {fetched_at} · 15분간 임시 저장")
        if category in analysis["errors"]:
            st.warning("선택한 기록을 조회하지 못했습니다. 기록이 없는 것으로 단정하지 않습니다.")
        elif not has_record(stats, category):
            st.info(f"해당 시즌 기록 없음 · 선택한 선수의 {season} 정규시즌 {kind} 기록이 없습니다. 다른 시즌이나 유형을 선택해 주세요.")
        else:
            show_metrics(stats, category, league)
            league_ui.chart([player], [stats], league, category, "dashboard")
            if category == "pitching":
                pitching_notes(stats)
    except API_ERRORS as error:
        show_api_error("시즌 기록", error)


def render_history_analysis(player, season, analysis, category, league):
    kind = '투구' if category == 'pitching' else '타격'
    st.subheader(f"시즌별 {kind} 기록 변화")
    latest = resolve_seasons(current_date().isoformat())["latest"]
    chart_end = max(latest, season)
    if category == "pitching":
        start, end = st.slider("차트 시즌 범위", 1876, chart_end, (max(2020, chart_end - 6), chart_end), key="pitch_history_range")
    else:
        start, end = st.slider("차트 시즌 범위", 1876, chart_end, (max(1876, chart_end - 2), chart_end), key="history_range")
    try:
        with st.spinner("시즌별 기록을 불러오는 중입니다…"):
            records, problems, fetched_at = fetch_history(player["id"], start, end, category)
        st.caption(f"시즌별 데이터 조회 시각: {fetched_at}")
        advanced_ui.trends(records, season, category, player, fetched_at)
        if problems:
            st.warning("API 기록을 확인할 수 없는 시즌: " + ", ".join(map(str, problems)))
        missing = [str(year) for year, record in records.items() if record is None and year not in problems]
        if missing:
            st.info("기록 없는 시즌: " + ", ".join(missing))
        keys = PITCH_HISTORY_KEYS if category == "pitching" else RATE_KEYS
        chart_labels = {value: label.split(" · ")[0] for label, value in (PITCHING_METRICS if category == "pitching" else METRICS).items()}
        missing_fields = [f"{year}: " + ", ".join(chart_labels[key] for key in keys if chart_value(record, key) is None)
                          for year, record in records.items() if record and any(chart_value(record, key) is None for key in keys)]
        if missing_fields:
            st.warning("제공되지 않은 차트 항목 · " + " / ".join(missing_fields))
        if any(chart_value(record, key) is not None for record in records.values() for key in keys):
            figure = ui.chart_controls(history_figure(records, category), f"history_{category}")
            st.plotly_chart(figure, width="stretch", key="history_chart")
            st.caption("마우스로 값 확인·확대·범례 클릭이 가능합니다. 누락된 값은 선으로 연결하지 않습니다.")
        else:
            st.info("선택한 범위에 차트로 표시할 기록이 없습니다.")
    except API_ERRORS as error:
        show_api_error("시즌별 차트", error)

    if st.session_state.get("ai_enabled"):
        with st.container(border=True, key="ai_analyst_panel"):
            ai_ui.player_panel(player, season, category, analysis["records"].get(category),
                               analysis["timestamps"].get(category), fetch_history, fetch_awards, league=league)


def comparison_page():
    st.subheader("두 선수 같은 시즌 비교")
    season = season_selector("비교 시즌")
    st.caption(f"{season} 정규시즌 · 선수를 선택하면 비교 가능한 기록을 자동으로 확인합니다.")
    columns = st.columns(2)
    players = []
    for index, column in enumerate(columns):
        with column:
            st.markdown(f"**선수 {index + 1}**")
            players.append(player_picker(f"compare_{index}", season=season))
    if any(player is None for player in players):
        st.info("비교할 두 선수를 모두 선택해 주세요.")
        return
    if players[0]["id"] == players[1]["id"]:
        st.warning("서로 다른 두 선수를 선택해 주세요.")
        return
    career_ui.comparison(players)
    render_award_comparison(players)
    analyses = [inspect_player(player, season) for player in players]
    for index, (player, analysis) in enumerate(zip(players, analyses)):
        with columns[index]:
            render_profile(player, analysis["profile"], season=season, key=f"compare_profile_{index}")
    if any(analysis.get("uncertain") for analysis in analyses):
        st.warning("일부 종류의 기록 조회에 실패해 선수 역할과 비교 범주를 확정할 수 없습니다. 기록 새로고침으로 다시 시도해 주세요.")
        return
    common = set(analyses[0]["options"]) & set(analyses[1]["options"])
    preferred = "hitting" if "hitting" in common else "pitching" if "pitching" in common else None
    categories = []
    for index, (player, analysis) in enumerate(zip(players, analyses)):
        with columns[index]:
            categories.append(detected_category(f"compare_{index}", player, season, analysis, preferred))
    if not common or categories[0] != categories[1]:
        st.info("같은 종류의 기록으로 비교할 수 없습니다. 타자와 투수의 통계는 서로 비교하지 않습니다. 겸업 선수의 표시할 기록을 맞추거나 다른 선수·시즌을 선택해 주세요.")
        if any(not analysis["options"] for analysis in analyses):
            st.caption("해당 시즌 기록 없음 또는 조회 실패로 비교 범주를 확인하지 못한 선수가 있습니다.")
        return
    category = categories[0]
    kind = "투구" if category == "pitching" else "타격"
    records = []
    for player, analysis in zip(players, analyses):
        stats = analysis["records"].get(category)
        records.append(stats if has_record(stats, category) else None)
        st.caption(f"{player['fullName']} (ID {player['id']}) · {season} · {kind} · 조회 시각 {analysis['timestamps'].get(category, '조회 실패')}")
        if not has_record(stats, category) and category not in analysis["errors"]:
            st.info(f"{player['fullName']}: 해당 시즌 기록 없음 · {season} 정규시즌 {kind}")
    validate_comparison(records, category)
    league = league_ui.load_comparison(season, category)
    metrics = PITCHING_METRICS if category == "pitching" else METRICS
    rows = []
    for label, key in metrics.items():
        row = {"지표": label}
        for player, stats in zip(players, records):
            value = (stats or {}).get(key)
            row[f"{player['fullName']} (ID {player['id']})"] = "—" if value is None or value == "" else str(value)
        rows.append(row)
    st.table(rows)
    advanced_ui.comparison(players, records, season, category,
                           [a['timestamps'].get(category) for a in analyses], league)
    st.caption("누락된 항목과 조회 실패 항목은 —로 표시하며 차트에서 제외합니다.")
    league_ui.chart(players, records, league, category, "comparison")
    statcast_ui.comparison(players,season,category)
    if category == "pitching":
        st.info("ERA·WHIP·BB/9는 일반적으로 낮을수록, K/9는 높을수록 양호합니다. SO는 투구량의 영향을 받습니다. IP는 투구량이며 그 자체로 실력의 우열을 뜻하지 않습니다.")
        st.write("이닝이 적으면 비율 지표가 크게 흔들릴 수 있습니다. 선발·구원 역할, 상대 타자와 경기 환경도 다르므로 한 지표만으로 우열을 판단하지 않습니다.")
        for player, stats in zip(players, records):
            if stats:
                pitching_notes(stats)
                st.caption(f"{player['fullName']} 표본: IP {stats.get('inningsPitched') or '—'} · GS {stats.get('gamesStarted', '—')} · 상대 타자 수 {stats.get('battersFaced', '—')}")
        if any(stats and stats.get("_outs") is not None and stats["_outs"] < 90 for stats in records):
            st.warning("30이닝 미만의 투구 표본이 포함되어 있습니다. 이는 참고용 표시이며 비율 지표 해석에 주의가 필요합니다.")
        if any(stats for stats in records):
            st.plotly_chart(comparison_figure(players, records, PITCH_COMPARE_KEYS, category), width="stretch", key="comparison_pitching")
    elif any(stats for stats in records):
        st.plotly_chart(comparison_figure(players, records, RATE_KEYS), width="stretch", key="comparison_rates")
        st.plotly_chart(comparison_figure(players, records, ("homeRuns", "rbi")), width="stretch", key="comparison_counts")


    if st.session_state.get("ai_enabled"):
        ai_ui.comparison_panel(players, season, category, records,
                               [analysis["timestamps"].get(category) for analysis in analyses], league=league)


def reset_search_display():
    """Remount autocomplete labels after a locale change; retain selected IDs."""
    for key in ("dashboard", "compare_0", "compare_1"):
        chosen = st.session_state.get(f"{key}_chosen")
        selected = st.session_state.get(f"{key}_selected")
        clear_autocomplete(key)
        if chosen:
            st.session_state[f"{key}_chosen"] = chosen
        if selected is not None:
            st.session_state[f"{key}_selected"] = selected


def main():
    st.set_page_config(page_title="MLB AI Analytics Pro · V4.9", page_icon="⚾", layout="wide")
    language_selector(reset_search_display)
    ui.apply_styles()
    from services.cache_manager import begin_view
    begin_view()
    import os
    from components.system_performance_ui import page as performance_page, freshness, label
    from utils.config import cloud
    if not cloud() and os.environ.get('MLB_ANALYTICS_DEVELOPER') == '1' and st.sidebar.checkbox(label('시스템 상태', 'System Performance')):
        performance_page()
        return
    favorites, warning = load_favorites()
    st.session_state["_favorites"] = favorites
    if warning:
        st.warning(warning)
    if st.session_state.get("_favorite_notice"):
        st.toast(st.session_state.pop("_favorite_notice"))
    if st.session_state.get("_favorite_error"):
        st.warning(st.session_state.pop("_favorite_error"))
    page = ui.sidebar(favorites)
    ai_ui.settings()
    ui.header(page)
    if st.sidebar.button("기록 새로고침"):
        # Invalidate freshness without deleting cached datasets or personal JSON.
        from services.database import connection
        import sqlite3
        try:
            if not cloud():
                with connection() as db, db:
                    db.execute('UPDATE datasets SET expires_at=0')
        except (sqlite3.Error, OSError):
            st.warning(label('영구 캐시 새로고침 실패. DB 접근 권한을 확인하세요.', 'Persistent refresh failed. Check database access.'))
        st.cache_data.clear()
        leaderboard_ui.clear_cache()
        career_ui.clear_cache()
        rankings_ui.clear_cache()
        statcast_ui.clear_cache()
        st.session_state.pop("ai_player_context", None)
        fetch_league_average.clear()
        team_totals.clear()
        season_membership.clear()
        resolve_seasons.clear()
        fetch_profile.clear()
        fetch_current_team_details.clear()
        fetch_awards.clear()
        fetch_headshot.clear()
        fetch_stats.clear()
        fetch_history.clear()
        search_players.clear()
        fetch_teams.clear()
        fetch_roster.clear()
        fetch_season_players.clear()
    st.sidebar.caption("무료 MLB Stats API · 통계 15분 · 팀 24시간 · 로스터 1시간 저장")
    if page=='MLB 선수 랭킹':
        leaderboard_ui.page(change_favorite,resolve_seasons)
    elif page == "선수 비교":
        comparison_page()
    else:
        if page == "대시보드":
            ui.home()
        dashboard(page)
    with st.expander("통계 용어와 계산 방법"):
        st.write("AVG: 타율 · OBP: 출루율 · SLG: 장타율 · OPS: 출루율 + 장타율 · HR: 홈런 · RBI: 타점")
        st.write("ERA = 자책점 × 9 / 이닝 · WHIP = (볼넷 + 피안타) / 이닝 · K/9 = 탈삼진 × 9 / 이닝 · BB/9 = 볼넷 × 9 / 이닝 · K/BB = 탈삼진 / 볼넷")
        st.write("W: 승 · L: 패 · SO: 탈삼진 · IP: 투구 이닝 · BB: 볼넷 허용 · H: 피안타 · 투수 HR: 피홈런 · GS: 선발 등판 · SV: 세이브")
        st.write("API의 유효한 비율 지표를 우선 사용하고, 누락된 경우에만 원자료로 계산합니다. 6.1이닝은 19아웃입니다. 분모가 0이거나 필요한 값이 없으면 —로 표시합니다.")
    st.markdown("출처: [MLB Stats API](https://statsapi.mlb.com/api/v1/)")
    st.caption("시즌 성적은 포스트시즌과 시범경기를 제외합니다. 수상 이력은 별도 범위입니다. 진행 중인 시즌은 현재까지의 기록입니다. 원자료 없는 수치를 만들지 않습니다.")
    freshness()


