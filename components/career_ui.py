"""Explicit career loading, pooled summaries, descriptive findings and AI context."""
from utils.i18n import st,t
from services.career_stats_service import fetch_career,load_contexts,season_calendar
from services.season_selection import current_date
from services.player_stats import API_ERRORS
from services.player_detection import fetch_profile
from analytics.career_trends import (aggregate,specs,metric_value,changes,peak,development,ai_context,league_value)
from components import career_charts as charts
from components.awards import fetch_awards,category_counts


def load(player,category,prefix):
    identity=(player['id'],category)
    if st.button(t('career_load'),key=prefix+'_load'):
        try:
            with st.spinner(t('career_loading')):
                career=fetch_career(player['id'],category,current_date().isoformat())
                try:
                    profile=fetch_profile(player['id'])
                except API_ERRORS:
                    profile={}
                try:
                    awards=fetch_awards(player['id'])
                except API_ERRORS:
                    awards={'records':[],'error':True}
            st.session_state[prefix+'_data']={'identity':identity,'career':career,'awards':awards,'profile':profile}
        except API_ERRORS:
            st.warning(t('career_fetch_error'))
    stored=st.session_state.get(prefix+'_data')
    return stored if stored and stored['identity']==identity else None


def summary_cards(career,profile):
    totals=career['career_totals']
    debut=str(profile.get('mlbDebutDate') or '')[:4]
    pairs=[(t('career_debut'),debut or 'N/A'),(t('career_latest'),career['last_season']),
           (t('career_seasons'),career['played_seasons']),(t('career_games'),totals.get('gamesPlayed')),
           ('PA' if career['category']=='hitting' else 'IP',totals.get('plateAppearances' if career['category']=='hitting' else 'inningsPitched'))]
    cols=st.columns(5)
    for col,(label,value) in zip(cols,pairs):
        with col.container(border=True):
            st.markdown('**'+label+'**')
            st.markdown('### '+str(value if value is not None else 'N/A'))
    st.caption(t('career_full_scope'))
    st.dataframe([{t('career_metric'):key,t('career_value'):str(value) if value is not None else 'N/A'} for key,value in totals.items()
                  if not key.startswith('_')],hide_index=True)


