"""League selectors and rate comparisons; no statistics are invented here."""
import plotly.graph_objects as go
import requests

from utils.i18n import st, t
from services.league_stats import (HIT_KEYS, PITCH_KEYS, LABELS, LEAGUES, LOWER, LeagueDataError,
                          differences, fetch_league_average, player_rates, season_membership, team_totals)
from components.ui_components import style_chart


def load_comparison(season, category):
    if not st.toggle(t("league_toggle"), key="league_enabled", persist_state="session"):
        return None
    league_id = st.selectbox(t("league_scope"), list(LEAGUES), format_func=LEAGUES.get,
                            key="league_scope", persist_state="session")
    try:
        with st.spinner(t("league_loading")):
            result = fetch_league_average(season, league_id, category)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        st.warning(t("league_unavailable"))
        if st.button("리그 평균 다시 시도", key="league_retry"):
            fetch_league_average.clear()
            team_totals.clear()
            season_membership.clear()
            st.rerun()
        return None
    st.caption(t("league_caption", season=season, league=LEAGUES[league_id],
                 teams=result["team_count"], at=result["retrieved_at"]))
    st.caption(t("league_note"))
    with st.expander(t("league_source")):
        st.write(result["method"])
        st.markdown(f"[MLB Stats API]({result['source']})")
        st.json({"team_ids": result["team_ids"], "totals": result["totals"],
                 "rates": result["rates"], "membership_source": result["membership_source"]})
    return result


def formatted(value, key):
    if value is None:
        return "—"
    return f"{value:.2f}%" if key in ("bbPercent", "kPercent") else f"{value:.3f}" if key in HIT_KEYS else f"{value:.2f}"


def card_context(stats, aggregate, category, key):
    if not aggregate or key not in aggregate["rates"]:
        return
    values = player_rates(stats, category)
    value, average = values.get(key), aggregate["rates"].get(key)
    if value is None or average is None:
        st.caption(t("league_value_missing"))
        return
    delta = differences(stats, aggregate, category).get(key)
    direction = "higher" if delta > 0 else "lower" if delta < 0 else "equal"
    display_delta = f"{delta:+.2f} pp" if key in ("bbPercent", "kPercent") else f"{delta:+.3f}"
    st.caption(t("league_value", league=LEAGUES[aggregate["league_id"]], value=formatted(average, key),
                 delta=display_delta, direction=t(direction)))


def comparison_figure(players, records, aggregate, category, key):
    if aggregate["category"] != category or key not in (HIT_KEYS if category == "hitting" else PITCH_KEYS):
        raise LeagueDataError("타격·투구 기록을 섞어 비교할 수 없습니다.")
    figure = go.Figure()
    palette = ["#3B82F6", "#60A5FA"]
    for index, (player, stats) in enumerate(zip(players, records)):
        value = player_rates(stats, category).get(key)
        label = f"{player['fullName']} (ID {player['id']})"
        figure.add_trace(go.Bar(name=label, x=[LABELS[key]], y=[value],
            marker_color=palette[index % 2], customdata=[formatted(value, key)],
            hovertemplate="%{fullData.name}<br>%{x}: %{customdata}<extra></extra>"))
    value = aggregate["rates"].get(key)
    figure.add_trace(go.Bar(name=LEAGUES[aggregate["league_id"]], x=[LABELS[key]], y=[value],
        marker_color="#94A3B8", customdata=[formatted(value, key)],
        hovertemplate="%{fullData.name}<br>%{x}: %{customdata}<extra></extra>"))
    figure.update_layout(barmode="group", title=f"{aggregate['season']} · {LEAGUES[aggregate['league_id']]} · {LABELS[key]}",
                         yaxis_title="%" if key in ("bbPercent", "kPercent") else LABELS[key])
    return style_chart(figure, height=420)


def chart(players, records, aggregate, category, key_prefix):
    if not aggregate:
        return
    st.subheader(t("league_chart"))
    keys = HIT_KEYS if category == "hitting" else PITCH_KEYS
    metric = st.selectbox(t("league_metric"), keys, format_func=LABELS.get, key=f"{key_prefix}_{category}_metric")
    if aggregate["rates"].get(metric) is None:
        st.info(t("league_value_missing"))
    st.caption("낮을수록 양호" if metric in LOWER else "일반적으로 높을수록 양호")
    st.plotly_chart(comparison_figure(players, records, aggregate, category, metric),
                    width="stretch", key=f"{key_prefix}_league_chart")
    st.caption(t("league_count_note"))


def ai_league_context(context, aggregate):
    """Attach only the matching selected-season/category benchmark and Python deltas."""
    from analytics.advanced_stats import baselines
    baseline = baselines(aggregate, context['season'], context['category'])
    context = dict(context, advanced_baselines=baseline,
        advanced_differences={key: item['value']-baseline[key]['value']
                             for key, item in context.get('advanced_statistics', {}).items()
                             if item['value'] is not None and baseline.get(key, {}).get('value') is not None})
    if not aggregate or aggregate["season"] != context["season"] or aggregate["category"] != context["category"]:
        return dict(context, league_comparison=None)
    return dict(context, league_comparison={
        "season": aggregate["season"], "league_id": aggregate["league_id"] , "category": aggregate["category"],
        "rates": aggregate["rates"], "source": aggregate["source"], "retrieved_at": aggregate["retrieved_at"],
        "team_count": aggregate["team_count"], "population": aggregate["population"],
        "limitations": aggregate["limitations"],
        "player_minus_league": differences(context.get("statistics"), aggregate, context["category"]),
        "significance": "No significance test; numerical difference only"})
