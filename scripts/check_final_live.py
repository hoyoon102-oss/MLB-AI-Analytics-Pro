"""Small final checks; no inference, personal files, or persistent cache writes."""
import json
import os
from datetime import datetime, timezone


def main():
    os.environ['MLB_CACHE_DISABLED'] = '1'
    os.environ['MLB_ANALYTICS_MODE'] = 'LOCAL'
    from services.player_stats import search_players
    from services.statcast_service import fetch_period
    from utils.paths import PROJECT_ROOT
    results = []
    for name, check in [('player_search', lambda: any(p['id'] == 660271 for p in search_players('Shohei Ohtani'))),
                        ('statcast_single_day', lambda: len(fetch_period(660271, 2024, 'hitting', '2024-09-19', '2024-09-19')['rows']) > 0)]:
        try:
            if not check():
                raise ValueError('Expected identified player or tracking rows missing')
            results.append({'check': name, 'status': 'PASS'})
            print('PASS:', name, flush=True)
        except Exception as error:
            # Keep paths, URLs with parameters and arbitrary upstream text out of evidence.
            results.append({'check': name, 'status': 'FAILED', 'error_type': type(error).__name__})
            print('FAILED:', name, type(error).__name__, flush=True)
    target = PROJECT_ROOT / 'docs' / 'final-live-checks.json'
    target.write_text(json.dumps({'at_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'One name query and one player/day Statcast query; no persistent cache or AI generation', 'results': results}, indent=2), encoding='utf-8')
    if any(r['status'] != 'PASS' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
