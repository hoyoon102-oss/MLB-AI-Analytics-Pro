"""Full-population filters, competition ranks, percentile scope and safe CSV export."""
from datetime import date
import json
import pandas as pd
from analytics.pitching import innings_to_outs,pitching_stats
from analytics.statcast_hitting import number
from analytics.advanced_stats import metrics as advanced_metrics
from services.statcast_service import integer
from analytics.percentiles import local_percentile
from analytics.advanced_stats import METHODS
from analytics.advanced_stats_sources import CONSTANTS_SOURCE,REVIEWED_AT

HITTING={k:(k,'count','desc') for k in ('HR','RBI','H','R','BB','SO','SB')}
HITTING.update({k:(k,'rate','desc') for k in ('AVG','OBP','SLG','OPS','wOBA','ISO','BABIP')})
HITTING.update({'BB%':('BB%','%','desc'),'K%':('K%','%','asc')})
PITCHING={k:(k,'count','desc') for k in ('W','SO','SV','GS')}
PITCHING.update({'L':('L','count','asc'),'IP':('IP','decimal IP','desc'),
                 **{k:(k,'rate','asc') for k in ('ERA','WHIP','FIP','BB/9','HR/9')},
                 'K/9':('K/9','rate','desc'),'K%':('K%','%','desc'),'BB%':('BB%','%','asc'),'K-BB%':('K-BB%','%','desc')})
SC_HIT={'EV':('exit_velocity_avg','mph','desc'),'Hard-Hit%':('hard_hit_percent','%','desc'),
        'Barrel%':('barrel_batted_rate','%','desc'),'xBA':('xba','rate','desc'),
        'xSLG':('xslg','rate','desc'),'xwOBA':('xwoba','rate','desc')}
SC_PITCH={'FB Velocity':('fastball_avg_speed','mph','desc'),'FB Spin':('fastball_avg_spin','rpm','desc'),
          'Whiff%':('whiff_percent','%','desc'),'Chase%':('oz_swing_percent','%','desc'),'xERA':('xera','rate','asc'),
          'EV Allowed':('exit_velocity_avg','mph','asc'),'Hard-Hit% Allowed':('hard_hit_percent','%','asc'),
          'Barrel% Allowed':('barrel_batted_rate','%','asc')}


def specs(category):
    if category not in ('hitting','pitching'):
        raise ValueError('lb_identity_error')
    return dict(HITTING if category=='hitting' else PITCHING,**(SC_HIT if category=='hitting' else SC_PITCH))


def historical_age(birth_date,season):
    try:
        born=date.fromisoformat(birth_date)
        reference=date(int(season),7,1)
        return reference.year-born.year-((reference.month,reference.day)<(born.month,born.day)) if born<=reference else None
    except (ValueError,TypeError):
        return None


