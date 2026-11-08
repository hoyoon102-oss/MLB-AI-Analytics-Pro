"""Full-season MLB discovery, with explicit loading and preserved custom filters."""
import math
from datetime import datetime,timezone
from utils.i18n import st,t
from services.leaderboard_service import discovery_dataset,clear_discovery_cache,fetch_table
from services.player_stats import API_ERRORS
from analytics.leaderboard_rankings import (build_frame,available_metrics,specs,filter_and_rank,paginate,
                                           export_csv,subset_percentile,ai_context)
from analytics.percentiles import profile
from components.leaderboard_charts import scatter
from components.ui_components import select_player
from components.rankings_ui import open_comparison
from utils.leaderboard_presets import load_presets,save_preset,rename_preset,delete_preset
from services.season_selection import current_date

DEFAULTS={'lb_league':0,'lb_team':0,'lb_position':'ALL','lb_age_enabled':False,'lb_ages':(18,45),
          'lb_min_pa':0,'lb_min_ip':0.,'lb_qualified':True,'lb_role':'all','lb_search':''}
PRESET_KEYS=set(DEFAULTS)|{'lb_season','lb_category','lb_sc','lb_metric','lb_ascending','lb_columns'}|{
    f'lb_t{i}_{suffix}' for i in range(3) for suffix in ('enabled','metric','min_on','min','max_on','max')}


def reset_filters():
    for key in PRESET_KEYS-{'lb_season','lb_category','lb_sc'}:
        st.session_state.pop(key,None)
    for key,value in DEFAULTS.items():
        st.session_state[key]=value
    st.session_state.pop('lb_sort_context',None)


def apply_preset(config):
    reset_filters()
    for key,value in config.items():
        if key in PRESET_KEYS:
            st.session_state[key]=tuple(value) if key=='lb_ages' else value
    # Preserve explicit preset sort direction across first render after applying.
    st.session_state['lb_sort_context']=(st.session_state.get('lb_category','hitting'),st.session_state.get('lb_metric'))
    st.session_state['lb_metric_category']=st.session_state.get('lb_category','hitting')


def _clear_delete_confirmation():
    st.session_state['lb_delete_confirm']=False


def preset_tools():
    with st.expander(t('lb_presets')):
        if st.session_state.get('lb_preset_notice'):
            st.success(st.session_state.pop('lb_preset_notice'))
        try:
            presets=load_presets()
        except (OSError,ValueError,TypeError):
            st.warning(t('lb_presets_error'))
            return
        if st.session_state.get('lb_preset_choice') not in presets:
            st.session_state.pop('lb_preset_choice',None)
        selected=st.selectbox(t('lb_preset_select'),list(presets),index=None,key='lb_preset_choice',on_change=_clear_delete_confirmation)
        if selected:
            st.button(t('lb_preset_apply'),on_click=apply_preset,args=(presets[selected],),key='lb_preset_apply')
        name=st.text_input(t('lb_preset_name'),key='lb_preset_name')
        try:
            if st.button(t('lb_preset_save'),key='lb_preset_save'):
                save_preset(name,{k:st.session_state[k] for k in PRESET_KEYS if k in st.session_state})
                st.session_state['lb_preset_notice']=t('lb_saved')
                st.rerun()
            if selected:
                if st.button(t('lb_preset_rename'),key='lb_preset_rename'):
                    rename_preset(selected,name)
                    st.session_state['lb_preset_notice']=t('lb_saved')
                    st.rerun()
                confirm=st.checkbox(t('lb_delete_confirm'),key='lb_delete_confirm')
                if st.button(t('lb_preset_delete'),key='lb_preset_delete',disabled=not confirm):
                    delete_preset(selected,confirmed=confirm)
                    st.session_state['lb_preset_notice']=t('lb_deleted')
                    st.rerun()
        except (OSError,ValueError,TypeError) as error:
            st.warning(t(str(error)) if str(error).startswith('lb_') else t('lb_presets_error'))


def open_player(person,season,page,category=None):
    st.session_state['selected_season']=season
    if category in ('hitting','pitching'):
        st.session_state['dashboard_stats_category']=category
        st.session_state['dashboard_stats_context']=(person['id'],season)
        st.session_state['career_category_'+str(person['id'])]=category
    select_player(person,page)


def _table_selection():
    event=st.session_state.get('lb_table',{})
    rows=event.get('selection',{}).get('rows',[])
    ids=st.session_state.get('_lb_visible_ids',[])
    picked=[ids[i] for i in rows if 0<=i<len(ids)][:2]
    if picked:
        st.session_state['lb_selected_id']=picked[0]
        st.session_state['lb_compare_ids']=picked


