"""Complete MLB regular-season career histories with per-season failure provenance."""
from datetime import date,datetime,timezone
import requests
from services.cache_manager import persistent, observe
import streamlit as st
from services.player_stats import api_json,validate_category,extract_stats,DataError
from analytics.pitching import pitching_stats,number
from analytics.career_trends import aggregate


def extract_career(payload,player_id,category,latest_year):
    validate_category(category)
    if not isinstance(payload,dict) or not isinstance(payload.get('stats'),list):
        raise ValueError('career_schema_error')
    groups=[g for g in payload['stats'] if isinstance(g,dict) and g.get('group',{}).get('displayName')==category
            and g.get('type',{}).get('displayName')=='yearByYear']
    if len(groups)!=1 or not isinstance(groups[0].get('splits'),list):
        raise ValueError('career_schema_error')
    rows=[]
    for split in groups[0]['splits']:
        if not isinstance(split,dict):
            raise ValueError('career_schema_error')
        if split.get('sport',{}).get('id',1)!=1 or split.get('gameType','R')!='R':
            continue
        if (split.get('player') or {}).get('id',player_id)!=player_id or not str(split.get('season','')).isdigit():
            raise ValueError('career_identity_error')
        if int(split['season'])>latest_year:
            continue
        if not isinstance(split.get('stat'),dict):
            raise ValueError('career_schema_error')
        rows.append(split)
    years=sorted({int(r['season']) for r in rows})
    records,problems,methods,teams={},{},{},{}
    for year in years:
        season_rows=[r for r in rows if int(r['season'])==year]
        teams[year]=sorted({r['team']['name'] for r in season_rows if (r.get('team') or {}).get('name')})
        try:
            selected=extract_stats({'stats':[{'group':{'displayName':category},'splits':season_rows}]},year,category,player_id)
            methods[year]='source_season_total'
        except DataError:
            # Aggregate only distinct team splits, never ambiguous duplicates or extra totals.
            ids=[(r.get('team') or {}).get('id') for r in season_rows]
            if any(i is None for i in ids) or len(set(ids))!=len(ids):
                records[year]=None
                problems[year]='ambiguous_season_total'
                continue
            try:
                selected=aggregate([r['stat'] for r in season_rows],category)
            except (ValueError,TypeError):
                records[year]=None
                problems[year]='invalid_count_or_innings_totals'
                continue
            selected['gamesPlayed']=None  # A suspended game can involve both teams; do not double count it.
            methods[year]='distinct_team_count_totals; games unavailable without official total'
        records[year]=selected
    career_groups=[g for g in payload['stats'] if isinstance(g,dict) and g.get('group',{}).get('displayName')==category
                   and g.get('type',{}).get('displayName')=='career']
    career_rows=[s for g in career_groups for s in g.get('splits',[]) if s.get('sport',{}).get('id',1)==1 and s.get('gameType','R')=='R']
    totals=None
    if len(career_rows)==1:
        s=career_rows[0]
        if (s.get('player') or {}).get('id',player_id)!=player_id or not isinstance(s.get('stat'),dict):
            raise ValueError('career_identity_error')
        totals=pitching_stats(s['stat']) if category=='pitching' else dict(s['stat'],_group=category)
    elif len(career_rows)>1:
        raise ValueError('career_schema_error')
    if records:
        for year in range(min(records),max(records)+1):
            records.setdefault(year,None)
    if totals is None and not problems:
        totals=aggregate([r for r in records.values() if r],category)
        total_method='pooled_season_count_totals'
    else:
        total_method='source_published_career' if totals is not None else 'unavailable'
    return {'player_id':player_id,'category':category,'game_type':'R','records':dict(sorted(records.items())),
            'career_totals':totals or {},'total_method':total_method,'problems':problems,'season_methods':methods,
            'teams':teams,'incomplete':[],'season_status':{},'calendar_error':None}


@observe
@st.cache_data(ttl=60,show_spinner=False)
@persistent('calendar')
def season_calendar():
    payload=api_json('seasons/all',{'sportId':1})
    if not isinstance(payload.get('seasons'),list):
        raise ValueError('career_schema_error')
    return {int(r['seasonId']):r for r in payload['seasons'] if str(r.get('seasonId','')).isdigit()}


@observe
@st.cache_data(ttl=60,show_spinner=False,max_entries=64)
@persistent('career')
def fetch_career(player_id,category,today_iso):
    if isinstance(player_id,bool) or not isinstance(player_id,int) or player_id<=0:
        raise ValueError('career_identity_error')
    validate_category(category)
    today=date.fromisoformat(today_iso)
    payload=api_json(f'people/{player_id}/stats',{'stats':'yearByYear,career','group':category,'sportIds':1,'gameType':'R'})
    result=extract_career(payload,player_id,category,today.year)
    try:
        calendar=season_calendar()
    except (ValueError,requests.RequestException,TypeError,KeyError):
        calendar={}
        result['calendar_error']='career_calendar_unavailable'
    for year in result['records']:
        end=(calendar.get(year) or {}).get('regularSeasonEndDate')
        try:
            complete=date.fromisoformat(end)<today if end else year<today.year
        except (ValueError,TypeError):
            complete=year<today.year
        if not complete:
            result['incomplete'].append(year)
        result['season_status'][year]={'complete':complete,'calendar_verified':bool(end),
                                      'shortened_known':year in (1994,1995,2020),
                                      'regular_season_end':end}
    played=[y for y,r in result['records'].items() if r]
    result.update(first_season=min(played) if played else None,last_season=max(played) if played else None,
                  played_seasons=len(played),source=f'https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=yearByYear,career&group={category}&sportIds=1&gameType=R',
                  retrieved_at=datetime.now(timezone.utc).isoformat())
    return result


def load_contexts(years,category,player_id,include_statcast=False,include_league=False,progress=None):
    """Explicit supplementary season summaries only; no career-wide pitch download."""
    from services.league_stats import fetch_league_average
    from services.leaderboard_service import fetch_table
    leagues,statcast,errors,sources={},{},[],{}
    for index,year in enumerate(years):
        if include_league:
            try:
                leagues[year]=fetch_league_average(year,0,category)
            except (ValueError,requests.RequestException,TypeError,KeyError):
                errors.append({'season':year,'source':'league'})
        if include_statcast and year>=2015:
            try:
                table=fetch_table(year,category,'raw')
                row=table['players'].get(player_id,{})
                fields={'avg_ev':'exit_velocity_avg','hard_hit':'hard_hit_percent','barrel':'barrel_batted_rate','xwoba':'xwoba','xera':'xera','fb_velocity':'fastball_avg_speed'}
                statcast[year]={key:number(row.get(field)) for key,field in fields.items()}
                sources[year]={'source':table['source'],'retrieved_at':table['retrieved_at']}
            except (ValueError,requests.RequestException,TypeError,KeyError):
                errors.append({'season':year,'source':'statcast'})
        if progress:
            progress((index+1)/len(years))
    return {'leagues':leagues,'statcast':statcast,'errors':errors,'sources':sources}
