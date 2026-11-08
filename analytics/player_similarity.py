"""Equal-weight, population-standardized RMS distance; no predictions or imputation."""
import numpy as np
from analytics.percentiles import MIN_PLAYING_TIME, raw_values, validate_bundle
from analytics.statcast_hitting import number

FEATURES=('avg_ev','bb','k')


def similar_players(bundle,player_id,top=5):
    validate_bundle(bundle)
    if top not in (5,10):
        raise ValueError('rank_identity_error')
    raw=(bundle.get('raw') or {}).get('players',{})
    values=raw_values(bundle)
    threshold=MIN_PLAYING_TIME[bundle['category']]
    eligible=[pid for pid in sorted(raw) if number(raw[pid].get('pa')) is not None and number(raw[pid]['pa'])>=threshold
              and all(values.get(pid,{}).get(k) is not None for k in FEATURES)]
    result={'player_id':player_id,'season':bundle['season'],'category':bundle['category'],'game_type':'R',
            'minimum_pa_or_bf':threshold,'eligible_n':len(eligible),'excluded_n':len(raw)-len(eligible),
            'features':list(FEATURES),'weights':{k:1/len(FEATURES) for k in FEATURES},
            'method':'population z-score (ddof=0); distance=sqrt(mean((z_candidate-z_target)^2)); score=1/(1+distance), not probability',
            'source':(bundle.get('raw') or {}).get('source'),'retrieved_at':(bundle.get('raw') or {}).get('retrieved_at'),
            'results':[],'status':'available'}
    if player_id not in eligible or len(eligible)<2:
        return dict(result,status='unqualified_missing_or_insufficient')
    matrix=np.asarray([[values[pid][k] for k in FEATURES] for pid in eligible],dtype=float)
    means=matrix.mean(axis=0)
    std=matrix.std(axis=0,ddof=0)
    if np.any(std==0):
        # Keep the fixed model explicit; never silently drop/reweight constant features.
        return dict(result,status='constant_feature')
    z=(matrix-means)/std
    index=eligible.index(player_id)
    distance=np.sqrt(np.mean((z-z[index])**2,axis=1))
    result.update(means=dict(zip(FEATURES,means.tolist())),std=dict(zip(FEATURES,std.tolist())),
                  target_values=values[player_id],target_z=dict(zip(FEATURES,z[index].tolist())))
    for i in sorted(range(len(eligible)),key=lambda i:(float(distance[i]),eligible[i])):
        pid=eligible[i]
        if pid==player_id:
            continue
        metadata=bundle.get('metadata',{}).get(pid,{})
        source=raw[pid]
        name=metadata.get('fullName') or source.get('last_name, first_name') or str(pid)
        result['results'].append({'player':{'id':pid,'fullName':name},'teams':metadata.get('teams',[]),
                                  'positions':metadata.get('positions',[]),'multiple_teams':metadata.get('multiple_teams',False),
                                  'season':bundle['season'],'distance':float(distance[i]),'score':1/(1+float(distance[i])),
                                  'values':{k:values[pid][k] for k in FEATURES},'z':dict(zip(FEATURES,z[i].tolist())),
                                  'differences':{k:values[pid][k]-values[player_id][k] for k in FEATURES}})
        if len(result['results'])==top:
            break
    return result


def ai_context(player,percentiles,similarity):
    if any(p['player_id']!=player['id'] for p in (percentiles,similarity)) or any(
        percentiles[k]!=similarity[k] for k in ('season','category')):
        raise ValueError('rank_identity_error')
    return {'player':{'id':player['id'],'name':player['fullName']},'season':percentiles['season'],
            'category':percentiles['category'],'mode':'Percentiles and similarity',
            'statistics':{k:v['actual'] for k,v in percentiles['metrics'].items()},
            'percentiles':percentiles,'similarity':similarity,
            'limitations':['Source-published percentiles and local ranks are distinct; qualification varies by metric.',
                          'Similarity is a statistical profile distance, not probability, quality ranking or future prediction.',
                          'Only the defined same-season, same-category reference population is used.',
                          'Three equal-weight features; no outcome guarantees or causal claims; missing values are unknown.']}
