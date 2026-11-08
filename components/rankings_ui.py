"""Opt-in percentile and similarity tools integrated with existing player state."""
import plotly.graph_objects as go
from utils.i18n import st,t
from services.leaderboard_service import load_boards,clear_cache as clear_source_cache
from analytics.percentiles import profile
from analytics.player_similarity import similar_players,ai_context,FEATURES
from components.ui_components import style_chart,select_player


def formatted(value,unit=''):
    return 'N/A' if value is None else f'{value:.3f}' if unit=='rate' else f'{value:.2f}'+(' '+unit if unit else '')


def open_comparison(target,candidate,season,category):
    """Reuse comparison identities and clear widgets that could select another player."""
    st.session_state['selected_season']=season
    for i,person in enumerate((target,candidate)):
        prefix=f'compare_{i}'
        for suffix in ('favorite_choice','result','auto','selected','context'):
            st.session_state.pop(prefix+'_'+suffix,None)
        st.session_state[prefix+'_chosen']=dict(person)
        st.session_state[prefix+'_mode']='즐겨찾기'
        st.session_state[prefix+'_stats_category']=category
        st.session_state[prefix+'_stats_context']=(person['id'],season)
    st.session_state['pro_page']='선수 비교'


def open_statistics(person,season):
    st.session_state['selected_season']=season
    select_player(person)


def percentile_chart(data):
    available=[(k,m) for k,m in data['metrics'].items() if m['percentile'] is not None]
    fig=go.Figure(go.Bar(x=[m['percentile'] for _,m in available],y=[t('rank_metric_'+k) for k,_ in available],
        orientation='h',marker_color=['#60A5FA' if m['percentile']>=50 else '#FBBF24' for _,m in available],
        customdata=[[formatted(m['actual'],m['unit']),m['population_n']] for _,m in available],
        hovertemplate='%{y}<br>%{x:.1f} / 100<br>%{customdata[0]}<br>n=%{customdata[1]}<extra></extra>'))
    fig.update_xaxes(range=[0,100],title=t('rank_percentile_axis'))
    fig.update_yaxes(autorange='reversed')
    fig.update_layout(title=t('rank_official' if data['mode']=='official' else 'rank_local'))
    return style_chart(fig,height=480)


def percentile_panel(data):
    st.subheader(t('rank_percentiles'))
    st.caption(t('rank_official_note') if data['mode']=='official' else t('rank_local_note'))
    columns=st.columns(3)
    for index,(key,metric) in enumerate(data['metrics'].items()):
        with columns[index%3].container(border=True):
            st.markdown('**'+t('rank_metric_'+key)+'**',help=t('rank_direction_'+metric['direction']))
            st.markdown('### '+('N/A' if metric['percentile'] is None else f"{metric['percentile']:.1f} / 100"))
            st.caption(t('rank_actual')+': '+formatted(metric['actual'],metric['unit']))
            st.caption(t('rank_population_n',n=metric['population_n'])+f" · {data['season']}")
            st.caption(t('rank_direction_'+metric['direction']))
            if metric['percentile'] is None:
                st.caption(t('rank_not_qualified'))
    st.plotly_chart(percentile_chart(data),key='rank_percentile_chart',width='stretch')


def standardized_chart(result,candidate):
    fig=go.Figure()
    for name,values in ((t('rank_selected'),result['target_z']),(candidate['player']['fullName'],candidate['z'])):
        fig.add_bar(name=name,x=[t('rank_metric_'+k) for k in FEATURES],y=[values[k] for k in FEATURES])
    fig.update_layout(barmode='group',title=t('rank_standardized'),yaxis_title=t('rank_z_axis'))
    return style_chart(fig,height=400)