def build_frame(dataset):
    category=dataset['category']
    specs(category)
    year=dataset['season']
    qualified=set(dataset['qualified_ids'])
    raw=(dataset.get('supplemental') or {}).get('players',{})
    if dataset.get('supplemental') and any(dataset['supplemental'][k]!=dataset[k] for k in ('season','category')):
        raise ValueError('lb_identity_error')
    rows=[]
    for split in dataset['rows']:
        person=split['player']
        pid=person['id']
        if str(split.get('season'))!=str(year) or split.get('gameType','R')!='R':
            raise ValueError('lb_identity_error')
        stat=split['stat']
        team=(split.get('team') or {}).get('id')
        multi=(integer(split.get('numTeams')) or 1)>1
        members=dataset['memberships'].get(pid,[]) if multi else [{'team_id':team,'league_id':(split.get('league') or {}).get('id')}]
        complete=all(m['team_id'] in dataset['teams'] for m in members) and bool(members)
        if multi and len(members)<integer(split['numTeams']):
            complete=False
        tids=tuple(sorted({m['team_id'] for m in members if m['team_id'] is not None}))
        lids=tuple(sorted({dataset['teams'][tid]['league_id'] for tid in tids if tid in dataset['teams'] and dataset['teams'][tid]['league_id'] is not None}))
        row={'id':pid,'name':person['fullName'],'season':year,'category':category,
             'team_ids':tids,'league_ids':lids,'teams':' / '.join(dataset['teams'][tid]['name'] for tid in tids if tid in dataset['teams']),
             'league':' / '.join('AL' if lid==103 else 'NL' if lid==104 else str(lid) for lid in lids),
             'position':(split.get('position') or {}).get('abbreviation') or None,
             'age':historical_age(person.get('birthDate'),year),'qualified':pid in qualified,
             'memberships_complete':complete,'multiple_teams':multi,'G':number(stat.get('gamesPlayed')),
             'PA':number(stat.get('plateAppearances')),'IP':None,'IP_display':stat.get('inningsPitched'),
             'role':'unknown','metric_source':dataset['sources'][0]}
        if category=='hitting':
            mapping={'AVG':'avg','OBP':'obp','SLG':'slg','OPS':'ops','HR':'homeRuns','RBI':'rbi','H':'hits',
                     'R':'runs','BB':'baseOnBalls','SO':'strikeOuts','SB':'stolenBases'}
            row.update({k:number(stat.get(field)) for k,field in mapping.items()})
            ab=number(stat.get('atBats'))
            if ab is None or ab<=0:
                for key in ('AVG','SLG','OPS'):
                    row[key]=None
            obp_parts=[number(stat.get(k)) for k in ('atBats','baseOnBalls','hitByPitch','sacFlies')]
            if any(v is None for v in obp_parts) or sum(obp_parts)<=0:
                row['OBP']=row['OPS']=None
        else:
            p=pitching_stats(stat)
            row.update({key:number(p.get(field)) for key,field in {'ERA':'era','WHIP':'whip','W':'wins','L':'losses',
                        'SO':'strikeOuts','SV':'saves','GS':'gamesStarted'}.items()})
            outs=innings_to_outs(p.get('inningsPitched'))
            row['IP']=outs/3 if outs is not None else None
            row['IP_display']=p.get('inningsPitched')
            appearances=number(stat.get('gamesPitched')) or row['G']
            if appearances and row['GS'] is not None:
                row['role']='starter' if row['GS']/appearances>=.5 else 'reliever'
        row.update({k:v['value'] for k,v in advanced_metrics(stat,year,category,pid,dataset['retrieved_at']).items() if k in specs(category)})
        for key,(field,unit,_) in (SC_HIT if category=='hitting' else SC_PITCH).items():
            row[key]=number(raw.get(pid,{}).get(field))
            if row[key] is not None and (row[key]<0 or unit=='%' and row[key]>100):
                row[key]=None
        rows.append(row)
    frame=pd.DataFrame(rows)
    if frame.empty:
        return frame
    if frame['id'].duplicated().any():
        raise ValueError('lb_population_error')
    return frame


def available_metrics(frame,category):
    return [key for key in specs(category) if key in frame and pd.to_numeric(frame[key],errors='coerce').notna().any()]


def filter_and_rank(frame,category,filters,metric,ascending=None):
    if metric not in specs(category):
        raise ValueError('lb_metric_error')
    if frame.empty:
        return frame.copy()
    if set(frame['category'])!={category} or len(frame['season'].unique())!=1:
        raise ValueError('lb_identity_error')
    result=frame.copy()
    if filters.get('qualified',True):
        result=result[result['qualified']]
    league=filters.get('league',0)
    team=filters.get('team',0)
    if (league or team) and not result['memberships_complete'].all():
        raise ValueError('lb_memberships_error')
    if league:
        result=result[result['league_ids'].map(lambda ids:league in ids)]
    if team:
        result=result[result['team_ids'].map(lambda ids:team in ids)]
    position=filters.get('position','ALL')
    if position!='ALL':
        choices={'LF','CF','RF','OF'} if position=='OF' else {position}
        result=result[result['position'].isin(choices)]
    if filters.get('role','all')!='all' and category=='pitching':
        result=result[result['role']==filters['role']]
    ages=filters.get('ages',[0,100])
    if ages!=[0,100] and tuple(ages)!=(0,100):
        result=result[result['age'].between(*ages)]
    minimum=filters.get('min_pa',0) if category=='hitting' else filters.get('min_ip',0)
    if minimum>0:
        result=result[result['PA' if category=='hitting' else 'IP']>=minimum]
    search=filters.get('search','').strip()
    if search:
        result=result[result['name'].str.contains(search,case=False,regex=False,na=False)]
    for threshold in filters.get('thresholds',[]):
        key=threshold['metric']
        if key not in specs(category) or key not in result:
            raise ValueError('lb_metric_error')
        if threshold.get('min') is not None:
            result=result[result[key]>=threshold['min']]
        if threshold.get('max') is not None:
            result=result[result[key]<=threshold['max']]
    result=result[result[metric].notna()].copy()
    asc=specs(category)[metric][2]=='asc' if ascending is None else bool(ascending)
    result['rank']=result[metric].rank(method='min',ascending=asc).astype(int)
    return result.sort_values([metric,'id'],ascending=[asc,True],kind='stable').reset_index(drop=True)


