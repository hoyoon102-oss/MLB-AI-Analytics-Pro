"""Career timelines with explicit calendar gaps and verified award seasons."""
import plotly.graph_objects as go
from analytics.career_trends import metric_value,career_x,rolling,league_value
from components.ui_components import style_chart
from utils.i18n import t,tr


def timeline(career,metric,start,end,leagues=None,statcast=None,smooth=False,awards=()):
    category=career['category']
    years=list(range(start,end+1))
    records=career['records']
    values=[metric_value(records.get(y),y,category,metric,statcast) for y in years]
    fig=go.Figure(go.Scatter(x=years,y=values,name=t('career_observed'),mode='lines+markers',connectgaps=False,
        customdata=[[str((records.get(y) or {}).get('inningsPitched')) if metric=='IP' else str(v) if v is not None else 'N/A',
                     (records.get(y) or {}).get('plateAppearances' if category=='hitting' else 'inningsPitched','N/A')] for y,v in zip(years,values)],
        hovertemplate='%{x}<br>%{customdata[0]}<br>PA / IP: %{customdata[1]}<extra>%{fullData.name}</extra>'))
    if leagues:
        fig.add_scatter(x=years,y=[league_value(leagues.get(y),category,metric) for y in years],name=t('career_league'),
                        mode='lines+markers',connectgaps=False,line=dict(dash='dash'))
    if smooth:
        pooled=rolling(records,category,metric)
        fig.add_scatter(x=years,y=[pooled.get(y) for y in years],name=t('career_smoothed'),mode='lines+markers',connectgaps=False)
    for award in awards:
        year=award.get('season')
        if year in years and values[years.index(year)] is not None:
            fig.add_scatter(x=[year],y=[values[years.index(year)]],mode='markers',marker=dict(symbol='star',size=14,color='#FBBF24'),
                            name=award['name'],showlegend=False,text=[award['name']],hovertemplate='%{x}<br>%{text}<extra></extra>')
    incomplete=[y for y in years if y in career['incomplete'] and values[years.index(y)] is not None]
    if incomplete:
        fig.add_scatter(x=incomplete,y=[values[years.index(y)] for y in incomplete],mode='markers',name=t('career_incomplete'),
                        marker=dict(symbol='circle-open',size=17,color='#FBBF24',line_width=3))
    fig.update_layout(xaxis_title=t('career_season'),yaxis_title=metric,title=metric,hovermode='x unified')
    fig.update_xaxes(dtick=1)
    return style_chart(fig,height=430)


def awards_timeline(awards):
    rows=[a for a in awards if a.get('season') is not None]
    fig=go.Figure(go.Scatter(x=[a['season'] for a in rows],y=[tr(a.get('category') or a['name']) for a in rows],mode='markers',
        marker=dict(symbol='diamond',color='#FBBF24',size=10),
        text=[a['name']+' · '+str(a.get('date') or 'N/A') for a in rows],hovertemplate='%{x}<br>%{text}<extra></extra>'))
    fig.update_layout(xaxis_title=t('career_season'),title=t('career_awards'))
    fig.update_xaxes(dtick=1)
    return style_chart(fig,height=350)


def comparison(players,careers,metric,mode,debuts):
    fig=go.Figure()
    for player,career,debut in zip(players,careers,debuts):
        years=sorted(career['records'])
        fig.add_scatter(x=[career_x(y,debut,mode) for y in years],
                        y=[metric_value(career['records'][y],y,career['category'],metric) for y in years],
                        mode='lines+markers',connectgaps=False,name=player['fullName'],customdata=years,
                        hovertemplate='%{customdata}<br>%{y:.3f}<extra>%{fullData.name}</extra>')
    fig.update_layout(xaxis_title=t('career_experience_axis' if mode=='experience' else 'career_season'),yaxis_title=metric)
    fig.update_xaxes(dtick=1)
    return style_chart(fig,height=430)
