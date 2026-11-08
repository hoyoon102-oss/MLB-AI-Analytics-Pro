"""Offline reproducible service benchmark; fixture timings are NOT live API timings.

Run: python -m scripts.benchmark_cache --baseline .backups/v48-before-...
Each persistent-cache measurement starts a new Python process. All DBs are temporary.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time


def worker(root, phase):
    sys.path.insert(0, str(Path(root).resolve()))
    from unittest.mock import Mock, patch
    from services.player_stats import search_players, fetch_stats
    from services.leaderboard_service import recent_population
    from services.statcast_service import published_table
    from services.career_stats_service import fetch_career
    from tests.test_career_trends import hitter, payload, split
    rows = [split(2024,hitter())]
    rows[0]['player']['fullName'] = 'Fixture Player'
    responses = {
        'lookup': {'people':[{'id':1,'fullName':'Fixture Player'}]},
        'stats': {'stats':[{'group':{'displayName':'hitting'},'splits':rows}]},
        'leaderboard': {'stats':[{'group':{'displayName':'hitting'},'type':{'displayName':'season'},'splits':rows,'totalSplits':1}]},
    }
    scenarios = {
        'player_lookup': (search_players, ('Fixture',), 'lookup'),
        'player_statistics': (fetch_stats, (1,2024,'hitting'), 'stats'),
        'leaderboard': (recent_population, (2024,'hitting','ALL'), 'leaderboard'),
        'statcast_summary': (published_table, (2024,'hitting','contact'), 'stats'),
        'career': (fetch_career, (1,'hitting','2026-11-05'), 'stats'),
    }
    output = {}
    for name,(loader,args,response_kind) in scenarios.items():
        response=Mock()
        response.json.return_value=responses[response_kind]
        response.url='https://statsapi.mlb.com/api/v1/stats'
        with patch('requests.get',return_value=response) as http, \
             patch('services.statcast_service.csv_request',return_value=(['player_id'],[{'player_id':'1','year':'2024'}],'https://baseballsavant.mlb.com/leaderboard/statcast')) as csv, \
             patch('services.career_stats_service.api_json',return_value=payload(rows)) as career_api, \
             patch('services.career_stats_service.season_calendar',return_value={2024:{'regularSeasonEndDate':'2024-09-30'}}):
            started=time.perf_counter()
            result=loader(*args)
            elapsed=time.perf_counter()-started
            source_calls=http.call_count+csv.call_count+career_api.call_count
            if phase=='persistent' and source_calls:
                raise AssertionError(name+' did not survive restart')
            if result is None:
                raise AssertionError('Missing fixture result')
            entry={'seconds':elapsed,'mock_source_calls':source_calls}
            if phase=='cold':
                started=time.perf_counter()
                repeated=loader(*args)
                entry['warm_memory_seconds']=time.perf_counter()-started
                assert repeated==result
            output[name]=entry
    print(json.dumps(output))


def run_worker(root, phase, db, disabled=False):
    env=dict(os.environ,MLB_ANALYTICS_DB_PATH=str(db),MLB_CACHE_DISABLED='1' if disabled else '0')
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker','--root',str(root),'--phase',phase],
                          env=env,capture_output=True,text=True,check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--phase',default='cold')
    parser.add_argument('--baseline')
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--output',default='docs/v48-benchmark.json')
    args=parser.parse_args()
    if args.worker:
        worker(args.root,args.phase)
        return
    observations={'v48_cold':[],'v48_restart':[],'baseline_cold':[]}
    with tempfile.TemporaryDirectory() as temporary:
        for index in range(args.runs):
            db=Path(temporary)/f'run{index}.db'
            observations['v48_cold'].append(run_worker(args.root,'cold',db))
            observations['v48_restart'].append(run_worker(args.root,'persistent',db))
            if args.baseline:
                observations['baseline_cold'].append(run_worker(args.baseline,'cold',db,True))
    medians={}
    for mode,runs in observations.items():
        if not runs:
            continue
        medians[mode]={name:{'median_seconds':statistics.median(r[name]['seconds'] for r in runs),
                             'mock_source_calls':[r[name]['mock_source_calls'] for r in runs],
                             **({'median_memory_seconds':statistics.median(r[name]['warm_memory_seconds'] for r in runs)} if mode.endswith('cold') else {})}
                       for name in runs[0]}
    report=dict(conditions='Offline fixed fixtures; source latency is not simulated. Three separate processes per phase; temporary databases. Excludes UI rendering and live network latency.',
                python=sys.version,runs=args.runs,medians=medians,observations=observations)
    Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(medians,indent=2))


if __name__=='__main__':
    main()
