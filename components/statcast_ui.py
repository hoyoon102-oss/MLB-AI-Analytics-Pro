"""Explicit opt-in Statcast requests; failures leave the standard dashboard intact."""
from datetime import date
import requests
import plotly.graph_objects as go
from utils.i18n import st, t
from services.season_selection import current_date
from services.statcast_service import (StatcastError, fetch_period, published_player, fetch_chunk, published_table)
from analytics.statcast_hitting import hitting_summary, published_metrics
from analytics.statcast_pitching import pitching_summary, arsenal
from analytics.statcast_context import summary, ai_context
from components import statcast_charts as charts
from components.ui_components import style_chart

PITCH_DESCRIPTIONS = {'FF':'sc_pitch_ff','SI':'sc_pitch_si','FC':'sc_pitch_fc','SL':'sc_pitch_sl',
                      'ST':'sc_pitch_st','CU':'sc_pitch_cu','KC':'sc_pitch_cu','CH':'sc_pitch_ch','FS':'sc_pitch_fs'}


def display(value, unit=''):
    return 'N/A' if value is None else (f'{value:.3f}' if unit == 'rate' else f'{value:.2f}') + (' '+unit if unit not in ('rate','ERA','') else '')


def cards(metrics, season):
    columns = st.columns(3)
    for index,(key,item) in enumerate(metrics.items()):
        with columns[index%3].container(border=True):
            st.markdown('**'+t('sc_'+key)+'**',help=t('sc_help_'+key))
            st.markdown('### '+display(item['value'],item['unit']))
            st.caption(str(season)+' · '+t('sc_n')+' '+str(item['n'] if item['n'] is not None else 'N/A'))
            st.caption(t('sc_league_na'))
            st.caption('Baseball Savant · '+t('sc_published' if item['classification'] == 'source_published' else 'sc_local'))
            with st.expander(t('sc_method')):
                st.write(item)


def load(player, season, category, prefix):
    if season < 2015 or season > current_date().year:
        st.info(t('sc_coverage'))
        return None
    first,last = date(season,1,1),min(date(season,12,31),current_date())
    left,right = st.columns(2)
    # Identity-specific widget keys prevent dates from another season leaking into requests.
    scope = f'{prefix}_{player["id"]}_{season}_{category}'
    start = left.date_input(t('sc_start'),value=first,min_value=first,max_value=last,key=scope+'_start')
    end = right.date_input(t('sc_end'),value=last,min_value=first,max_value=last,key=scope+'_end')
    identity = (player['id'],season,category,start.isoformat(),end.isoformat())
    key = prefix+'_loaded'
    stored = st.session_state.get(key)
    if stored and stored['identity'] != identity:
        stored = None
    st.caption(t('sc_load_note'))
    if st.button(t('sc_load'),key=scope+'_load'):
        if start > end:
            st.error(t('sc_dates_error'))
            return None
        with st.spinner(t('sc_loading')):
            published = published_player(season,category,player['id'])
            progress = st.progress(0.)
            try:
                dataset = fetch_period(player['id'],season,category,start.isoformat(),end.isoformat(),progress.progress)
            except (StatcastError,requests.RequestException,ValueError,UnicodeError) as error:
                st.warning(t(str(error)) if str(error).startswith('sc_') else t('sc_network_error'))
                dataset = {'player_id':player['id'],'season':season,'category':category,'game_type':'R',
                           'start':start.isoformat(),'end':end.isoformat(),'rows':[],'sources':[],
                           'quality':{},'retrieved_at':None,'error':str(error)}
            finally:
                progress.empty()
            stored = {'identity':identity,'dataset':dataset,'published':published}
            st.session_state[key] = stored
    return stored


def hitting_charts(dataset, prefix):
    rows = dataset['rows']
    st.subheader(t('sc_observed'))
    observed = hitting_summary(rows)
    st.caption(t('sc_bbe_count',pitches=observed['pitches'],bbe=observed['bbe']))
    cards(observed['metrics'],dataset['season'])
    st.plotly_chart(charts.exit_histogram(rows),key=prefix+'_hist',width='stretch')
    st.plotly_chart(charts.exit_scatter(rows),key=prefix+'_evla',width='stretch')
    metric = st.selectbox(t('sc_month_metric'),['avg_ev','hard_hit','barrel'],format_func=lambda v:t('sc_'+v),key=prefix+'_monthmetric')
    st.plotly_chart(charts.monthly_chart(rows,metric,dataset['start'],dataset['end']),key=prefix+'_months',width='stretch')
    st.plotly_chart(charts.breakdown(rows),key=prefix+'_breakdown',width='stretch')
    options = sorted({r.get('events') for r in rows if r.get('type') == 'X' and r.get('events')})
    event = st.selectbox(t('sc_event'),['ALL',*options],format_func=lambda v:t('sc_all') if v == 'ALL' else v,key=prefix+'_event')
    fig = charts.spray(rows,None if event == 'ALL' else event)
    if fig is None:
        st.info(t('sc_no_locations'))
    else:
        st.plotly_chart(fig,key=prefix+'_spray',width='stretch')
        st.caption(t('sc_spray_note'))


