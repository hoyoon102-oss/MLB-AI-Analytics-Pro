"""Small season leaderboards for rankings and similarity, never pitch-level MLB data."""
from datetime import datetime, timezone
from services.cache_manager import persistent, observe
import requests
import streamlit as st
from services.statcast_service import csv_request, integer, StatcastError, published_table

SELECTIONS = ('pa,k_percent,bb_percent,whiff_percent,oz_swing_percent,exit_velocity_avg,'
              'hard_hit_percent,barrel_batted_rate,xba,xslg,xwoba,xera,fastball_avg_speed,fastball_avg_spin,sprint_speed')
QUALIFICATION_SOURCE = 'https://baseballsavant.mlb.com/leaderboard/percentile-rankings'


def validate_table(rows, season):
    result = {}
    for row in rows:
        pid = integer(row.get('player_id'))
        if pid == 999999:  # Source's non-player placeholder, never an eligible player.
            continue
        if pid is None or pid <= 0 or integer(row.get('year')) != int(season) or pid in result:
            raise StatcastError('rank_identity_error')
        result[pid] = row
    return result


@observe
@st.cache_data(ttl=60, max_entries=32, show_spinner=False)
@persistent('leaderboard', 'Baseball Savant')
def fetch_table(season, category, kind):
    if int(season)<2015 or category not in ('hitting','pitching') or kind not in ('percentiles','raw'):
        raise StatcastError('sc_coverage')
    path = '/leaderboard/percentile-rankings' if kind == 'percentiles' else '/leaderboard/custom'
    params={'type':'batter' if category=='hitting' else 'pitcher','year':int(season),
            'position':'','team':'','csv':'true'}
    if kind == 'raw':
        params.update(min=0,selections=SELECTIONS)
    fields, rows, source = csv_request(path,params)
    required={'player_id','year'} | ({'pa','k_percent','bb_percent','exit_velocity_avg'} if kind=='raw' else {'player_name'})
    if not required <= set(fields):
        raise StatcastError('sc_schema_error')
    return {'season':int(season),'category':category,'game_type':'R','kind':kind,
            'players':validate_table(rows,season),'source':source,
            'retrieved_at':datetime.now(timezone.utc).isoformat()}


@observe
@st.cache_data(ttl=60, max_entries=16, show_spinner=False)
@persistent('memberships')
def season_metadata(season,category):
    """MLB season affiliations/positions, not current-team hydration."""
    records,offset,total = [],0,None
    while total is None or offset < total:
        response=requests.get('https://statsapi.mlb.com/api/v1/stats',params={
            'stats':'season','group':category,'season':int(season),'sportIds':1,'gameType':'R',
            'playerPool':'ALL','limit':1000,'offset':offset,'hydrate':'person'},timeout=(5,30))
        response.raise_for_status()
        groups=[g for g in response.json().get('stats',[]) if g.get('group',{}).get('displayName')==category]
        if len(groups)!=1 or not isinstance(groups[0].get('splits'),list):
            raise StatcastError('sc_schema_error')
        group=groups[0]
        total=integer(group.get('totalSplits'))
        splits=group['splits']
        if total is None or total>10000 or (not splits and offset<total):
            raise StatcastError('sc_schema_error')
        records.extend(splits)
        offset += len(splits)
    result={}
    for split in records:
        if integer(split.get('season'))!=int(season) or split.get('gameType','R')!='R':
            raise StatcastError('rank_identity_error')
        person=split.get('player') or {}
        pid=integer(person.get('id'))
        if pid is None or not isinstance(person.get('fullName'),str):
            raise StatcastError('rank_identity_error')
        item=result.setdefault(pid,{'id':pid,'fullName':person['fullName'],'teams':[], 'positions':[],
                                    'season':int(season),'category':category})
        team=(split.get('team') or {}).get('name')
        position=(split.get('position') or {}).get('abbreviation')
        if team and team not in item['teams']:
            item['teams'].append(team)
        if position and position not in item['positions']:
            item['positions'].append(position)
        item['multiple_teams']=item.get('multiple_teams',False) or (integer(split.get('numTeams')) or 0)>1
    return result


def load_boards(season,category):
    output={'season':int(season),'category':category,'game_type':'R','official':None,'raw':None,
            'contact':None,'metadata':{},'errors':[]}
    for key,loader in [('official',lambda:fetch_table(season,category,'percentiles')),
                       ('raw',lambda:fetch_table(season,category,'raw')),
                       ('contact',lambda:published_table(season,category,'contact')),
                       ('metadata',lambda:season_metadata(season,category))]:
        try:
            output[key]=loader()
        except (ValueError,requests.RequestException,KeyError,TypeError,UnicodeError) as error:
            output['errors'].append({'source':key,'error':str(error)})
    return output


def clear_cache():
    fetch_table.clear()
    season_metadata.clear()


