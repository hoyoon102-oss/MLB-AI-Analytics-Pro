"""Metric-labelled scatter explorer with stable MLBAM IDs in selection payloads."""
import plotly.graph_objects as go
from components.ui_components import style_chart,COLORS
from utils.i18n import t
from analytics.leaderboard_rankings import specs


def scatter(frame,category,x,y,size=None,group='league',selected=None):
    required=[x,y]+([size] if size else [])
    valid=frame.dropna(subset=required)
    fig=go.Figure()
    groups=sorted(valid[group].fillna('N/A').astype(str).unique())
    for i,label in enumerate(groups):
        data=valid[valid[group].fillna('N/A').astype(str)==label]
        sizes=[9]*len(data)
        if size and not data.empty:
            maximum=max(float(valid[size].max()),1)
            sizes=[7+18*(max(float(v),0)/maximum)**.5 for v in data[size]]
        fig.add_scatter(x=data[x].tolist(),y=data[y].tolist(),mode='markers',name=label,
            customdata=[[int(r['id']),r['name']] for _,r in data.iterrows()],
            marker=dict(size=sizes,color=COLORS[i%len(COLORS)],opacity=.7),
            hovertemplate='%{customdata[1]} · MLB ID %{customdata[0]}<br>'+x+': %{x}<br>'+y+': %{y}<extra>%{fullData.name}</extra>')
    highlighted=valid[valid['id']==selected]
    if not highlighted.empty:
        r=highlighted.iloc[0]
        fig.add_scatter(x=[r[x]],y=[r[y]],mode='markers',name=t('lb_selected'),customdata=[[int(r['id']),r['name']]],
                        marker=dict(size=20,symbol='circle-open',color='#FBBF24',line_width=3))
    units=specs(category)
    unit_label=lambda key:t({'rate':'lb_unit_rate','count':'lb_unit_count','decimal IP':'lb_unit_decimal_ip'}[units[key][1]]) if units[key][1] in ('rate','count','decimal IP') else units[key][1]
    fig.update_layout(title=t('lb_scatter')+f' · n={len(valid)}',
                      xaxis_title=f'{x} ({unit_label(x)})',yaxis_title=f'{y} ({unit_label(y)})')
    return style_chart(fig,height=450)
