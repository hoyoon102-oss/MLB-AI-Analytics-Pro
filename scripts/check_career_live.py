"""Real career service validation; no user data changes or pitch-event downloads."""
import json
from utils.paths import PROJECT_ROOT
from services.career_stats_service import fetch_career,load_contexts
from services.season_selection import current_date
from analytics.pitching import innings_to_outs
from analytics.career_trends import development

def main():
    evidence=[]
    for pid,category in [(660271,'hitting'),(660271,'pitching'),(592450,'hitting'),(477132,'pitching'),
                         (669373,'pitching'),(694973,'pitching'),(405395,'hitting')]:
        c=fetch_career(pid,category,current_date().isoformat())
        if not c['records'] or c['problems']:
            raise RuntimeError('Career validation failed: '+str(c['problems']))
        if category=='pitching':
            summed=sum(innings_to_outs(r['inningsPitched']) for r in c['records'].values() if r)
            if summed!=innings_to_outs(c['career_totals']['inningsPitched']):
                raise RuntimeError('Career outs do not reconcile with season totals')
        elif sum(r['hits'] for r in c['records'].values() if r)!=c['career_totals']['hits']:
            raise RuntimeError('Career hits do not reconcile with season totals')
        print(f'PASS: MLBAM {pid}, {category}, {c["first_season"]}-{c["last_season"]}, {c["played_seasons"]} played seasons')
        if pid==405395 and len(c['teams'].get(2021,[]))!=2:
            raise RuntimeError('Traded-season affiliations not preserved')
        evidence.append(c)
    context=load_contexts([2021,2022,2024],'pitching',669373,include_league=True)
    skubal=next(c for c in evidence if c['player_id']==669373)
    if context['errors']:
        raise RuntimeError('League context check failed: '+str(context['errors']))
    print('PASS: verified historical MLB league context for 2021, 2022, 2024')
    (PROJECT_ROOT/'docs/career-live-evidence.json').write_text(json.dumps({'careers':evidence,
        'league_context':context,'development_example':development(skubal['records'],'pitching',context['leagues'],skubal['incomplete'])},indent=2),encoding='utf-8')

if __name__=='__main__':main()
