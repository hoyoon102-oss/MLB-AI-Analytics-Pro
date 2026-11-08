"""Optional real MLB API validation; stores no player histories locally."""
import requests

from services.player_stats import search_players
from components.awards import fetch_awards, normalize_awards, category_counts, season_awards
from services.player_detection import fetch_profile
from components.profile_ui import fetch_headshot


def main():
    for name in ('Shohei Ohtani', 'Aaron Judge', 'Clayton Kershaw', 'Tarik Skubal'):
        matches = [p for p in search_players(name) if p['fullName'].casefold() == name.casefold()]
        assert len(matches) == 1, (name, 'ambiguous exact-name search')
        player_id = matches[0]['id']
        response = requests.get(f'https://statsapi.mlb.com/api/v1/people/{player_id}/awards', timeout=20)
        response.raise_for_status()
        payload = response.json()
        result = fetch_awards(player_id)
        assert not result['invalid'], (name, result['invalid'])
        doubled = normalize_awards({'awards': payload['awards'] * 2}, player_id)
        counts = category_counts(result['records'])
        assert counts == category_counts(doubled['records'])
        assert len(result['records']) == len(doubled['records'])
        for codes, category in [({'ALMVP', 'NLMVP'}, 'MVP'), ({'ALCY', 'NLCY'}, '사이영상')]:
            expected = {(a['id'], a['season']) for a in payload['awards'] if a.get('id') in codes}
            assert counts.get(category, 0) == len(expected), (name, category)
        assert counts.get('올스타 선정 시즌', 0) == len({a['season'] for a in payload['awards'] if a.get('id') in {'ALAS', 'NLAS'}})
        assert all(a['season'] == 2024 for a in season_awards(result['records'], 2024))
        assert all(a['id'] != 'WSCHAMP' for a in result['records'])
        profile = fetch_profile(player_id)
        assert profile['fullName'] == name
        image = fetch_headshot(player_id)
        print('PASS:', name, 'ID', player_id, 'API records', result['received'], 'displayed', len(result['records']),
              'major counts', counts, 'headshot', 'available' if image else 'placeholder', flush=True)
    print('PASS: four live players, IDs, profiles, deduplication, career totals and season filters', flush=True)


if __name__ == '__main__':
    main()