def _plot_selection():
    points=st.session_state.get('lb_plot',{}).get('selection',{}).get('points',[])
    if points and points[-1].get('customdata'):
        pid=int(points[-1]['customdata'][0])
        if pid in st.session_state.get('_lb_result_ids',[]):
            st.session_state['lb_selected_id']=pid


def col_label(key):
    return t('lb_col_'+key) if key in ('rank','id','name','teams','position','age','G','PA','IP_display') else 'IP (outs/3)' if key=='IP' else key


def filters_ui(frame,category,metrics):
    for key,value in DEFAULTS.items():
        st.session_state.setdefault(key,value)
    with st.expander(t('lb_filters'),expanded=True):
        st.button(t('lb_reset'),on_click=reset_filters,key='lb_reset')
        a,b,c=st.columns(3)
        league=a.selectbox(t('lb_league'),[0,103,104],format_func=lambda v:t('lb_all_mlb',locale='ko') if not v else 'AL' if v==103 else 'NL',key='lb_league')
        teams={tid:name for _,r in frame.iterrows() for tid in r['team_ids'] for name in [st.session_state['_lb_teams'][tid]['name']]}
        if st.session_state.get('lb_team') not in [0,*teams]:
            st.session_state['lb_team']=0
        team=b.selectbox(t('lb_team'),[0,*sorted(teams,key=teams.get)],format_func=lambda v:t('lb_all_teams',locale='ko') if not v else teams[v],key='lb_team')
        positions=['ALL',*sorted(set(frame['position'].dropna())|{'OF'})]
        if st.session_state.get('lb_position') not in positions:
            st.session_state['lb_position']='ALL'
        position=c.selectbox(t('lb_position'),positions,format_func=lambda v:t('lb_all_positions',locale='ko') if v=='ALL' else v,key='lb_position')
        a,b,c=st.columns(3)
        qualified=a.checkbox(t('lb_qualified'),key='lb_qualified')
        if category=='hitting':
            minimum=b.number_input(t('lb_min_pa'),min_value=0,step=25,key='lb_min_pa')
        else:
            minimum=b.number_input(t('lb_min_ip'),min_value=0.,step=5.,key='lb_min_ip')
        role=c.selectbox(t('lb_role'),['all','starter','reliever'],format_func=lambda k:t('lb_role_'+k,locale='ko'),key='lb_role') if category=='pitching' else 'all'
        age_on=st.checkbox(t('lb_age_filter'),key='lb_age_enabled')
        ages=st.slider(t('lb_age_range'),0,100,key='lb_ages') if age_on else (0,100)
        st.caption(t('lb_age_note'))
        search=st.text_input(t('lb_search'),key='lb_search')
        thresholds=[]
        for i in range(3):
            enabled=st.checkbox(t('lb_threshold',n=i+1),key=f'lb_t{i}_enabled')
            if enabled:
                a,b,c,d,e=st.columns([3,1,2,1,2])
                key=f'lb_t{i}_metric'
                if st.session_state.get(key) not in metrics:
                    st.session_state.pop(key,None)
                metric=a.selectbox(t('lb_metric'),metrics,key=key)
                low_on=b.checkbox(t('lb_min'),key=f'lb_t{i}_min_on')
                low=c.number_input(t('lb_min_value'),value=0.,key=f'lb_t{i}_min')
                high_on=d.checkbox(t('lb_max'),key=f'lb_t{i}_max_on')
                high=e.number_input(t('lb_max_value'),value=0.,key=f'lb_t{i}_max')
                thresholds.append({'metric':metric,'min':low if low_on else None,'max':high if high_on else None})
        st.caption(t('lb_membership_note'))
    return {'qualified':qualified,'league':league,'team':team,'position':position,'ages':list(ages),
            'min_pa':minimum if category=='hitting' else 0,'min_ip':minimum if category=='pitching' else 0,
            'role':role,'search':search,'thresholds':thresholds}


