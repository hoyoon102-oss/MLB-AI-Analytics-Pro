"""Localized compact cards and single-unit Plotly comparisons."""
import plotly.graph_objects as go
from utils.i18n import st, t
from analytics.advanced_stats import metrics, baselines, METHODS
from components.ui_components import style_chart
from analytics.pitching import number


def formatted(value, key):
    return 'N/A' if value is None else f'{value:.2f}%' if '%' in key else f'{value:.3f}'


def cards(stats, season, category, player_id, at, league=None, prefix='advanced'):
    data = metrics(stats, season, category, player_id, at)
    baseline = baselines(league, season, category)
    st.subheader(t('advanced_' + category))
    st.caption(t('advanced_note'))
    columns = st.columns(4)
    for index, (key, item) in enumerate(data.items()):
        with columns[index % 4].container(border=True):
            value = item['value']
            st.markdown(f'**{key}**', help=t('metric_' + key))
            st.markdown(f'### {formatted(value, key)}')
            with st.expander(t('advanced_explain')):
                st.write(t('metric_' + key))
                st.code(METHODS[key])
            base = baseline.get(key, {})
            st.caption(t('advanced_reference') if key.endswith('+') else t('advanced_average'))
            st.caption(formatted(base.get('value'), key))
            if value is not None and base.get('value') is not None:
                st.caption(t('advanced_delta') + f" {value-base['value']:+.3f}" + (' pp' if '%' in key else ''))
            st.caption('MLB Stats API · ' + t('advanced_local'))
            if item['constants']:
                st.caption('FanGraphs Guts · ' + str(season))
    with st.expander(t('advanced_provenance')):
        st.json({'metrics': data, 'baselines': baseline})
    return data


def player_chart(stats, season, category, player, at, league):
    data = metrics(stats, season, category, player['id'], at)
    key = st.selectbox(t('advanced_metric'), list(data), key='advanced_player_metric')
    baseline = baselines(league, season, category).get(key, {})
    fig = go.Figure()
    fig.add_bar(name=player['fullName'], x=[key], y=[data[key]['value']])
    fig.add_bar(name=t('advanced_reference') if key.endswith('+') else t('advanced_average'),
                x=[key], y=[baseline.get('value')])
    st.plotly_chart(style_chart(fig, height=360), key='advanced_player_chart')


def comparison(players, records, season, category, timestamps, league=None):
    st.subheader(t('advanced_comparison'))
    groups = []
    for index, (column, player, stats, at) in enumerate(zip(st.columns(2), players, records, timestamps)):
        with column:
            st.markdown(f"**{player['fullName']} · MLB ID {player['id']}**")
            groups.append(cards(stats, season, category, player['id'], at, league, f'compare_adv_{index}'))
    key = st.selectbox(t('advanced_metric'), list(groups[0]), key='advanced_compare_metric')
    fig = go.Figure()
    for player, data in zip(players, groups):
        fig.add_bar(name=player['fullName'], x=[key], y=[data[key]['value']])
    base = baselines(league, season, category).get(key, {}).get('value')
    if base is not None:
        fig.add_bar(name=t('advanced_reference') if key.endswith('+') else t('advanced_average'), x=[key], y=[base])
    st.plotly_chart(style_chart(fig, height=360), key='advanced_comparison_chart')


def trends(records, season, category, player, at):
    keys = list(metrics({}, season, category))
    options = keys + (['FIP / ERA', 'K% / BB%'] if category == 'pitching' else ['ISO / BABIP', 'K% / BB%'])
    chosen = st.selectbox(t('advanced_metric'), options, key=f'advanced_trend_{category}')
    selected = chosen.split(' / ')
    fig = go.Figure()
    years = sorted(records)
    data = {year: metrics(record, year, category, player['id'], at) for year, record in records.items()}
    for key in selected:
        values = [number((records[y] or {}).get('era')) if key == 'ERA' else data[y][key]['value'] for y in years]
        fig.add_scatter(x=years, y=values, name=key, mode='lines+markers', connectgaps=False)
    fig.update_xaxes(dtick=1)
    st.plotly_chart(style_chart(fig, height=360), key='advanced_trend_chart')
    st.caption(t('advanced_note'))
    with st.expander(t('advanced_provenance')):
        st.json(data)
