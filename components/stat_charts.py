"""Existing standard-statistic Plotly charts, with formulas unchanged."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from analytics.pitching import PITCHING_METRICS, PITCH_HISTORY_KEYS, PITCH_COMPARE_KEYS, chart_value
from analytics.standard import METRICS, RATE_KEYS, numeric
from services.player_stats import validate_comparison
import components.ui_components as ui
def history_figure(records, category="hitting"):
    if category == "pitching":
        return pitching_figure(records=records)
    figure = go.Figure()
    years = sorted(records)
    for key in RATE_KEYS:
        figure.add_trace(go.Scatter(
            x=years, y=[numeric((records[year] or {}).get(key)) for year in years],
            name=key.upper(), mode="lines+markers", connectgaps=False,
            hovertemplate="%{x}년: %{y:.3f}<extra>%{fullData.name}</extra>"))
    figure.update_layout(xaxis_title="시즌", yaxis_title="기록", hovermode="x unified",
                         legend_title_text="지표", xaxis=dict(dtick=1), yaxis=dict(tickformat=".3f"))
    return ui.style_chart(figure, height=420)


def comparison_figure(players, records, keys, category="hitting"):
    validate_comparison(records, category)
    if category == "pitching":
        return pitching_figure(players=players, comparison=records)
    figure = go.Figure()
    for person, stats in zip(players, records):
        figure.add_trace(go.Bar(name=f"{person['fullName']} (ID {person['id']})",
                               x=[label for label, key in METRICS.items() if key in keys],
                               y=[numeric((stats or {}).get(key)) for key in keys]))
    figure.update_layout(barmode="group", xaxis_title="지표", yaxis_title="기록")
    return ui.style_chart(figure, height=420)


def pitching_figure(records=None, players=None, comparison=None):
    is_comparison = comparison is not None
    keys = PITCH_COMPARE_KEYS if is_comparison else PITCH_HISTORY_KEYS
    labels = {value: label for label, value in PITCHING_METRICS.items()}
    directions = {"era": "낮을수록 양호", "whip": "낮을수록 양호",
                  "strikeOuts": "누적 기록 · 이닝과 함께 확인", "inningsPitched": "투구량 · 우열 기준 아님",
                  "strikeoutsPer9Inn": "일반적으로 높을수록 양호", "walksPer9Inn": "낮을수록 양호"}
    figure = make_subplots(rows=3, cols=2,
                           subplot_titles=[f"{labels[key]}<br>{directions[key]}" for key in keys],
                           vertical_spacing=.15)
    years = sorted(records) if not is_comparison else None
    for index, key in enumerate(keys):
        row, col = index // 2 + 1, index % 2 + 1
        if is_comparison:
            for player_index, (person, stats) in enumerate(zip(players, comparison)):
                figure.add_trace(go.Bar(
                    x=[f"{person['fullName']} (ID {person['id']})"],
                    y=[chart_value(stats, key)], customdata=[str((stats or {}).get(key)) if (stats or {}).get(key) is not None else "—"],
                    name=f"{person['fullName']} (ID {person['id']})", legendgroup=str(person["id"]),
                    showlegend=index == 0, marker_color=["#38bdf8", "#fbbf24"][player_index],
                    hovertemplate="%{x}<br>기록: %{customdata}<extra></extra>"), row=row, col=col)
        else:
            figure.add_trace(go.Scatter(
                x=years, y=[chart_value(records[year], key) for year in years],
                customdata=[str((records[year] or {}).get(key)) if (records[year] or {}).get(key) is not None else "—" for year in years],
                mode="lines+markers", connectgaps=False, name=labels[key], showlegend=False,
                line=dict(color="#38bdf8", width=3),
                hovertemplate="%{x}년<br>기록: %{customdata}<extra></extra>"), row=row, col=col)
            figure.update_xaxes(dtick=1, title_text="시즌", row=row, col=col)
        figure.update_yaxes(title_text="이닝 (실수 환산)" if key == "inningsPitched" else labels[key].split(" · ")[0],
                            rangemode="tozero", row=row, col=col)
    figure.update_layout(height=1000, margin=dict(t=65, b=40), barmode="group")
    return ui.style_chart(figure, height=900)