def _season_population(season,category,pool):
    """Fetch every page and reject repeated/partial populations before ranking."""
    if category not in ('hitting','pitching') or pool not in ('ALL','QUALIFIED'):
        raise StatcastError('lb_identity_error')
    rows,offset,total,seen=[],0,None,set()
    sources=[]
    while total is None or offset<total:
        response=requests.get('https://statsapi.mlb.com/api/v1/stats',params={
            'stats':'season','group':category,'season':int(season),'sportIds':1,'gameType':'R',
            'playerPool':pool,'limit':200,'offset':offset,'hydrate':'person'},timeout=(5,30))
        response.raise_for_status()
        payload=response.json()
        if not isinstance(payload,dict) or not isinstance(payload.get('stats'),list):
            raise StatcastError('lb_schema_error')
        groups=[g for g in payload['stats'] if isinstance(g,dict) and g.get('group',{}).get('displayName')==category
                and g.get('type',{}).get('displayName')=='season']
        if len(groups)!=1 or not isinstance(groups[0].get('splits'),list):
            raise StatcastError('lb_schema_error')
        reported=integer(groups[0].get('totalSplits'))
        if reported is None or reported<0 or reported>10000 or (total is not None and reported!=total):
            raise StatcastError('lb_population_error')
        total=reported
        page=groups[0]['splits']
        if (not page and offset<total) or offset+len(page)>total:
            raise StatcastError('lb_population_error')
        for split in page:
            pid=integer((split.get('player') or {}).get('id'))
            if (pid is None or pid<=0 or pid in seen or integer(split.get('season'))!=int(season)
                    or split.get('gameType','R')!='R' or (split.get('sport') or {}).get('id',1)!=1
                    or not isinstance(split.get('stat'),dict)):
                raise StatcastError('lb_population_error')
            seen.add(pid)
            rows.append(split)
        sources.append(response.url)
        offset+=len(page)
    return {'rows':rows,'season':int(season),'category':category,'pool':pool,'game_type':'R',
            'population_n':total,'sources':sources,'retrieved_at':datetime.now(timezone.utc).isoformat()}


@observe
@st.cache_data(ttl=60,max_entries=24,show_spinner=False)
@persistent('leaderboard')
def recent_population(season,category,pool):
    return _season_population(season,category,pool)


@observe
@st.cache_data(ttl=60,max_entries=48,show_spinner=False)
@persistent('leaderboard')
def historical_population(season,category,pool):
    return _season_population(season,category,pool)


def player_population(season,category):
    from services.season_selection import current_date
    fetch=historical_population if int(season)<current_date().year else recent_population
    all_players=fetch(season,category,'ALL')
    qualified=fetch(season,category,'QUALIFIED')
    ids={(r.get('player') or {})['id'] for r in all_players['rows']}
    qualified_ids={(r.get('player') or {})['id'] for r in qualified['rows']}
    if not qualified_ids<=ids:
        raise StatcastError('lb_population_error')
    return dict(all_players,qualified_ids=sorted(qualified_ids),qualification_source=qualified,
                cache_policy='historical_24h' if fetch is historical_population else 'current_year_15m')


@observe
@st.cache_data(ttl=60,max_entries=48,show_spinner=False)
@persistent('memberships')
def traded_memberships(season,category,ids):
    """Only traded players: batched yearByYear hydration, never last-team inference."""
    result={}
    for start in range(0,len(ids),50):
        subset=ids[start:start+50]
        response=requests.get('https://statsapi.mlb.com/api/v1/people',params={
            'personIds':','.join(map(str,subset)),
            'hydrate':f'stats(group=[{category}],type=[yearByYear],season={season},gameType=R)'},timeout=(5,30))
        response.raise_for_status()
        people=response.json().get('people')
        if not isinstance(people,list) or {p.get('id') for p in people}!=set(subset):
            raise StatcastError('lb_memberships_error')
        for person in people:
            members={}
            for group in person.get('stats',[]):
                if (group.get('group') or {}).get('displayName')!=category or (group.get('type') or {}).get('displayName')!='yearByYear':
                    continue
                for split in group.get('splits',[]):
                    if integer(split.get('season'))!=int(season) or split.get('gameType','R')!='R' or (split.get('sport') or {}).get('id',1)!=1:
                        continue
                    tid=integer((split.get('team') or {}).get('id'))
                    if tid:
                        members[tid]={'team_id':tid,'league_id':integer((split.get('league') or {}).get('id'))}
            result[person['id']]=list(members.values())
    return result


def discovery_dataset(season,category,include_statcast=False):
    from services.league_stats import season_membership
    population=player_population(season,category)
    teams_payload,team_source=season_membership(season)
    teams={t['id']:{'name':t['name'],'league_id':(t.get('league') or {}).get('id')} for t in teams_payload.get('teams',[])
           if (t.get('sport') or {}).get('id',1)==1 and str(t.get('season'))==str(season)}
    if not teams:
        raise StatcastError('lb_memberships_error')
    traded=tuple(sorted(r['player']['id'] for r in population['rows'] if (integer(r.get('numTeams')) or 1)>1))
    errors=[]
    try:
        memberships=traded_memberships(season,category,traded) if traded else {}
    except (ValueError,requests.RequestException,TypeError,KeyError):
        memberships={}
        errors.append('lb_memberships_error')
    supplemental=None
    if include_statcast and int(season)>=2015:
        try:
            supplemental=fetch_table(season,category,'raw')
        except (ValueError,requests.RequestException,TypeError,KeyError,UnicodeError):
            errors.append('lb_statcast_error')
    return dict(population,teams=teams,team_source=team_source,memberships=memberships,
                supplemental=supplemental,errors=errors,include_statcast=include_statcast)


def clear_discovery_cache():
    recent_population.clear()
    historical_population.clear()
    traded_memberships.clear()
