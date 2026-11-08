"""Check source-published 2024 examples and real similarity populations."""
import json
from utils.paths import PROJECT_ROOT
from services.leaderboard_service import load_boards
from analytics.percentiles import profile
from analytics.player_similarity import similar_players


def main():
    evidence=[]
    for category,pid,expected in [('hitting',660271,{'k':44,'hard_hit':100,'xwoba':99}),
                                  ('pitching',694973,{'k':95,'xera':97,'fb_velocity':99})]:
        bundle=load_boards(2024,category)
        if not bundle['official'] or not bundle['raw']:
            raise RuntimeError(str(bundle['errors']))
        official=profile(bundle,pid)
        for key,value in expected.items():
            if official['metrics'][key]['percentile']!=value:
                raise RuntimeError('Published example differs from verified CSV probe: '+key)
        similar=similar_players(bundle,pid)
        if similar['status']!='available' or len(similar['results'])!=5 or any(r['player']['id']==pid for r in similar['results']):
            raise RuntimeError('Real population similarity validation failed')
        evidence.append({'official_profile':official,'local_profile':profile(bundle,pid,'local'),
                         'similarity':similar,'source_errors':bundle['errors']})
        print(f'PASS: {category} MLBAM {pid}; verified published percentiles; qualified similarity population {similar["eligible_n"]}')
        print('Nearest:',[(r['player']['fullName'],round(r['score'],4)) for r in similar['results']])
    (PROJECT_ROOT/'docs/rankings-live-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