def paginate(ranked,limit=25,page=1):
    if limit not in (10,25,50,100,'all') or page<1:
        raise ValueError('lb_page_error')
    return ranked.copy() if limit=='all' else ranked.iloc[(page-1)*limit:page*limit].copy()


def subset_percentile(ranked,player_id,metric,ascending):
    target=ranked[ranked['id']==player_id]
    if target.empty:
        return None
    return local_percentile(float(target.iloc[0][metric]),ranked[metric].tolist(),'lower' if ascending else 'higher')


def export_csv(ranked,columns,dataset,filters,metric):
    exported=ranked[[key for key in ['rank','id','name','season','teams','position','age','G','PA','IP_display',*columns] if key in ranked]].copy()
    exported=exported.loc[:,~exported.columns.duplicated()]
    exported['ranking_metric']=metric
    exported['filter_configuration']=json.dumps(filters,ensure_ascii=False,allow_nan=False)
    exported['record_scope']='MLB regular-season full-season totals; season affiliation filters'
    exported['source']=dataset['sources'][0]
    exported['retrieved_at']=dataset['retrieved_at']
    exported['statcast_source']=(dataset.get('supplemental') or {}).get('source')
    exported['statcast_retrieved_at']=(dataset.get('supplemental') or {}).get('retrieved_at')
    # CSV text cells from external names must not be interpreted as spreadsheet formulas.
    for column in exported.select_dtypes(include='object'):
        exported[column]=exported[column].map(lambda v:"'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v)
    return exported.to_csv(index=False,na_rep='').encode('utf-8-sig')


def ai_context(ranked,dataset,filters,metric,ascending,selected_id=None,columns=()):
    keys=[k for k in ['rank','id','name','teams','position','age','G','PA','IP_display',metric,'OPS','ERA','BB%','K%',*columns] if k in ranked]
    keys=list(dict.fromkeys(keys))
    top=ranked.head(25).loc[:,keys]
    selected=ranked[ranked['id']==selected_id].loc[:,keys]
    clean=lambda df:df.astype(object).where(pd.notna(df),None).to_dict('records')
    return {'mode':'MLB Leaderboard','season':dataset['season'],'category':dataset['category'],'game_type':'R',
            'filters':filters,'ranking_metric':metric,'unit':specs(dataset['category'])[metric][1],
            'ascending':ascending,'rank_method':'competition rank: 1,2,2,4; filter before ranking; ID tie-break display only',
            'metric_definition':METHODS.get(metric,'Source-published MLB season statistic or Savant Custom Leaderboard season metric; see units and source'),
            'advanced_constants':{'source':CONSTANTS_SOURCE,'reviewed_at':REVIEWED_AT} if metric in ('wOBA','FIP') else None,
            'eligible_n':len(ranked),'source_population_n':dataset['population_n'],
            'top_results':clean(top),'context_limit':25,'selected_player':clean(selected),
            'sources':dataset['sources'],'retrieved_at':dataset['retrieved_at'],
            'statcast_source':(dataset.get('supplemental') or {}).get('source'),
            'limitations':['Full-season totals filtered by verified season affiliations; cross-league traded players may appear in both affiliation subsets.',
                          'Ranks describe the complete filtered population, not just visible rows; table-only sorts do not change the ranking metric.',
                          'API QUALIFIED pool is distinct from custom minimums and Statcast qualification. No overall talent or future prediction.']}