def similarity_panel(player,result,season,category,change_favorite):
    st.subheader(t('rank_similar'))
    st.caption(t('rank_similarity_note'))
    st.caption(t('rank_similarity_population',n=result['eligible_n'],excluded=result['excluded_n'],minimum=result['minimum_pa_or_bf']))
    if result['status']!='available':
        st.info(t('rank_similarity_unavailable'))
        return
    st.caption(t('rank_feature_reason_'+category))
    for index,candidate in enumerate(result['results']):
        person=candidate['player']
        with st.container(border=True):
            st.markdown(f"**{index+1}. {person['fullName']} · MLB ID {person['id']}**")
            teams=' / '.join(candidate['teams']) or 'N/A'
            if candidate['multiple_teams']:
                teams=t('rank_multiple_teams')+' · '+teams
            st.caption(f"{season} · {teams} · {' / '.join(candidate['positions']) or 'N/A'}")
            st.caption(t('rank_score')+f": {candidate['score']:.4f} · "+t('rank_distance')+f": {candidate['distance']:.4f}")
            st.dataframe([{t('rank_metric'):t('rank_metric_'+key),t('rank_selected'):result['target_values'][key],
                           person['fullName']:candidate['values'][key],t('rank_candidate_difference'):candidate['differences'][key]}
                          for key in FEATURES],hide_index=True,width='stretch')
            closest=min(FEATURES,key=lambda k:abs(candidate['z'][k]-result['target_z'][k]))
            different=max(FEATURES,key=lambda k:abs(candidate['z'][k]-result['target_z'][k]))
            st.caption(t('rank_reason',close=t('rank_metric_'+closest),different=t('rank_metric_'+different)))
            a,b,c,d=st.columns(4)
            a.button(t('rank_open'),key=f'rank_open_{person["id"]}',on_click=open_statistics,args=(person,season))
            saved=any(p['id']==person['id'] for p in st.session_state.get('_favorites',[]))
            b.button(t('rank_unsave' if saved else 'rank_save'),key=f'rank_save_{person["id"]}',on_click=change_favorite,args=(person,))
            c.button(t('rank_compare'),key=f'rank_compare_{person["id"]}',on_click=open_comparison,args=(player,person,season,category))
            d.button(t('career_open'),key=f'rank_career_{person["id"]}',on_click=select_player,args=(person,'커리어 분석'))
    options={c['player']['id']:c for c in result['results']}
    if options:
        key='rank_visual_candidate'
        if st.session_state.get(key) not in options:
            st.session_state.pop(key,None)
        selected=st.selectbox(t('rank_visual_select'),list(options),format_func=lambda pid:options[pid]['player']['fullName'],key=key)
        st.plotly_chart(standardized_chart(result,options[selected]),key='rank_similarity_chart',width='stretch')


def panel(player,season,category,change_favorite):
    st.subheader(t('rank_title'))
    st.caption(t('rank_intro'))
    if category=='pitching':
        st.caption(t('rank_pitcher_note'))
    if season<2015:
        st.info(t('sc_coverage'))
        return
    identity=(player['id'],season,category)
    stored=st.session_state.get('rank_boards')
    if st.button(t('rank_load'),key='rank_load'):
        with st.spinner(t('rank_loading')):
            bundle=load_boards(season,category)
            stored={'identity':identity,'bundle':bundle}
            st.session_state['rank_boards']=stored
    if not stored or stored['identity']!=identity:
        return
    bundle=stored['bundle']
    if bundle['errors']:
        st.warning(t('rank_source_partial'))
    mode=st.radio(t('rank_method'),['official','local'],format_func=lambda k:t('rank_'+k),horizontal=True,key='rank_method')
    count=st.selectbox(t('rank_top'),[5,10],key='rank_top')
    try:
        percentiles=profile(bundle,player['id'],mode)
        similarity=similar_players(bundle,player['id'],count)
    except ValueError:
        st.warning(t('rank_identity_error'))
        return
    ranks_tab,similar_tab=st.tabs([t('rank_percentiles'),t('rank_similar')])
    with ranks_tab:
        percentile_panel(percentiles)
    with similar_tab:
        similarity_panel(player,similarity,season,category,change_favorite)
    if st.session_state.get('ai_enabled'):
        from components import ai_ui
        if ai_ui.ready():
            context=ai_context(player,percentiles,similarity)
            st.subheader(t('rank_ai'))
            ai_ui.report(context,t('rank_ai_prompt'),'rank_ai')
            with st.expander(t('rank_chat')):
                ai_ui.chat(context)
    with st.expander(t('rank_sources')):
        st.json({'percentiles':percentiles,'similarity':similarity,
                 'sources':{k:{field:v.get(field) for field in ('source','retrieved_at')} for k in ('official','raw','contact') if (v:=bundle.get(k))},
                 'errors':bundle['errors']})


def clear_cache():
    clear_source_cache()
    st.session_state.pop('rank_boards',None)
