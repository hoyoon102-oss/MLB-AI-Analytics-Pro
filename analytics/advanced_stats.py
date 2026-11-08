"""Provenance and matching shared by UI and AI."""
from analytics.advanced_hitting import hitting_metrics
from analytics.advanced_pitching import pitching_metrics
from analytics.advanced_stats_sources import CONSTANTS_SOURCE, REVIEWED_AT, seasonal_constants

METHODS = {
    'ISO': 'SLG - AVG (exact H/AB and TB/AB when available)',
    'BABIP': '(H-HR)/(AB-SO-HR+SF)', 'BB%': '100*BB/PA (hitting) or 100*BB/BF (pitching)',
    'K%': '100*SO/PA (hitting) or 100*SO/BF (pitching)', 'BB/K': 'BB/SO',
    'K-BB%': 'K% - BB%', 'K/9': '27*SO/outs', 'BB/9': '27*BB/outs',
    'HR/9': '27*HR/outs', 'K/BB': 'SO/BB',
    'FIP': '3*(13*HR+3*(BB+HBP)-2*SO)/outs + season cFIP',
    'wOBA': '(wBB*(BB-IBB)+wHBP*HBP+w1B*1B+w2B*2B+w3B*3B+wHR*HR)/(AB+BB-IBB+SF+HBP)',
    'OPS+': 'Requires verified source-published park-adjusted OPS+',
    'wRC+': 'Requires verified league run environment and park adjustments',
    'ERA+': 'Requires verified source-published park-adjusted ERA+',
}


def metrics(stats, season, category, player_id=None, retrieved_at=None):
    if category not in ('hitting', 'pitching') or (stats and stats.get('_group', category) != category):
        raise ValueError('Category mismatch')
    values = (hitting_metrics if category == 'hitting' else pitching_metrics)(stats, season)
    source = f'https://statsapi.mlb.com/api/v1/people/{player_id}/stats' if player_id else 'https://statsapi.mlb.com/api/v1/teams/stats'
    return {key: {'name': key, 'value': value, 'season': int(season), 'category': category,
                  'player_id': player_id, 'game_type': 'R', 'source': source,
                  'method': METHODS[key], 'classification': 'locally_calculated' if value is not None else 'unavailable',
                  'retrieved_at': retrieved_at, 'availability': 'available' if value is not None else 'unavailable',
                  'reason': None if value is not None else ('park_adjustment_unavailable' if key.endswith('+') else 'missing_inputs_or_season_constants_or_invalid_denominator'),
                  'constants': {'source': CONSTANTS_SOURCE, 'reviewed_at': REVIEWED_AT, 'season': int(season),
                                'values': seasonal_constants(season)} if key in ('FIP', 'wOBA') else None}
            for key, value in values.items()}


def baselines(league, season, category):
    result = {key: {'value': 100., 'kind': 'park_adjusted_reference', 'source': METHODS[key]}
              for key in (('OPS+', 'wRC+') if category == 'hitting' else ('ERA+',))}
    if league and league.get('season') == int(season) and league.get('category') == category and league.get('game_type', 'R') == 'R':
        totals = dict(league['totals'])
        if category == 'pitching' and totals.get('outs') is not None:
            outs = int(totals['outs'])
            totals['inningsPitched'] = f'{outs//3}.{outs%3}'
        for key, item in metrics(totals, season, category, retrieved_at=league.get('retrieved_at')).items():
            if not key.endswith('+'):
                result[key] = {'value': item['value'], 'kind': 'league_average', 'source': league.get('source'),
                               'league_id': league.get('league_id'), 'season': int(season), 'retrieved_at': league.get('retrieved_at')}
    return result


def attach_context(context, stats, league=None):
    advanced = metrics(stats, context['season'], context['category'], context['player']['id'], context['retrieved_at'])
    baseline = baselines(league, context['season'], context['category'])
    return dict(context, advanced_statistics=advanced, advanced_baselines=baseline,
                advanced_differences={k: item['value']-baseline[k]['value'] for k, item in advanced.items()
                                      if item['value'] is not None and baseline.get(k, {}).get('value') is not None})
