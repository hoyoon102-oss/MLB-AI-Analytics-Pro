"""Optional Streamlit controls; MLB dashboard remains independent of Ollama."""
import threading
from datetime import datetime, timezone

import requests
from utils.i18n import st, raw_st, current_language, t, tr, LANGUAGES

from services.ai_analyst import (AIError, comparison_context, context_key, conversation,
                        generate, list_models, player_context)
from components.ui_components import ai_status
from components.league_ui import ai_league_context


SCOUT = """다음 5개 제목으로 근거 수치를 인용한 스카우팅 보고서를 작성하세요:
1. 선수 종합 평가 2. 주요 강점 3. 개선이 필요한 부분 또는 추가 확인이 필요한 지표
4. 시즌 성적 분석 5. 통계에 근거한 결론. 제공된 시즌 추이와 고급 지표만 사용하세요."""
CAREER = """제공된 커리어 시즌 범위를 명시하고 시즌별 개선·하락, Python이 계산한 변화량,
수상 시즌과 통계의 관계를 설명하세요. 통계적 성취와 공식 수상을 별도 항목으로 구분하세요.
연속되지 않은 시즌은 기간 차이를 밝히세요. 확인되지 않은 우승이나 사건을 언급하지 마세요."""
COMPARE = """같은 시즌의 두 선수를 비교하세요. 확인된 지표와 Python 변화량을 사용해
각각의 장단점, 경기·타석·이닝 등 출장량과 표본 차이, 비교의 한계를 설명하세요.
타격과 투구를 혼합하지 말고 한 지표만으로 승자를 선언하지 마세요."""


def request_analysis(model, context, task, history=(), timeout=300):
    if "ai_request_lock" not in st.session_state:
        st.session_state["ai_request_lock"] = threading.Lock()
    lock = st.session_state["ai_request_lock"]
    if not lock.acquire(blocking=False):
        raise AIError("이미 AI 요청이 진행 중입니다. 완료된 후 다시 시도하세요.")
    try:
        task = tr(task) if task in (SCOUT, CAREER, COMPARE) else task
        return generate(model, context, task, history, timeout, language=current_language())
    finally:
        lock.release()


def settings():
    from utils.config import cloud
    if cloud():
        st.session_state['ai_enabled'] = False
        st.sidebar.info('클라우드 데모: AI 비활성화 · 설정은 세션에만 저장됩니다.' if current_language() == 'ko' else 'Cloud demo: AI disabled; preferences last for this session only.')
        return
    enabled = st.sidebar.toggle("로컬 AI 사용", key="ai_enabled")
    if not enabled:
        return
    st.sidebar.caption("Ollama 로컬 전용 · 유료 API·API 키 불필요")
    with st.sidebar.expander("Ollama 연결 안내"):
        st.markdown("[Ollama 설치](https://ollama.com/download/windows) 후 앱을 실행하세요.")
        st.code("ollama pull qwen2.5:1.5b", language="powershell")
        st.write("처음에는 작은 모델로 테스트하세요. 위 명령은 사용자가 직접 실행할 때만 모델을 다운로드합니다.")
    if st.sidebar.button("모델 목록 새로고침", key="ai_refresh_models"):
        try:
            with st.spinner("Ollama 모델 확인 중…"):
                st.session_state["ai_models"] = list_models()
            st.session_state.pop("ai_models_error", None)
            st.session_state["ai_connection_check"] = {"ok": True, "at": datetime.now(timezone.utc)}
        except AIError as error:
            st.session_state["ai_models"] = []
            st.session_state["ai_models_error"] = str(error)
            st.session_state["ai_connection_check"] = {"ok": False, "at": datetime.now(timezone.utc)}
    if st.session_state.get("ai_models_error"):
        st.sidebar.warning(st.session_state["ai_models_error"])
    models = st.session_state.get("ai_models", [])
    if models:
        if st.session_state.get("ai_model") not in models:
            st.session_state["ai_model"] = models[0]
        st.sidebar.selectbox("설치된 로컬 AI 모델 (작은 용량순)", models, key="ai_model")
    else:
        st.sidebar.info("모델 목록 새로고침을 눌러 연결을 확인하세요.")
    st.sidebar.number_input("AI 응답 제한 시간 (초)", 30, 900, 300, step=30, key="ai_timeout")


def ready():
    if not st.session_state.get("ai_enabled"):
        return False
    status, _, detail = ai_status()
    st.caption(f"로컬 AI · {status} · {detail}")
    if st.session_state.get("ai_model") not in st.session_state.get("ai_models", []):
        st.info("왼쪽에서 모델 목록을 새로고침하고 로컬 모델을 선택하세요.")
        return False
    st.caption("AI 해석에는 오류가 있을 수 있습니다. 아래 입력 자료와 MLB 공식 기록을 함께 확인하세요.")
    return True


def report(context, task, key):
    if task == SCOUT and not any(isinstance(value, (int, float)) for value in (context.get("statistics") or {}).values()):
        st.info(t("ai_no_verified_season"))
        return
    model = st.session_state["ai_model"]
    identity = context_key(context, model)
    saved_key = f"{key}_result"
    if st.button("AI 분석 생성 / 다시 시도", key=f"{key}_generate"):
        try:
            with st.spinner("로컬 AI 분석 중입니다. 컴퓨터 성능에 따라 몇 분 걸릴 수 있습니다…"):
                result = request_analysis(model, context, task, timeout=st.session_state.get("ai_timeout", 300))
            st.session_state[saved_key] = (identity, result, current_language())
        except AIError as error:
            st.error(str(error))
    saved = st.session_state.get(saved_key)
    if saved and saved[0] == identity:
        with st.container(border=True):
            st.caption("AI 스카우팅 리포트 · 공식 MLB 기록에 대한 AI 해석")
            report_language = saved[2] if len(saved) > 2 else "ko"
            if report_language != current_language():
                st.info(t("old_report_language", language=LANGUAGES[report_language]))
            raw_st.markdown(saved[1])
            st.caption(f"생성 모델: {model} · AI 해석 (공식 평가 아님)")