def page(change_favorite,resolve_seasons):
    st.subheader(t('lb_title'))
    preset_tools()
    seasons=resolve_seasons(current_date().isoformat())
    if seasons.get('warning'):
        st.info(seasons['warning'])
    years=seasons['years']
    if st.session_state.get('lb_season') not in years:
        st.session_state['lb_season']=seasons['latest']
    a,b=st.columns(2)
    season=a.selectbox(t('lb_season'),years,key='lb_season')
    category=b.radio(t('lb_category'),['hitting','pitching'],format_func=lambda k:t('lb_'+k,locale='ko'),horizontal=True,key='lb_category')
    include=st.checkbox(t('lb_statcast'),key='lb_sc')
    if st.button(t('lb_load'),key='lb_load'):
        try:
            with st.spinner(t('lb_loading')):
                dataset=discovery_dataset(season,category,include)
                frame=build_frame(dataset)
                st.session_state['lb_loaded']={'identity':(season,category,include),'dataset':dataset,'frame':frame}
        except API_ERRORS:
            st.warning(t('lb_fetch_error'))
    stored=st.session_state.get('lb_loaded')
    if not stored or stored['identity']!=(season,category,include):
        st.info(t('lb_load_note'))
        return
    dataset,frame=stored['dataset'],stored['frame']
    st.session_state['_lb_teams']=dataset['teams']
    policy=t('lb_cache_historical' if dataset['cache_policy']=='historical_24h' else 'lb_cache_current')
    st.caption(t('lb_source',at=dataset['retrieved_at'],policy=policy,n=dataset['population_n']))
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(dataset['retrieved_at'])).total_seconds()
        if age>(86400 if dataset['cache_policy']=='historical_24h' else 900):
            st.warning(t('lb_stale'))
    except (ValueError,TypeError):
        pass
    if dataset['errors']:
        st.warning(t('lb_partial'))
    if frame.empty:
        st.info(t('lb_empty'))
        return
    metrics=available_metrics(frame,category)
    if not metrics:
        st.info(t('lb_empty'))
        return
    filters=filters_ui(frame,category,metrics)
    default='OPS' if category=='hitting' else 'ERA'
    if st.session_state.get('lb_metric') not in metrics or st.session_state.get('lb_metric_category')!=category:
        st.session_state['lb_metric']=default if default in metrics else metrics[0]
        st.session_state['lb_metric_category']=category
    metric=st.selectbox(t('lb_metric'),metrics,key='lb_metric')
    if st.session_state.get('lb_sort_context')!=(category,metric):
        st.session_state['lb_ascending']=specs(category)[metric][2]=='asc'
        st.session_state['lb_sort_context']=(category,metric)
    ascending=st.checkbox(t('lb_ascending'),key='lb_ascending')
    try:
        ranked=filter_and_rank(frame,category,filters,metric,ascending)
    except ValueError as error:
        st.warning(t(str(error)))
        return
    st.caption(t('lb_eligible',n=len(ranked),qualified=len(dataset['qualified_ids'])))
    st.caption(t('lb_method'))
    if ranked.empty:
        st.info(t('lb_empty'))
        return
    default_cols=[metric]+[k for k in ('OPS','HR','BB%','K%') if k in metrics and k!=metric] if category=='hitting' else [metric]+[k for k in ('WHIP','SO','FIP','K/9') if k in metrics and k!=metric]
    if 'lb_columns' in st.session_state:
        st.session_state['lb_columns']=[k for k in st.session_state['lb_columns'] if k in metrics]
    else:
        st.session_state['lb_columns']=default_cols
    columns=st.multiselect(t('lb_columns'),metrics,key='lb_columns')
    a,b=st.columns(2)
    limit=a.selectbox(t('lb_show'),[10,25,50,100,'all'],index=1,format_func=lambda v:t('lb_all_eligible',locale='ko') if v=='all' else f'Top {v}',key='lb_limit')
    size=b.selectbox(t('lb_page_size'),[10,25,50],index=1,key='lb_page_size')
    scope=ranked if limit=='all' else ranked.head(limit)
    pages=max(1,math.ceil(len(scope)/size))
    if st.session_state.get('lb_page',1)>pages:
        st.session_state['lb_page']=1
    index=st.number_input(t('lb_page'),min_value=1,max_value=pages,step=1,key='lb_page')
    shown=paginate(scope,size,index)
    keys=list(dict.fromkeys(['rank','id','name','teams','position','age','G','PA' if category=='hitting' else 'IP_display',metric,*columns]))
    table=shown[keys].rename(columns={k:col_label(k) for k in keys})
    st.session_state['_lb_visible_ids']=shown['id'].tolist()
    st.session_state['_lb_result_ids']=ranked['id'].tolist()
    column_config={}
    for key in keys:
        if key in specs(category):
            unit=specs(category)[key][1]
            precision='%.0f' if unit=='count' else '%.3f' if key in ('AVG','OBP','SLG','OPS','wOBA','ISO','BABIP','xBA','xSLG','xwOBA','IP') else '%.2f'
            column_config[col_label(key)]=st.column_config.NumberColumn(col_label(key),format=precision)
    st.dataframe(table,hide_index=True,width='stretch',column_config=column_config,
                 on_select=_table_selection,selection_mode='multi-row',key='lb_table')
    st.caption(t('lb_table_sort_note'))
    st.download_button(t('lb_download'),export_csv(ranked,[metric,*columns],dataset,filters,metric),
                       file_name=f'MLB_{season}_{category}_{metric.replace("/","-")}.csv',mime='text/csv',key='lb_export')
    players={int(r['id']):{'id':int(r['id']),'fullName':r['name']} for _,r in ranked.iterrows()}
    if st.session_state.get('lb_selected_id') not in players:
        st.session_state.pop('lb_selected_id',None)
    selected=st.selectbox(t('lb_select_player'),list(players),format_func=lambda pid:players[pid]['fullName']+f' · {pid}',key='lb_selected_id')
    person=players[selected]
    a,b,c,d=st.columns(4)
    for col,label,target in [(a,'lb_open','선수 기록'),(b,'lb_open_statcast','Statcast 분석'),(c,'career_open','커리어 분석')]:
        col.button(t(label),key='lb_nav_'+target,on_click=open_player,args=(person,season,target,category))
    d.button(t('lb_favorite'),key='lb_favorite',on_click=change_favorite,args=(person,))
    if 'lb_compare_ids' in st.session_state:
        st.session_state['lb_compare_ids']=[pid for pid in st.session_state['lb_compare_ids'] if pid in players][:2]
    compare=st.multiselect(t('lb_compare_select'),list(players),format_func=lambda pid:players[pid]['fullName'],max_selections=2,key='lb_compare_ids')
    if len(compare)==2:
        st.button(t('rank_compare'),key='lb_compare',on_click=open_comparison,args=(players[compare[0]],players[compare[1]],season,category))
    with st.expander(t('lb_scatter')):
        bubble_metrics=[m for m in metrics if (ranked[m].dropna()>=0).all()]
        for key,options in [('lb_x',metrics),('lb_y',metrics),('lb_bubble',['NONE',*bubble_metrics])]:
            if st.session_state.get(key) not in options:
                st.session_state.pop(key,None)
        x=st.selectbox(t('lb_x'),metrics,key='lb_x')
        y=st.selectbox(t('lb_y'),metrics,index=min(1,len(metrics)-1),key='lb_y')
        bubble=st.selectbox(t('lb_bubble'),['NONE',*bubble_metrics],format_func=lambda k:t('lb_no_bubble',locale='ko') if k=='NONE' else k,key='lb_bubble')
        grouping=st.selectbox(t('lb_color'),['league','teams','position'],format_func=lambda k:t('lb_group_'+k,locale='ko'),key='lb_color')
        st.plotly_chart(scatter(ranked,category,x,y,None if bubble=='NONE' else bubble,grouping,selected),
                        key='lb_plot',on_select=_plot_selection,width='stretch')
        st.caption(t('lb_scatter_note'))
    with st.expander(t('lb_percentiles')):
        st.caption(t('lb_subset_percentile',n=len(ranked),value=subset_percentile(ranked,selected,metric,ascending)))
        if st.button(t('lb_official_percentiles'),key='lb_official_percentiles'):
            try:
                official=fetch_table(season,category,'percentiles')
                data=profile({'season':season,'category':category,'game_type':'R','official':official,
                              'raw':dataset.get('supplemental'),'contact':None},selected)
                st.session_state['lb_percentiles_data']={'identity':(season,category,selected),'profile':data}
            except API_ERRORS:
                st.warning(t('lb_percentile_error'))
        data=st.session_state.get('lb_percentiles_data')
        if data and data['identity']==(season,category,selected):
            st.caption(t('lb_official_population_note'))
            st.dataframe([{t('lb_metric'):t('rank_metric_'+k),t('lb_percentile'):v['percentile'],
                           t('lb_population_n'):v['population_n']} for k,v in data['profile']['metrics'].items()],hide_index=True)
    if st.session_state.get('ai_enabled'):
        from components import ai_ui
        if ai_ui.ready():
            context=ai_context(ranked,dataset,filters,metric,ascending,selected,columns)
            st.subheader(t('lb_ai'))
            ai_ui.report(context,t('lb_ai_prompt'),'lb_ai')
            # This UI reuses chat identity with the selected player; rankings retain full scope.
            context=dict(context,player={'id':selected,'name':person['fullName']})
            with st.expander(t('lb_chat')):
                ai_ui.chat(context)
    with st.expander(t('lb_sources')):
        metadata={k:v for k,v in dataset.items() if k not in ('rows','memberships','supplemental','qualification_source')}
        metadata['qualification_source']={k:v for k,v in dataset.get('qualification_source',{}).items() if k!='rows'}
        st.json(metadata)
        st.json({'filters':filters,'metric':metric,'ascending':ascending,
                 'statcast_source':(dataset.get('supplemental') or {}).get('source'),
                 'statcast_retrieved_at':(dataset.get('supplemental') or {}).get('retrieved_at')})
        st.caption(t('lb_unavailable'))


def clear_cache():
    clear_discovery_cache()
    st.session_state.pop('lb_loaded',None)
