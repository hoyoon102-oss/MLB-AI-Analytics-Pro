"""Pitching rates use outs, never decimal baseball innings."""
from analytics.pitching import innings_to_outs, number
from analytics.advanced_hitting import ratio
from analytics.advanced_stats_sources import seasonal_constants


def pitching_metrics(stats, season):
    s = stats or {}
    outs = innings_to_outs(s.get('inningsPitched'))
    raw = number(s.get('outs'))
    if outs is None and s.get('inningsPitched') is None and raw is not None and raw.is_integer():
        outs = int(raw)
    if raw is not None and outs != raw:
        outs = None
    hr, bb, hbp, so, bf = [number(s.get(k)) for k in ('homeRuns', 'baseOnBalls', 'hitBatsmen', 'strikeOuts', 'battersFaced')]
    k, b = ratio(so, bf, 100), ratio(bb, bf, 100)
    c = seasonal_constants(season)
    fip = ratio(13*hr + 3*(bb+hbp) - 2*so, outs, 3) if all(v is not None for v in (hr, bb, hbp, so)) else None
    h, ab, sf = [number(s.get(key)) for key in ('hits', 'atBats', 'sacFlies')]
    babip = ratio(h-hr, ab-so-hr+sf) if all(v is not None for v in (h, hr, ab, so, sf)) and h >= hr else None
    return {'ERA+': None, 'FIP': fip+c[6] if fip is not None and c else None,
            'K/9': ratio(so, outs, 27), 'BB/9': ratio(bb, outs, 27), 'HR/9': ratio(hr, outs, 27),
            'K/BB': ratio(so, bb), 'K%': k, 'BB%': b, 'K-BB%': k-b if k is not None and b is not None else None,
            'BABIP': babip if babip is None or 0 <= babip <= 1 else None}