def panel(player,profile,default_category='hitting'):
    st.subheader(t('career_title'))
    category=st.radio(t('career_category'),['hitting','pitching'],
                      format_func=lambda k:t('career_'+k),index=1 if default_category=='pitching' else 0,
                      horizontal=True,key='career_category_'+str(player['id']))
    stored=load(player,category,'career')
    if not stored:
        return
    career=stored['career']
    if not career['records']:
        st.info(t('career_empty'))
        return
    debut=str((stored.get('profile') or profile).get('mlbDebutDate') or '')[:4]
    if debut.isdigit() and 1800<=int(debut)<min(career['records']):
        career=dict(career,records={y:career['records'].get(y) for y in range(int(debut),max(career['records'])+1)})
    summary_cards(career,profile)
    st.caption(t('career_source',at=career['retrieved_at']))
    st.caption(t('career_rules'))
    if career['problems'] or career['calendar_error']:
        st.warning(t('career_unverified')+' '+str(list(career['problems'])))
    st.caption(t('career_shortened_note'))
    years=sorted(career['records'])
    start,end=st.select_slider(t('career_range'),options=years,value=(years[0],years[-1]),key=f'career_range_{player["id"]}_{category}')
    records={y:career['records'][y] for y in years if start<=y<=end}
    missing=[y for y,r in records.items() if r is None and y not in career['problems']]
    st.caption(t('career_missing')+': '+(', '.join(map(str,missing)) or '—'))
    supplements=st.session_state.get('career_supplements')
    context_id=(player['id'],category,start,end)
    if not supplements or supplements['identity']!=context_id:
        supplements={'identity':context_id,'leagues':{},'statcast':{},'sources':{},'errors':[]}
    league=st.checkbox(t('career_load_league'),key='career_want_league')
    statcast=st.checkbox(t('career_load_statcast'),key='career_want_statcast')
    if st.button(t('career_load_context'),key='career_context_load'):
        progress=st.progress(0.)
        try:
            supplements=dict(load_contexts(list(records),category,player['id'],statcast,league,progress.progress),identity=context_id)
            st.session_state['career_supplements']=supplements
        finally:
            progress.empty()
    if supplements['errors']:
        st.warning(t('career_context_missing'))
    metric_options=list(specs(category))
    if supplements['statcast']:
        metric_options += ['EV','Hard-Hit%','Barrel%','xwOBA'] if category=='hitting' else ['xERA','FB Velocity']
    metric_key=f'career_metric_{player["id"]}_{category}'
    if st.session_state.get(metric_key) not in metric_options:
        st.session_state.pop(metric_key,None)
    metric=st.selectbox(t('career_metric'),metric_options,key=metric_key)
    smooth=st.toggle(t('career_smooth'),key='career_smooth')
    st.caption(t('career_smooth_note'))
    awards=stored['awards'].get('records',[])
    st.plotly_chart(charts.timeline(career,metric,start,end,supplements['leagues'],supplements['statcast'],smooth,awards),key='career_timeline',width='stretch')
    st.subheader(t('career_yoy'))
    differences=changes(records,category,metric,supplements['statcast'])
    st.dataframe([{t('career_previous_season'):r['from'],t('career_current_season'):r['to'],
        t('career_gap'):r['gap_years'],t('career_previous'):r['previous'],t('career_current'):r['current'],
        t('career_difference'):r['difference'],t('career_percentage'):r['percentage_change'],
        t('career_direction'):t('career_direction_'+r['direction']),
        t('career_previous_sample'):r['previous_sample'],t('career_current_sample'):r['current_sample']} for r in differences],hide_index=True)
    st.caption(t('career_yoy_note'))
    findings=development(records,category,supplements['leagues'],career['incomplete'],career['problems'])
    st.subheader(t('career_findings'))
    st.caption(t('career_findings_note'))
    if findings['changes']:
        st.dataframe([{t('career_previous_season'):r['from'],t('career_current_season'):r['to'],
                       t('career_difference'):r['difference'],t('career_direction'):t('career_'+r['finding'])} for r in findings['changes']],hide_index=True)
    else:
        st.info(t('career_insufficient'))
    st.subheader(t('career_breakout'))
    st.caption(t('career_breakout_note'))
    if findings['breakouts']:
        st.dataframe([{t('career_season'):r['season'],t('career_prior_seasons'):', '.join(map(str,r['prior_seasons'])),
                       t('career_relative'):r['relative'],t('career_previous_baseline'):r['prior_relative_mean'],
                       t('career_difference'):r['relative_difference']} for r in findings['breakouts']],hide_index=True)
    else:
        st.info(t('career_no_breakout'))
    peak_metric=st.selectbox(t('career_peak_metric'),[m for m,v in specs(category).items() if v[2]!='context'],key='career_peak_metric_'+category)
    peaks=peak(records,category,peak_metric,career['incomplete'])
    st.subheader(t('career_peak'))
    st.caption(t('career_peak_note'))
    if peaks:
        for p in peaks:
            st.markdown(f"**{p['season']} · {peak_metric}: {p['value']:.3f}**")
            st.write({t('career_sample'):p['record'].get('plateAppearances' if category=='hitting' else 'inningsPitched'),
                      t('career_league'):league_value(supplements['leagues'].get(p['season']),category,peak_metric),
                      t('career_supporting'):{m:metric_value(p['record'],p['season'],category,m) for m in
                        (['OPS','OBP','ISO','BB%','K%'] if category=='hitting' else ['ERA','FIP','WHIP','K-BB%'])},
                      t('career_awards'):[a['name'] for a in awards if a['season']==p['season']]})
    else:
        st.info(t('career_insufficient'))
    with st.expander(t('career_stages')):
        played=sorted(y for y,r in career['records'].items() if r)
        groups=[played[:3],played[3:6],played[6:10],played[10:]]
        st.caption(t('career_stages_note'))
        stage_names=[t('career_stage_'+str(i)) for i in range(4)]
        for name,group in zip(stage_names,groups):
            if group:
                st.markdown('**'+name+' · '+', '.join(map(str,group))+'**')
                pooled=aggregate([career['records'][y] for y in group],category)
                st.write({m:metric_value(pooled,group[-1],category,m) for m in (['AVG','OBP','SLG','OPS'] if category=='hitting' else ['ERA','WHIP','K/9','BB/9'])})
        chosen=st.multiselect(t('career_custom_group'),played,key=f'career_custom_group_{player["id"]}_{category}')
        if chosen:
            st.json(aggregate([career['records'][y] for y in chosen],category))
    st.subheader(t('career_awards'))
    if stored['awards'].get('error'):
        st.info(t('career_awards_error'))
    else:
        st.write(category_counts(awards))
        st.plotly_chart(charts.awards_timeline(awards),key='career_awards_chart',width='stretch')
    if st.session_state.get('ai_enabled'):
        from components import ai_ui
        if ai_ui.ready():
            context=ai_context(player,dict(career,records=records),metric,supplements['leagues'],supplements['statcast'])
            context['verified_awards']=[{k:a.get(k) for k in ('id','name','season','category')} for a in sorted(awards,key=lambda a:a.get('season') or 0,reverse=True)[:100]]
            context['award_summary']=category_counts(awards)
            context['awards_context_truncated']=len(awards)>100
            context['statcast_provenance']=supplements['sources']
            st.subheader(t('career_ai'))
            ai_ui.report(context,t('career_ai_prompt'),'career_ai')
            with st.expander(t('career_chat')):
                ai_ui.chat(context)
    with st.expander(t('career_provenance')):
        st.json({k:v for k,v in career.items() if k!='records'})
        st.json(supplements)


def comparison(players,category=None):
    with st.expander(t('career_comparison')):
        if category is None:
            category=st.radio(t('career_category'),['hitting','pitching'],format_func=lambda k:t('career_'+k),horizontal=True,key='career_compare_category')
        careers=[]
        for i,player in enumerate(players):
            st.markdown('**'+player['fullName']+'**')
            stored=load(player,category,f'career_compare_{i}')
            careers.append(stored)
        if not all(careers) or not all(s['career']['records'] for s in careers):
            return
        data=[s['career'] for s in careers]
        mode=st.radio(t('career_comparison_mode'),['calendar','experience'],format_func=lambda m:t('career_mode_'+m),horizontal=True,key='career_compare_mode')
        metric=st.selectbox(t('career_metric'),list(specs(category)),key='career_compare_metric')
        debuts=[]
        for stored,c in zip(careers,data):
            year=str(stored['profile'].get('mlbDebutDate') or '')[:4]
            debuts.append(int(year) if year.isdigit() and int(year)<=c['first_season'] else c['first_season'])
        st.plotly_chart(charts.comparison(players,data,metric,mode,debuts),key='career_compare_chart',width='stretch')
        st.caption(t('career_comparison_note'))
        for player,stored in zip(players,careers):
            st.write(player['fullName'],stored['career']['career_totals'])
            st.plotly_chart(charts.awards_timeline(stored['awards'].get('records',[])),key=f'career_compare_awards_{player["id"]}',width='stretch')


def clear_cache():
    fetch_career.clear()
    season_calendar.clear()
    for key in list(st.session_state):
        if key=='career_supplements' or key.startswith('career') and key.endswith('_data'):
            del st.session_state[key]
