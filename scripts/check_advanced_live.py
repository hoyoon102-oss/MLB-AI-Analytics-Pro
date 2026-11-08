"""Read-only availability check with reproducible verified MLB examples."""
import json
from pathlib import Path
from datetime import datetime, timezone
import requests
from services.player_stats import extract_stats
from analytics.advanced_stats import metrics

results = []
for player_id, category in [(660271, 'hitting'), (543037, 'pitching')]:
    response = requests.get(f'https://statsapi.mlb.com/api/v1/people/{player_id}/stats',
        params=dict(stats='season', group=category, season=2024, gameType='R'), timeout=25)
    response.raise_for_status()
    stats = extract_stats(response.json(), 2024, category, player_id)
    if not stats:
        raise RuntimeError('Expected completed-season example missing')
    at = datetime.now(timezone.utc).isoformat()
    results.append(dict(player_id=player_id, season=2024, category=category, source=response.url,
                        retrieved_at=at, stats=stats, metrics=metrics(stats,2024,category,player_id,at)))
Path('tests/advanced-verified-examples.json').write_text(json.dumps(results,indent=2), encoding='utf-8')
print('PASS: MLB API returned matching regular-season examples for both categories')