def arsenal_table(data):
    output = []
    for row in data:
        result = {t('sc_pitch'):row['pitch_name']+' · '+t(PITCH_DESCRIPTIONS.get(row['pitch_type'],'sc_pitch_other')),
                  t('sc_count'):row['pitches'],t('sc_usage'):display(row['usage']['value'],'%')}
        for key,item in row['metrics'].items():
            result[t('sc_'+key)] = display(item['value'],item['unit'])
            result[t('sc_'+key)+' n'] = item['n']
        output.append(result)
    return output


def pitching_charts(dataset,prefix):
    rows = dataset['rows']
    observed = pitching_summary(rows)
    st.subheader(t('sc_observed'))
    st.caption(t('sc_pitches_count',n=len(rows)))
    cards(observed['metrics'],dataset['season'])
    data = arsenal(rows)
    st.dataframe(arsenal_table(data),hide_index=True,width='stretch')
    codes = [r['pitch_type'] for r in data]
    selected = st.multiselect(t('sc_pitch_filter'),codes,default=codes,key=prefix+'_pitches')
    normalized = st.toggle(t('sc_normalized'),value=True,key=prefix+'_normalized')
    density = st.toggle(t('sc_density'),key=prefix+'_density')
    st.caption(t('sc_location_note'))
    st.caption(t('sc_location_2026') if dataset['season'] >= 2026 else t('sc_location_2025'))
    st.plotly_chart(charts.locations(rows,selected,normalized,density),key=prefix+'_locations',width='stretch')
    st.caption(t('sc_density_note'))
    st.plotly_chart(charts.movement(rows,selected),key=prefix+'_movement',width='stretch')
    st.caption(t('sc_movement_note'))


def ai_section(player, stored, previous, prefix):
    from components import ai_ui
    st.subheader(t('sc_ai'))
    if not st.session_state.get('ai_enabled') or not ai_ui.ready():
        st.info(t('sc_ai_enable'))
        return
    context = ai_context(player,stored['dataset'],stored['published'],previous)
    with st.expander(t('sc_ai_context')):
        st.json(context)
    report_tab,chat_tab = st.tabs([t('sc_ai'),'AI에게 질문'])
    with report_tab:
        ai_ui.report(context,t('sc_ai_prompt'),prefix+'_ai')
    with chat_tab:
        ai_ui.chat(context)


def panel(player, season, category, prefix='statcast'):
    st.subheader(t('sc_hitting' if category == 'hitting' else 'sc_pitching'))
    st.caption(t('sc_limitations'))
    stored = load(player,season,category,prefix)
    if not stored:
        return
    dataset,published = stored['dataset'],stored['published']
    st.subheader(t('sc_full_season'))
    cards(published_metrics(published),season)
    if published.get('errors'):
        st.info(t('sc_published_missing'))
    st.caption(t('sc_range',start=dataset['start'],end=dataset['end'],at=dataset['retrieved_at'] or 'N/A'))
    if dataset.get('error'):
        st.warning(t('sc_partial_error'))
    elif not dataset['rows']:
        st.info(t('sc_empty'))
    else:
        (hitting_charts if category == 'hitting' else pitching_charts)(dataset,prefix)
    previous = None
    if season > 2015:
        with st.expander(t('sc_previous')):
            year = st.selectbox(t('sc_previous_year'),list(range(2015,season)),index=season-2016,key=prefix+'_previous_year')
            previous_stored = load(player,year,category,prefix+'_previous')
            if previous_stored:
                previous = summary(previous_stored['dataset'],previous_stored['published'])
                current = summary(dataset,published)
                st.dataframe([{
                    t('sc_metric'):t('sc_'+key),str(season):display(item['value'],item['unit']),
                    str(season)+' n':item['n'],str(year):display(previous['observed']['metrics'][key]['value'],item['unit']),
                    str(year)+' n':previous['observed']['metrics'][key]['n'],
                    t('sc_difference'):item['value']-previous['observed']['metrics'][key]['value']
                    if item['value'] is not None and previous['observed']['metrics'][key]['value'] is not None else None}
                    for key,item in current['observed']['metrics'].items()],hide_index=True)
                st.caption(t('sc_period_warning'))
    if dataset['rows'] or any(item['value'] is not None for item in published_metrics(published).values()):
        ai_section(player,stored,previous,prefix)
    with st.expander(t('sc_sources')):
        st.json({'request':{k:v for k,v in dataset.items() if k != 'rows'},'published':published})
        st.markdown('[Baseball Savant CSV](https://baseballsavant.mlb.com/csv-docs)')


