"""Pure calculations. Missing inputs are never assumed to be zero."""
from analytics.pitching import number
from analytics.advanced_stats_sources import seasonal_constants


def ratio(a, b, scale=1):
    return a / b * scale if a is not None and b is not None and b > 0 else None


def hitting_metrics(stats, season):
    s = stats or {}
    h, hr, ab, so, sf, bb, pa = [number(s.get(k)) for k in
        ('hits', 'homeRuns', 'atBats', 'strikeOuts', 'sacFlies', 'baseOnBalls', 'plateAppearances')]
    avg, slg = number(s.get('avg')), number(s.get('slg'))
    # Prefer exact counts when available; rounded API rates are fallback inputs.
    tb = number(s.get('totalBases'))
    if h is not None and ab is not None:
        avg = ratio(h, ab)
    if tb is not None and ab is not None:
        slg = ratio(tb, ab)
    babip = ratio(h - hr, ab - so - hr + sf) if all(v is not None for v in (h, hr, ab, so, sf)) and h >= hr else None
    result = {'OPS+': None, 'wRC+': None, 'wOBA': None,
              'ISO': slg - avg if slg is not None and avg is not None and slg >= avg else None,
              'BABIP': babip if babip is None or 0 <= babip <= 1 else None,
              'BB%': ratio(bb, pa, 100), 'K%': ratio(so, pa, 100), 'BB/K': ratio(bb, so)}
    c = seasonal_constants(season)
    ibb, hbp, doubles, triples = [number(s.get(k)) for k in ('intentionalWalks', 'hitByPitch', 'doubles', 'triples')]
    if c and all(v is not None for v in (h, hr, ab, sf, bb, ibb, hbp, doubles, triples)):
        singles = h - doubles - triples - hr
        if singles >= 0 and bb >= ibb:
            result['wOBA'] = ratio(sum(w * v for w, v in zip(c[:6], (bb-ibb, hbp, singles, doubles, triples, hr))), ab+bb-ibb+sf+hbp)
    return result
