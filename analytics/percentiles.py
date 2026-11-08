"""Official percentiles stay untouched; local ranks use explicit average-rank rules."""
from analytics.statcast_hitting import number

MIN_PLAYING_TIME={'hitting':300,'pitching':200}
# official CSV column, raw custom CSV column, unit, favorable raw direction.
HITTING={
 'avg_ev':('exit_velocity','exit_velocity_avg','mph','higher'),
 'max_ev':('max_ev',None,'mph','higher'),
 'hard_hit':('hard_hit_percent','hard_hit_percent','%','higher'),
 'barrel':('brl_percent','barrel_batted_rate','%','higher'),
 'xwoba':('xwoba','xwoba','rate','higher'), 'xba':('xba','xba','rate','higher'),
 'xslg':('xslg','xslg','rate','higher'),
 'whiff':('whiff_percent','whiff_percent','%','lower'),
 'chase':('chase_percent','oz_swing_percent','%','lower'),
 'k':('k_percent','k_percent','%','lower'), 'bb':('bb_percent','bb_percent','%','higher'),
 'sprint':('sprint_speed','sprint_speed','ft/s','higher')}
PITCHING={
 'fb_velocity':('fb_velocity','fastball_avg_speed','mph','higher'),
 'fb_spin':('fb_spin','fastball_avg_spin','rpm','context'),
 'whiff':('whiff_percent','whiff_percent','%','higher'),
 'chase':('chase_percent','oz_swing_percent','%','higher'),
 'k':('k_percent','k_percent','%','higher'), 'bb':('bb_percent','bb_percent','%','lower'),
 'hard_hit':('hard_hit_percent','hard_hit_percent','%','lower'),
 'barrel':('brl_percent','barrel_batted_rate','%','lower'),
 'avg_ev':('exit_velocity','exit_velocity_avg','mph','lower'),
 'xera':('xera','xera','ERA','lower'), 'xba':('xba','xba','rate','lower'),
 'xwoba':('xwoba','xwoba','rate','lower')}


def specs(category):
    if category not in ('hitting','pitching'):
        raise ValueError('rank_identity_error')
    return HITTING if category=='hitting' else PITCHING


def local_percentile(value, population, direction):
    """100*(average_rank-1)/(N-1), ties average; all tied -> 50; N<2 -> N/A."""
    valid=[v for raw in population if (v:=number(raw)) is not None]
    value=number(value)
    if value is None or len(valid)<2 or value not in valid or direction not in ('higher','lower'):
        return None
    less=sum(v<value for v in valid)
    equal=sum(v==value for v in valid)
    rank=100*(less+(equal-1)/2)/(len(valid)-1)
    return 100-rank if direction=='lower' else rank


def validate_bundle(bundle):
    specs(bundle['category'])
    if bundle.get('game_type')!='R':
        raise ValueError('rank_identity_error')
    for key in ('official','raw'):
        table=bundle.get(key)
        if table and (table['season']!=bundle['season'] or table['category']!=bundle['category'] or table.get('game_type')!='R'):
            raise ValueError('rank_identity_error')
    contact=bundle.get('contact')
    if contact and (contact['season']!=bundle['season'] or contact['category']!=bundle['category']):
        raise ValueError('rank_identity_error')


def raw_values(bundle):
    validate_bundle(bundle)
    raw=(bundle.get('raw') or {}).get('players',{})
    contact={}
    for row in (bundle.get('contact') or {}).get('rows',[]):
        text=str(row.get('player_id',''))
        if not text.isdigit() or int(text)<=0 or int(text) in contact:
            raise ValueError('rank_identity_error')
        contact[int(text)]=row
    def valid(value,unit):
        value=number(value)
        return value if value is not None and value>=0 and (unit!='%' or value<=100) else None
    return {pid:{key:valid(contact.get(pid,{}).get('max_hit_speed') if key=='max_ev' else raw.get(pid,{}).get(field),unit)
                 for key,(_,field,unit,_) in specs(bundle['category']).items()} for pid in set(raw)|set(contact)}


def profile(bundle,player_id,mode='official'):
    validate_bundle(bundle)
    if mode not in ('official','local'):
        raise ValueError('rank_identity_error')
    values=raw_values(bundle)
    raw=(bundle.get('raw') or {}).get('players',{})
    official=(bundle.get('official') or {}).get('players',{})
    threshold=MIN_PLAYING_TIME[bundle['category']]
    eligible={pid:row for pid,row in raw.items() if number(row.get('pa')) is not None and number(row['pa'])>=threshold}
    result={}
    for key,(field,raw_field,unit,direction) in specs(bundle['category']).items():
        actual=values.get(player_id,{}).get(key)
        if mode=='official':
            percentile=number(official.get(player_id,{}).get(field))
            if percentile is not None and not 0<=percentile<=100:
                raise ValueError('rank_schema_error')
            n=sum(number(row.get(field)) is not None for row in official.values())
            status='published' if percentile is not None else 'not_published_or_unqualified'
        else:
            population=[values.get(pid,{}).get(key) for pid in eligible]
            n=sum(v is not None for v in population)
            percentile=local_percentile(actual,population,direction) if player_id in eligible else None
            status='available' if percentile is not None else 'unqualified_missing_or_insufficient'
        result[key]={'percentile':percentile,'actual':actual,'unit':unit,'direction':direction,'population_n':n,
                     'status':status,'classification':'source_published' if mode=='official' else 'locally_calculated',
                     'season':bundle['season'],'category':bundle['category'], 'player_id':player_id,
                     'source':(bundle.get('official' if mode=='official' else 'raw') or {}).get('source'),
                     'retrieved_at':(bundle.get('official' if mode=='official' else 'raw') or {}).get('retrieved_at'),
                     'actual_source':(bundle.get('contact' if key=='max_ev' else 'raw') or {}).get('source')}
    return {'player_id':player_id,'season':bundle['season'],'category':bundle['category'],'mode':mode,
            'metrics':result,'minimum_pa_or_bf':threshold if mode=='local' else None,
            'qualification':'source-published per metric; general core rule 2.1 PA/team game for hitters, 1.25 BF/team game for pitchers; supplementary metrics may differ' if mode=='official' else f'app minimum {threshold} '+('PA' if bundle['category']=='hitting' else 'BF'),
            'method':'source values unchanged, including favorable direction' if mode=='official' else '100*(average_rank-1)/(N-1); lower direction inverted; ties averaged; N<2 unavailable; contextual spin not ranked'}
