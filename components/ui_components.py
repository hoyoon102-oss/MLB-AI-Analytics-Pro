"""Presentation components for the Pro UI; no MLB requests or calculations."""
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from utils.i18n import st, t

PAGES = ["대시보드", "선수 기록", "선수 비교", "수상 경력", "AI 분석", "Statcast 분석", "백분위·유사 선수", "커리어 분석", "MLB 선수 랭킹"]
PAGE_ICONS = {"대시보드": "◈", "선수 기록": "▤", "선수 비교": "⇄", "수상 경력": "◇", "AI 분석": "✦", "Statcast 분석":"◉", "백분위·유사 선수":"▥", "커리어 분석":"↗", "MLB 선수 랭킹":"≡"}
COLORS = ["#60A5FA", "#FBBF24", "#2DD4BF", "#C4B5FD", "#FB7185", "#F8FAFC"]


def apply_styles():
    css = Path(__file__).with_name("ui_styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def navigate(page):
    st.session_state["pro_page"] = page


def select_player(player, page="선수 기록"):
    # Clear widgets that could restore a different player on the next rerun.
    for suffix in ("favorite_choice", "result", "auto", "selected", "context"):
        st.session_state.pop(f"dashboard_{suffix}", None)
    st.session_state["dashboard_chosen"] = dict(player)
    st.session_state["dashboard_mode"] = "즐겨찾기"
    navigate(page)


def remember_player(player):
    recent = st.session_state.get("pro_recent", [])
    identity = {"id": player["id"], "fullName": player["fullName"]}
    st.session_state["pro_recent"] = [identity] + [p for p in recent if p["id"] != player["id"]][:5]


def sidebar(favorites):
    st.sidebar.markdown("### MLB AI Analytics Pro")
    st.sidebar.caption("선수 데이터와 스카우팅을 한곳에서")
    page = st.sidebar.radio("화면 선택", PAGES, key="pro_page",
                            format_func=lambda name: f"{PAGE_ICONS[name]}  {name}", persist_state="session")
    with st.sidebar.expander(f"즐겨찾기 · {len(favorites)}명", expanded=bool(favorites)):
        if not favorites:
            st.caption("선수 이름 옆 ☆로 저장하세요.")
        for player in favorites:
            st.button(player["fullName"], key=f"sidebar_favorite_{player['id']}",
                      on_click=select_player, args=(player,), width="stretch")
    st.sidebar.divider()
    return page


def ai_status():
    check = st.session_state.get("ai_connection_check")
    if not st.session_state.get("ai_enabled"):
        return "AI 꺼짐", "neutral", "필요할 때 로컬 AI를 켜세요."
    if not check:
        return "연결 미확인", "warning", "모델 목록 새로고침으로 확인하세요."
    age = (datetime.now(timezone.utc) - check["at"]).total_seconds()
    at = check["at"].strftime("%H:%M UTC")
    if age > 60:
        return "연결 재확인 필요", "warning", f"마지막 확인 {at} · 새로고침하세요."
    if not check["ok"]:
        return "AI 사용 준비 필요", "warning", f"확인 {at} · 연결 또는 모델 설치를 확인하세요."
    model = st.session_state.get("ai_model")
    return "Ollama 확인됨", "success", f"{model or '모델 선택 필요'} · 확인 {at}"


def header(page):
    status, kind, detail = ai_status()
    model = st.session_state.get("ai_model") if st.session_state.get("ai_enabled") else None
    if model and model not in detail:
        detail = f"{model} · {detail}"
    st.markdown(f'''<header class="pro-header">
      <div><div class="pro-eyebrow">MLB AI ANALYTICS PRO <span>VERSION 4.9</span></div>
      <h1>MLB AI Analytics Pro</h1><p>{escape(t('subtitle'))}</p></div>
      <div class="pro-connection"><span class="pro-status {kind}">{escape(status)}</span>
      <small>{escape(detail)}</small></div></header>
      <div class="pro-page-title">{escape(PAGE_ICONS[page])} &nbsp;{escape(page)}</div>''', unsafe_allow_html=True)


def home():
    with st.container(border=True, key="home_intro"):
        st.caption("공식 기록에서 시작하는 선수 분석")
        st.subheader("기록을 읽고, 선수의 흐름을 발견하세요.")
        st.write("선수를 검색해 시즌 성적과 커리어를 살펴보고, 같은 시즌의 두 선수를 비교하세요.")
        for column, page, label in zip(st.columns(4), PAGES[1:],
                                        ["기록 열기", "비교 열기", "수상 열기", "AI 분석 열기"]):
            column.button(label, key=f"home_{page}", on_click=navigate, args=(page,), width="stretch")
    recent = st.session_state.get("pro_recent", [])
    if recent:
        st.caption("최근 본 선수 · 이 세션에서만 저장")
        columns = st.columns(3)
        for index, person in enumerate(recent):
            columns[index % 3].button(person["fullName"], key=f"recent_{person['id']}", on_click=select_player, args=(person,), width="stretch")
    st.subheader("선수 검색")


def style_chart(figure, height=None):
    figure.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=COLORS, font=dict(family="Arial, Malgun Gothic, sans-serif", color="#F8FAFC", size=12),
        hoverlabel=dict(bgcolor="#18243A", bordercolor="#2B3E56", font_color="#F8FAFC"),
        legend=dict(orientation="h", y=-.2, x=0), margin=dict(l=45, r=24, t=55, b=85),
        **({"height": height} if height else {}))
    figure.update_xaxes(gridcolor="#2B3E56", zerolinecolor="#2B3E56", automargin=True)
    figure.update_yaxes(gridcolor="#2B3E56", zerolinecolor="#2B3E56", automargin=True)
    return figure


def chart_controls(figure, key):
    names = list(dict.fromkeys(trace.name for trace in figure.data if trace.name))
    with st.expander("차트 표시 지표 선택"):
        selected = st.multiselect("표시할 지표 / 선수", names, default=names, key=f"{key}_visible")
    for trace in figure.data:
        trace.visible = True if trace.name in selected else "legendonly"
    return figure
