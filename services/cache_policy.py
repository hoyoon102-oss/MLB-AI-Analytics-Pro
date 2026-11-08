"""Conservative calendar fallback: same-year seasons stay short-lived all year."""
from datetime import date
import os


def season_state(season, today=None):
    today = today or date.today()
    if season is None:
        return 'metadata'
    season = int(season)
    return 'completed' if season < today.year else 'upcoming' if season > today.year else 'active'


def ttl(namespace, season=None, today=None):
    state = season_state(season, today)
    kind = 'historical' if state == 'completed' else 'active'
    if namespace in ('profile', 'team_profile', 'teams', 'awards', 'calendar'):
        kind = 'metadata'
    defaults = {'historical': 30*86400, 'metadata': 86400, 'active': 900}
    # Keep a margin beyond the 60-second L1 cache lifetime.
    try:
        return max(900, int(os.environ.get('MLB_CACHE_TTL_' + kind.upper(), defaults[kind])))
    except (ValueError, TypeError):
        return defaults[kind]
