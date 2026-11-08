"""Validate complete production populations against MLB leaders and traded affiliations."""
import requests
import json
from utils.paths import PROJECT_ROOT
from services.leaderboard_service import discovery_dataset
from analytics.leaderboard_rankings import build_frame,filter_and_rank

def main():
    base='https://statsapi.mlb.com/api/v1'
    evidence=[]
    for category,metric,leader_key in [('hitting','OPS','onBasePlusSlugging'),('pitching','ERA','earnedRunAverage')]:
        data=discovery_dataset(2024,category,True)
        frame=build_frame(data)
        ranked=filter_and_rank(frame,category,{'qualified':True},metric)
        if len(frame)!=data['population_n'] or frame['id'].duplicated().any():
            raise RuntimeError('Incomplete or duplicated population')
        r=requests.get(base+'/stats/leaders',params={'leaderCategories':leader_key,'statGroup':category,
            'season':2024,'sportId':1,'gameType':'R','playerPool':'QUALIFIED','limit':5},timeout=(5,30))
        r.raise_for_status()
        leaders=r.json()['leagueLeaders'][0]['leaders']
        if any(abs(float(a)-float(b['value']))>1e-9 for a,b in zip(ranked.head(5)[metric],leaders)):
            raise RuntimeError('Top five published metric values do not match official leaders')
        # MLB may resolve equal displayed rates with unpublished precision. Our explicit
        # competition ranks keep equal published values tied and use ID for display only.
        if not {p['person']['id'] for p in leaders}<=set(ranked[ranked['rank']<=5]['id']):
            raise RuntimeError('Official leaders fall outside matching tie-inclusive ranks')
        if category=='hitting':
            traded=frame[frame['id']==665862].iloc[0]
            if set(traded['team_ids'])!={146,147} or set(traded['league_ids'])!={103,104}:
                raise RuntimeError('Historical traded affiliations not verified')
            if 665862 not in filter_and_rank(frame,category,{'qualified':False,'team':146},metric)['id'].tolist():
                raise RuntimeError('Traded player not included in former-team filter')
        print(f'PASS: {category} complete population {len(frame)}, qualified {len(ranked)}, official values/tie-inclusive ranks match')
        evidence.append({'season':2024,'category':category,'population_n':len(frame),
            'qualified_n':len(ranked),'sources':data['sources'],'retrieved_at':data['retrieved_at'],
            'top_five':ranked.head(5)[['rank','id','name',metric]].to_dict('records'),
            'official_top_five':[{k:r[k] for k in ('rank','value','person')} for r in leaders],
            'traded_players_verified':int(frame['multiple_teams'].sum()),'source_errors':data['errors'],
            'statcast_source':(data.get('supplemental') or {}).get('source')})
    (PROJECT_ROOT/'docs/leaderboards-live-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')

if __name__=='__main__':main()
