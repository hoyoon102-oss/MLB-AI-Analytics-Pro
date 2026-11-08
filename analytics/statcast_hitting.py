"""Tracked-subset summaries, separated from source-published full-season values."""
from collections import Counter
import math


def number(value):
    if isinstance(value,bool):
        return None
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):
        return None


def values(rows, field):
    return [v for row in rows if (v := number(row.get(field))) is not None]


def measured(v, unit, n, denominator, method, numerator=None):
    return {'value':v,'unit':unit,'n':n,'denominator':denominator,'method':method,
            'numerator':numerator,'classification':'locally_calculated'}


def mean_metric(rows, field, unit, denominator, scale=1, maximum=False):
    v = values(rows,field)
    return measured((max(v) if maximum else sum(v)/len(v))*scale if v else None,
                    unit,len(v),denominator,('max' if maximum else 'mean')+'('+field+')'+f' * {scale}')


def batted(rows):
    return [r for r in rows if r.get('type') == 'X']


def hitting_summary(rows):
    bbe = batted(rows)
    ev = values(bbe,'launch_speed')
    la = values(bbe,'launch_angle')
    zones = [v for v in values(bbe,'launch_speed_angle') if v in (1,2,3,4,5,6)]
    hard, sweet, barrel = sum(v >= 95 for v in ev), sum(8 <= v <= 32 for v in la), zones.count(6)
    return {'pitches':len(rows),'bbe':len(bbe),'metrics':{
        'avg_ev':mean_metric(bbe,'launch_speed','mph','BBE with non-null launch_speed'),
        'max_ev':mean_metric(bbe,'launch_speed','mph','BBE with non-null launch_speed',maximum=True),
        'avg_la':mean_metric(bbe,'launch_angle','deg','BBE with non-null launch_angle'),
        'hard_hit':measured(hard/len(ev)*100 if ev else None,'%',len(ev),'BBE with non-null launch_speed','100 * count(EV >= 95 mph) / valid EV BBE',hard),
        'sweet_spot':measured(sweet/len(la)*100 if la else None,'%',len(la),'BBE with non-null launch_angle','100 * count(8 <= LA <= 32 degrees) / valid LA BBE',sweet),
        'barrel':measured(barrel/len(zones)*100 if zones else None,'%',len(zones),'BBE with source launch_speed_angle in 1..6','100 * count(source launch_speed_angle == 6) / classified BBE',barrel)},
        'breakdown':dict(Counter(r.get('bb_type') or 'unknown' for r in bbe)),
        'launch_angle_distribution':{'n':len(la),'below_0':sum(v<0 for v in la),
            '0_to_below_8':sum(0<=v<8 for v in la),'8_to_32':sum(8<=v<=32 for v in la),
            'above_32':sum(v>32 for v in la)}}


def monthly_summary(rows):
    months = sorted({r['game_date'][:7] for r in rows})
    return {month:hitting_summary([r for r in rows if r['game_date'].startswith(month)]) for month in months}


CONTACT_FIELDS = {'avg_ev':('avg_hit_speed','mph'),'max_ev':('max_hit_speed','mph'),
                  'avg_la':('avg_hit_angle','deg'),'hard_hit':('ev95percent','%'),
                  'barrel':('brl_percent','%'),'sweet_spot':('anglesweetspotpercent','%')}
EXPECTED_FIELDS = {'xba':('est_ba','rate'),'xslg':('est_slg','rate'),'xwoba':('est_woba','rate'),'xera':('xera','ERA')}


def published_metrics(published):
    result = {}
    for key,(field,unit) in {**CONTACT_FIELDS,**EXPECTED_FIELDS}.items():
        if published['category'] == 'hitting' and key == 'xera':
            continue
        if published['category'] == 'pitching' and key != 'xera':
            continue
        table = published.get('tables',{}).get('contact' if key in CONTACT_FIELDS else 'expected',{})
        row = table.get('row',{})
        result[key] = {'value':number(row.get(field)), 'unit':unit,
                       'n':number(row.get('attempts' if key in CONTACT_FIELDS else 'pa')),
                       'bip':number(row.get('bip')), 'denominator':'published BBE' if key in CONTACT_FIELDS else 'published PA (BIP separately reported)',
                       'method':'source column '+field,'classification':'source_published',
                       'source':table.get('source'), 'retrieved_at':table.get('retrieved_at'),
                       'season':published['season'],'scope':'published_full_season',
                       'availability':'available' if number(row.get(field)) is not None else 'unavailable'}
    return result