def chat(context):
    model = st.session_state["ai_model"]
    messages = conversation(st.session_state, context_key(context, model))
    player = context["player"]
    kind = "타격" if context["category"] == "hitting" else "투구"
    st.caption(f"대화 대상: {player['name']} · MLB ID {player['id']} · {context['season']} · {kind}")
    if st.button("대화 초기화", key="ai_chat_clear"):
        messages.clear()
        st.session_state.pop("ai_chat_pending", None)
        st.session_state.pop("ai_chat_error", None)
    for message in messages:
        with st.chat_message(message["role"]):
            if message.get("language", "ko") != current_language():
                st.caption(t("message_language", language=LANGUAGES[message.get("language", "ko")]))
            raw_st.markdown(message["content"])
    pending = st.session_state.get("ai_chat_pending")
    if st.session_state.get("ai_chat_error"):
        st.error(st.session_state["ai_chat_error"])
    retry = st.button("실패한 질문 다시 시도", key="ai_chat_retry") if pending else False
    question = st.chat_input("이 선수의 기록에 대해 질문하세요", max_chars=2000, key="ai_question")
    question = question or (pending if retry else None)
    if question:
        st.session_state["ai_chat_pending"] = question
        try:
            with st.spinner("선택한 선수의 자료로 답변 중…"):
                answer = request_analysis(model, context, question, messages, st.session_state.get("ai_timeout", 300))
            messages.extend([{"role": "user", "content": question, "language": current_language()},
                             {"role": "assistant", "content": answer, "language": current_language()}])
            del messages[:-20]
            st.session_state.pop("ai_chat_pending", None)
            st.session_state.pop("ai_chat_error", None)
            st.rerun()
        except AIError as error:
            st.session_state["ai_chat_error"] = str(error) + " 질문을 보관했습니다. 다시 시도하거나 새 질문을 입력하세요."
            st.rerun()


def player_panel(player, season, category, stats, fetched_at, fetch_history, fetch_awards, league=None):
    st.subheader("AI 선수 분석")
    if not ready():
        return
    identity = (player["id"], season, category)
    if st.session_state.get("ai_player_identity") != identity:
        st.session_state["ai_player_identity"] = identity
        st.session_state.pop("ai_player_context", None)
        conversation(st.session_state, None)
    st.caption("자료 준비는 MLB 조회만 수행합니다. AI 생성은 각 버튼 또는 질문 전송 시에만 실행합니다.")
    end = max(season, st.session_state.get("selected_season", season))
    start, end = st.slider("AI 커리어 분석 시즌 범위", 1876, end, (max(1876, end - 9), end), key=f"ai_range_{end}")
    if st.button("AI 분석 자료 준비 / 새로고침", key="ai_prepare"):
        records, problems, history_at, awards = {}, [], None, None
        history_error = awards_error = None
        with st.spinner("검증된 MLB 시즌 기록과 수상 자료 준비 중…"):
            try:
                records, problems, history_at = fetch_history(player["id"], start, end, category)
            except (ValueError, TypeError, AttributeError, requests.RequestException):
                history_error = "시즌 이력 조회 실패; 통산 분석 불가"
            try:
                awards = fetch_awards(player["id"])
            except (ValueError, TypeError, AttributeError, requests.RequestException):
                awards_error = "수상 조회 실패; 수상 없음이 아님"
        st.session_state["ai_player_context"] = player_context(
            player, season, category, stats, fetched_at, records, history_at, problems, awards,
            history_error, awards_error)
    context = st.session_state.get("ai_player_context")
    if context and (context["player"]["id"], context["season"], context["category"]) != identity:
        context = None
    if not context:
        st.info("AI 분석 자료 준비를 눌러 주세요. 기본 범위는 최근 10개 시즌이며 이전 시즌도 선택할 수 있습니다.")
        return
    context = ai_league_context(context, league)
    st.caption("보고서는 준비된 자료 기준입니다. 범위를 바꾸거나 기록을 갱신한 뒤에는 자료를 다시 준비하세요.")
    for field in ("history_error", "awards_error"):
        if context.get(field):
            st.warning(context[field])
    with st.expander("AI에 전달하는 검증 자료 · 출처·조회 시각"):
        st.json(context)
    scout, career, discussion = st.tabs(["AI 선수 분석", "AI 커리어 분석", "AI에게 질문"])
    with scout:
        report(context, SCOUT, "ai_scout")
    with career:
        report(context, CAREER, "ai_career")
    with discussion:
        chat(context)


def comparison_panel(players, season, category, records, timestamps, league=None):
    st.subheader("AI 비교 분석")
    if not ready():
        return
    try:
        context = comparison_context([ai_league_context(player_context(player, season, category, record, timestamp), league)
                                      for player, record, timestamp in zip(players, records, timestamps)])
    except ValueError as error:
        st.info(str(error))
        return
    with st.expander("AI 비교 입력 자료"):
        st.json(context)
    report(context, COMPARE, "ai_comparison")