def comparison(players, season, category):
    with st.expander(t('sc_comparison')):
        st.caption(t('sc_period_warning'))
        stored = []
        for index,(column,player) in enumerate(zip(st.columns(2),players)):
            with column:
                st.markdown('**'+player['fullName']+'**')
                stored.append(load(player,season,category,f'sc_compare_{index}'))
        if not all(stored):
            return
        datasets = [s['dataset'] for s in stored]
        if (datasets[0]['start'],datasets[0]['end']) != (datasets[1]['start'],datasets[1]['end']):
            st.info(t('sc_period_mismatch'))
            return
        if any(d.get('error') for d in datasets):
            st.warning(t('sc_partial_error'))
            return
        groups = [(hitting_summary if category == 'hitting' else pitching_summary)(d['rows'])['metrics'] for d in datasets]
        if category == 'hitting':
            scope = st.radio(t('sc_scope'),['observed','published'],format_func=lambda v:t('sc_observed' if v == 'observed' else 'sc_full_season'),key='sc_compare_scope')
            if scope == 'published':
                groups = [published_metrics(s['published']) for s in stored]
        else:
            all_codes = sorted({r['pitch_type'] for d in datasets for r in arsenal(d['rows'])})
            code = st.selectbox(t('sc_pitch_filter'),['ALL',*all_codes],key='sc_compare_pitch',format_func=lambda v:t('sc_all') if v == 'ALL' else v)
            subsets = [d['rows'] if code == 'ALL' else [r for r in d['rows'] if (r.get('pitch_type') or 'UN') == code] for d in datasets]
            groups = [pitching_summary(r)['metrics'] for r in subsets]
            for g,sub,d in zip(groups,subsets,datasets):
                g['usage'] = {'value':len(sub)/len(d['rows'])*100 if d['rows'] else None,'n':len(d['rows']),'unit':'%'}
            st.caption(t('sc_arsenal_compare_note'))
        for column,player,group in zip(st.columns(2),players,groups):
            with column:
                st.markdown('**'+player['fullName']+'**')
                for key,item in group.items():
                    st.caption(t('sc_'+key)+': '+display(item['value'],item['unit'])+' · n='+str(item['n']))
        metric = st.selectbox(t('sc_metric'),list(groups[0]),format_func=lambda k:t('sc_'+k),key='sc_compare_metric')
        a,b = groups[0][metric],groups[1][metric]
        fig = go.Figure()
        for player,item in zip(players,(a,b)):
            fig.add_bar(name=player['fullName'],x=[t('sc_'+metric)],y=[item['value']])
        st.plotly_chart(style_chart(fig,height=360),key='sc_compare_chart',width='stretch')
        st.caption(t('sc_difference')+': '+display(a['value']-b['value'] if a['value'] is not None and b['value'] is not None else None,a['unit']))
        with st.expander(t('sc_sources')):
            st.json([summary(s['dataset'],s['published']) for s in stored])
        if st.session_state.get('ai_enabled'):
            from components import ai_ui
            if ai_ui.ready():
                contexts = [ai_context(player,s['dataset'],s['published']) for player,s in zip(players,stored)]
                context = {'players':contexts,'mode':'Statcast comparison',
                           'compared_statistics':groups,
                           'difference_first_minus_second':{key:groups[0][key]['value']-groups[1][key]['value']
                               for key in groups[0] if groups[0][key]['value'] is not None and groups[1][key]['value'] is not None},
                           'comparison_scope':{'metric_scope':scope if category == 'hitting' else code,
                                               'observed_date_ranges':[(d['start'],d['end']) for d in datasets]}}
                ai_ui.report(context,t('sc_ai_prompt'),'sc_compare_ai')


def clear_cache():
    fetch_chunk.clear()
    published_table.clear()
    for key in list(st.session_state):
        if key.endswith('_loaded') and (key.startswith('statcast') or key.startswith('sc_compare')):
            del st.session_state[key]
