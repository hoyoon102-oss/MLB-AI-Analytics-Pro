"""Career arithmetic and transparent descriptive rules, without talent inference."""
from analytics.pitching import number,innings_to_outs,outs_to_innings
from services.league_stats import sum_teams,rates_from_totals,ratio
from analytics.advanced_stats import metrics as advanced_metrics
from analytics.statcast_hitting import number as finite_number

HIT_COUNTS=('gamesPlayed','plateAppearances','atBats','hits','totalBases','baseOnBalls','strikeOuts','hitByPitch',
            'sacFlies','homeRuns','rbi','doubles','triples','intentionalWalks')
PITCH_COUNTS=('gamesPlayed','gamesPitched','gamesStarted','battersFaced','hits','baseOnBalls','strikeOuts','earnedRuns',
              'homeRuns','hitBatsmen','wins','losses','saves','atBats','sacFlies')
HIT_METRICS={'AVG':('avg','rate','higher'),'OBP':('obp','rate','higher'),'SLG':('slg','rate','higher'),
             'OPS':('ops','rate','higher'),'HR':('homeRuns','count','context'),'RBI':('rbi','count','context'),
             'BB%':('BB%','pp','higher'),'K%':('K%','pp','lower'),'ISO':('ISO','rate','higher'),
             'OPS+':('OPS+','index','higher'),'wRC+':('wRC+','index','higher'),'wOBA':('wOBA','rate','higher')}
PITCH_METRICS={'ERA':('era','rate','lower'),'WHIP':('whip','rate','lower'),'SO':('strikeOuts','count','context'),
               'IP':('inningsPitched','innings','context'),'K/9':('K/9','rate','higher'),'BB/9':('BB/9','rate','lower'),
               'K-BB%':('K-BB%','pp','higher'),'FIP':('FIP','rate','lower'),'ERA+':('ERA+','index','higher')}
STATCAST_METRICS={'EV':('avg_ev','mph','context'),'Hard-Hit%':('hard_hit','pp','context'),
                  'Barrel%':('barrel','pp','context'),'xwOBA':('xwoba','rate','context'),
                  'xERA':('xera','rate','lower'),'FB Velocity':('fb_velocity','mph','context')}


def specs(category):
    if category not in ('hitting','pitching'):
        raise ValueError('career_category_error')
    return HIT_METRICS if category=='hitting' else PITCH_METRICS


def aggregate(records,category):
    """Sum counts with strict missing propagation, derive rates from totals only."""
    specs(category)
    if not records:
        return {}
    if any(r.get('_group',category)!=category for r in records):
        raise ValueError('career_category_error')
    totals,_=sum_teams(records,category)
    for key in HIT_COUNTS if category=='hitting' else PITCH_COUNTS:
        if key in totals:
            continue
        nums=[number(r.get(key)) for r in records]
        totals[key]=sum(nums) if all(v is not None and v.is_integer() for v in nums) else None
    rates=rates_from_totals(totals,category)
    result=dict(totals,**rates,_group=category,_pooled=True)
    if category=='pitching':
        outs=totals.get('outs')
        result['inningsPitched']=outs_to_innings(int(outs)) if outs is not None else None
        result['_outs']=outs
        result['K-BB%']=ratio(totals.get('strikeOuts'),totals.get('battersFaced'),100)
        walk=ratio(totals.get('baseOnBalls'),totals.get('battersFaced'),100)
        result['K-BB%']=result['K-BB%']-walk if result['K-BB%'] is not None and walk is not None else None
    return result


def metric_value(record,year,category,metric,statcast=None):
    if not record:
        return None
    if metric in STATCAST_METRICS:
        return (statcast or {}).get(year,{}).get(STATCAST_METRICS[metric][0])
    field=specs(category)[metric][0]
    if metric=='IP':
        outs=innings_to_outs(record.get('inningsPitched'))
        return outs/3 if outs is not None else None
    if metric=='ISO' and record.get('_pooled'):
        a,b=number(record.get('slg')),number(record.get('avg'))
        return a-b if a is not None and b is not None else None
    if field in record:
        return (finite_number if metric in ('K-BB%','FIP') else number)(record.get(field))
    return advanced_metrics(record,year,category).get(metric,{}).get('value')


def qualified(record,category,metric):
    if not record:
        return False
    if specs(category).get(metric,('',None,None))[1]=='count':
        return True
    if category=='hitting':
        return (number(record.get('plateAppearances')) or 0)>=300
    outs=innings_to_outs(record.get('inningsPitched'))
    return outs is not None and outs>=300 and (metric!='K-BB%' or (number(record.get('battersFaced')) or 0)>=300)


def changes(records,category,metric,statcast=None):
    unit,direction=(specs(category).get(metric) or STATCAST_METRICS[metric])[1:]
    years=sorted(y for y,r in records.items() if r)
    output=[]
    for before,after in zip(years,years[1:]):
        first,second=metric_value(records[before],before,category,metric,statcast),metric_value(records[after],after,category,metric,statcast)
        delta=second-first if first is not None and second is not None else None
        favorable=delta if direction=='higher' else -delta if direction=='lower' and delta is not None else None
        label='increase' if favorable is not None and favorable>0 else 'decline' if favorable is not None and favorable<0 else 'equal' if delta==0 else 'context'
        percent=100*delta/first if delta is not None and first>0 and unit in ('rate','count') else None
        output.append({'from':before,'to':after,'gap_years':after-before,'previous':first,'current':second,
                       'difference':delta,'percentage_change':percent,'direction':label,'unit':unit,
                       'previous_sample':records[before].get('plateAppearances' if category=='hitting' else 'inningsPitched'),
                       'current_sample':records[after].get('plateAppearances' if category=='hitting' else 'inningsPitched')})
    return output


