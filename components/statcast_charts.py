"""Statcast Plotly charts; measured coordinates only, no imputed locations."""
import hashlib
from datetime import date
import plotly.graph_objects as go
from analytics.statcast_hitting import batted, number, monthly_summary
from components.ui_components import style_chart
from utils.i18n import t

PALETTE = ['#60A5FA','#FBBF24','#2DD4BF','#C4B5FD','#FB7185','#FB923C','#A3E635','#E879F9','#94A3B8']
COLORS = dict(zip(('FF','SI','FC','SL','ST','CU','CH','FS','UN'),PALETTE))


def color(code):
    return COLORS.get(code, PALETTE[int(hashlib.sha256(code.encode()).hexdigest()[:8],16)%len(PALETTE)])


def chart(fig, title, x, y):
    fig.update_layout(title=title,xaxis_title=x,yaxis_title=y)
    return style_chart(fig,height=400)


def exit_histogram(rows):
    speeds = [v for r in batted(rows) if (v := number(r.get('launch_speed'))) is not None]
    fig = go.Figure(go.Histogram(x=speeds,marker_color='#60A5FA',nbinsx=24))
    return chart(fig,t('sc_hist')+f' · n={len(speeds)}',t('sc_ev_axis'),t('sc_count'))


def exit_scatter(rows):
    fig = go.Figure()
    total = 0
    groups = sorted({r.get('events') or 'unknown' for r in batted(rows)})
    for event in groups:
        subset = [r for r in batted(rows) if (r.get('events') or 'unknown') == event
                  and number(r.get('launch_speed')) is not None and number(r.get('launch_angle')) is not None]
        total += len(subset)
        fig.add_scatter(x=[number(r['launch_speed']) for r in subset],y=[number(r['launch_angle']) for r in subset],
                        mode='markers',name=event,text=[r['game_date'] for r in subset],
                        hovertemplate='%{text}<br>%{x:.1f} mph · %{y:.1f}°<extra>%{fullData.name}</extra>')
    return chart(fig,t('sc_ev_la')+f' · n={total}',t('sc_ev_axis'),t('sc_la_axis'))


def monthly_chart(rows, metric, start=None, end=None):
    summaries = monthly_summary(rows)
    months = sorted(summaries)
    if start and end:
        months = []
        cursor = date.fromisoformat(start).replace(day=1)
        last = date.fromisoformat(end).replace(day=1)
        while cursor <= last:
            months.append(cursor.strftime('%Y-%m'))
            cursor = date(cursor.year+1,1,1) if cursor.month == 12 else date(cursor.year,cursor.month+1,1)
    v = [summaries[m]['metrics'][metric] if m in summaries else {'value':None,'n':0} for m in months]
    fig = go.Figure(go.Scatter(x=months,y=[r['value'] for r in v],customdata=[r['n'] for r in v],
                             mode='lines+markers',connectgaps=False,
                             hovertemplate='%{x}<br>%{y:.2f}<br>n=%{customdata}<extra></extra>'))
    return chart(fig,t('sc_monthly'),t('sc_month'),t('sc_'+metric))


def breakdown(rows):
    data = monthly_summary(rows)
    counts = {}
    for summary in data.values():
        for key,n in summary['breakdown'].items():
            counts[key] = counts.get(key,0)+n
    fig = go.Figure(go.Bar(x=[t('sc_bb_'+k) for k in counts],y=list(counts.values()),marker_color='#60A5FA'))
    return chart(fig,t('sc_breakdown'),t('sc_batted_type'),t('sc_count'))


def spray_point(row):
    x,y = number(row.get('hc_x')),number(row.get('hc_y'))
    # Match MLBAM diagram convention used by pybaseball plotting. No feet conversion.
    return (x-125,199-y) if x is not None and y is not None and x > 0 and y > 0 else None


def spray(rows, event=None):
    selected = [r for r in batted(rows) if (event is None or r.get('events') == event) and spray_point(r) is not None]
    if not selected:
        return None
    fig = go.Figure()
    # A schematic diamond and foul lines, not a real stadium boundary or distance scale.
    fig.add_scatter(x=[-150,0,150],y=[150,0,150],mode='lines',line_color='#94A3B8',showlegend=False,hoverinfo='skip')
    fig.add_scatter(x=[0,25,0,-25,0],y=[0,25,50,25,0],mode='lines',line_color='#94A3B8',showlegend=False,hoverinfo='skip')
    fig.add_scatter(x=[spray_point(r)[0] for r in selected],y=[spray_point(r)[1] for r in selected],
                    mode='markers',marker=dict(color='#60A5FA',size=8),
                    text=[r['game_date']+' · '+(r.get('events') or '') for r in selected],
                    hovertemplate='%{text}<br>hc offset (%{x:.1f}, %{y:.1f})<extra></extra>',showlegend=False)
    fig.update_yaxes(scaleanchor='x',scaleratio=1)
    return chart(fig,t('sc_spray')+f' · n={len(selected)}',t('sc_diagram_x'),t('sc_diagram_y'))


def location_point(row, normalized=False):
    x,z = number(row.get('plate_x')),number(row.get('plate_z'))
    if x is None or z is None:
        return None
    if not normalized:
        return x,z
    bottom,top = number(row.get('sz_bot')),number(row.get('sz_top'))
    return (x,(z-bottom)/(top-bottom)) if bottom is not None and top is not None and top > bottom else None


def locations(rows, selected, normalized, density):
    subset = [r for r in rows if (r.get('pitch_type') or 'UN') in selected and location_point(r,normalized) is not None]
    fig = go.Figure()
    if density and len(subset) >= 50:
        points = [location_point(r,normalized) for r in subset]
        fig.add_trace(go.Histogram2d(x=[p[0] for p in points],y=[p[1] for p in points],nbinsx=20,nbinsy=20,colorscale='Blues',showscale=False))
    else:
        for code in selected:
            group = [r for r in subset if (r.get('pitch_type') or 'UN') == code]
            points = [location_point(r,normalized) for r in group]
            fig.add_scatter(x=[p[0] for p in points],y=[p[1] for p in points],name=code,mode='markers',
                            marker=dict(color=color(code),size=6,opacity=.65),
                            text=[r['game_date']+' · '+(r.get('description') or '') for r in group],
                            hovertemplate='%{text}<br>x=%{x:.2f}, z=%{y:.2f}<extra>%{fullData.name}</extra>')
    if normalized:
        fig.add_shape(type='rect',x0=-17/24,x1=17/24,y0=0,y1=1,line_color='#FBBF24')
    else:
        # Overlay individual measured zones, rather than assume one universal zone.
        zones = {(number(r.get('sz_bot')),number(r.get('sz_top'))) for r in subset}
        for bottom,top in zones:
            if bottom is not None and top is not None and top > bottom:
                fig.add_shape(type='rect',x0=-17/24,x1=17/24,y0=bottom,y1=top,line=dict(color='rgba(251,191,36,0.15)',width=1))
    return chart(fig,t('sc_locations')+f' · n={len(subset)}',t('sc_plate_x'),t('sc_zone_relative') if normalized else t('sc_plate_z'))


def movement(rows, selected):
    fig = go.Figure()
    for code in selected:
        subset = [r for r in rows if (r.get('pitch_type') or 'UN') == code and number(r.get('pfx_x')) is not None and number(r.get('pfx_z')) is not None]
        fig.add_scatter(x=[number(r['pfx_x'])*12 for r in subset],y=[number(r['pfx_z'])*12 for r in subset],
                        mode='markers',name=code,marker=dict(color=color(code),size=6,opacity=.6),
                        text=[r['game_date'] for r in subset],hovertemplate='%{text}<br>%{x:.2f} in · %{y:.2f} in<extra>%{fullData.name}</extra>')
    fig.add_hline(y=0,line_color='#94A3B8')
    fig.add_vline(x=0,line_color='#94A3B8')
    return chart(fig,t('sc_movement'),t('sc_pfx_x'),t('sc_pfx_z'))