def peak(records,category,metric,incomplete=()):
    direction=specs(category)[metric][2]
    if direction=='context':
        return []
    valid=[(y,metric_value(r,y,category,metric)) for y,r in records.items()
           if y not in incomplete and qualified(r,category,metric) and metric_value(r,y,category,metric) is not None]
    if not valid:
        return []
    value=(min if direction=='lower' else max)(v for _,v in valid)
    return [{'season':y,'value':v,'record':records[y]} for y,v in valid if v==value]


def rolling(records,category,metric):
    """Three consecutive calendar seasons, recomputed from pooled counts."""
    allowed={'AVG','OBP','SLG','OPS','ISO','BB%','K%'} if category=='hitting' else {'ERA','WHIP','K/9','BB/9','K-BB%'}
    result={year:None for year in records}
    if metric not in allowed:
        return result
    for year in sorted(records):
        window=[records.get(y) for y in range(year-2,year+1)]
        if all(window):
            pooled=aggregate(window,category)
            # For BB/K rates, advanced calculator needs MLB API count field names.
            result[year]=metric_value(pooled,year,category,metric)
    return result


def league_value(league,category,metric):
    if not league or league.get('category')!=category:
        return None
    key=(specs(category).get(metric) or ('',))[0]
    alias={'BB%':'bbPercent','K%':'kPercent','K/9':'strikeoutsPer9Inn','BB/9':'walksPer9Inn'}
    if metric=='ISO':
        a,b=league['rates'].get('slg'),league['rates'].get('avg')
        return a-b if a is not None and b is not None else None
    return league['rates'].get(alias.get(key,key))


def development(records,category,leagues,incomplete=(),unknown=()):
    """Large descriptive changes, not significance tests. Require league context for breakout."""
    metric='OPS' if category=='hitting' else 'ERA'
    threshold=.100 if category=='hitting' else 1.0
    direction=1 if category=='hitting' else -1
    eligible={y:r for y,r in records.items() if y not in incomplete and qualified(r,category,metric)}
    changes_out=[]
    for c in changes(records,category,metric):
        a,b=c['from'],c['to']
        if a not in eligible or b not in eligible or c['difference'] is None or any(a<=y<=b for y in unknown):
            continue
        signed=direction*c['difference']
        if abs(signed)>=threshold:
            changes_out.append(dict(c,finding='statistical_improvement' if signed>0 else 'statistical_decline'))
    breakout=[]
    for year in sorted(eligible):
        prior=sorted(y for y in eligible if y<year)[-3:]
        if len(prior)<2:
            continue
        if any(prior[0]<=y<=year for y in unknown):
            continue
        years=prior+[year]
        league_rates=[league_value(leagues.get(y),category,metric) if (leagues.get(y) or {}).get('season')==y else None for y in years]
        values=[metric_value(eligible[y],y,category,metric) for y in years]
        if any(v is None or v<=0 for v in league_rates) or any(v is None for v in values):
            continue
        # OPS/lgOPS (higher); lgERA/ERA (higher), never label these OPS+ or ERA+.
        if category=='pitching' and any(v<=0 for v in values):
            continue
        relative=[v/l if category=='hitting' else l/v for v,l in zip(values,league_rates)]
        baseline=sum(relative[:-1])/len(prior)
        improvement=relative[-1]-baseline
        if relative[-1]>=1 and improvement>=.15:
            breakout.append({'season':year,'prior_seasons':prior,'relative':relative[-1],
                             'prior_relative_mean':baseline,'relative_difference':improvement,
                             'metric':metric,'method':'unadjusted OPS/lgOPS or lgERA/ERA, >=0.15 above preceding 2–3 qualified-season baseline and >=1.0'})
    return {'metric':metric,'threshold':threshold,'changes':changes_out,'breakouts':breakout,
            'method':'300 PA or 100 IP; completed seasons; large descriptive changes, not statistical significance or underlying talent'}


def career_x(year,debut,mode):
    return year-debut+1 if mode=='experience' else year


def ai_context(player,career,metric,leagues=None,statcast=None):
    if player['id']!=career['player_id']:
        raise ValueError('career_identity_error')
    records=career['records']
    return {'player':{'id':player['id'],'name':player['fullName']},'season':max(records) if records else None,
            'category':career['category'],'mode':'Career Development', 'statistics':career['career_totals'],
            'career_summary':{k:v for k,v in career.items() if k not in ('records','career_totals')},
            'selected_metric':metric,'timeline':{str(y):metric_value(r,y,career['category'],metric,statcast) for y,r in records.items()},
            'analysis_range':[min(records),max(records)] if records else [],
            'year_over_year':changes(records,career['category'],metric,statcast),
            'peak':peak(records,career['category'],metric,career['incomplete']) if metric in specs(career['category']) else [],
            'development':development(records,career['category'],leagues or {},career['incomplete'],career['problems']),
            'league_context':{str(y):{'value':league_value(l,career['category'],metric),'source':l.get('source'),'retrieved_at':l.get('retrieved_at')} for y,l in (leagues or {}).items()},
            'limitations':['Descriptive rules, no significance test or talent/causal inference. No future prediction.',
                          'Calendar gaps are explicit; percentage changes omitted for percentage-point/index/innings metrics.',
                          'Unadjusted league ratios are not OPS+ or ERA+. Career rates use pooled counts or official career totals.']}
