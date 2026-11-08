"""Observed pitch classifications and denominator-explicit arsenal metrics."""
from analytics.statcast_hitting import number, mean_metric, measured

WHIFFS = {'swinging_strike','swinging_strike_blocked','missed_bunt','swinging_pitchout'}
SWINGS = WHIFFS | {'foul','foul_tip','hit_into_play','foul_bunt','bunt_foul_tip','swinging_pitchout','foul_pitchout'}


def pitching_summary(rows):
    swings = sum(r.get('description') in SWINGS for r in rows)
    whiffs = sum(r.get('description') in WHIFFS for r in rows)
    return {'pitches':len(rows),'metrics':{
        'velocity':mean_metric(rows,'release_speed','mph','pitches with non-null release_speed'),
        'max_velocity':mean_metric(rows,'release_speed','mph','pitches with non-null release_speed',maximum=True),
        'spin':mean_metric(rows,'release_spin_rate','rpm','pitches with non-null release_spin_rate'),
        'extension':mean_metric(rows,'release_extension','ft','pitches with non-null release_extension'),
        'horizontal':mean_metric(rows,'pfx_x','in','pitches with non-null pfx_x',scale=12),
        'vertical':mean_metric(rows,'pfx_z','in','pitches with non-null pfx_z',scale=12),
        'whiff':measured(100*whiffs/swings if swings else None,'%',swings,
                         'recognized swing descriptions (includes bunt attempts)',
                         '100 * (swinging_strike + swinging_strike_blocked + missed_bunt + swinging_pitchout) / recognized swings',whiffs)},
        'swing_descriptions':sorted(SWINGS), 'whiff_descriptions':sorted(WHIFFS)}


def arsenal(rows):
    codes = sorted({r.get('pitch_type') or 'UN' for r in rows})
    result = []
    for code in codes:
        subset = [r for r in rows if (r.get('pitch_type') or 'UN') == code]
        result.append({'pitch_type':code,'pitch_name':next((r['pitch_name'] for r in subset if r.get('pitch_name')),code),
                       **pitching_summary(subset),
                       'usage':measured(len(subset)/len(rows)*100 if rows else None,'%',len(rows),
                                        'all retrieved pitches, including unknown pitch types','100 * pitch-type count / all pitches',len(subset))})
    return result


def location_summary(rows):
    pairs = [(number(r.get('plate_x')),number(r.get('plate_z'))) for r in rows]
    pairs = [(x,z) for x,z in pairs if x is not None and z is not None]
    eligible,inside = 0,0
    for row in rows:
        x,z,bottom,top = [number(row.get(k)) for k in ('plate_x','plate_z','sz_bot','sz_top')]
        if all(v is not None for v in (x,z,bottom,top)) and top > bottom:
            eligible += 1
            inside += -17/24 <= x <= 17/24 and bottom <= z <= top
    return {'valid_plate_pairs':len(pairs),'mean_plate_x_ft':sum(p[0] for p in pairs)/len(pairs) if pairs else None,
            'mean_plate_z_ft':sum(p[1] for p in pairs)/len(pairs) if pairs else None,
            'valid_batter_zone_pairs':eligible,'center_in_measured_rectangle_pct':inside/eligible*100 if eligible else None,
            'definition':'Pitch center inside 17-inch plate width and its own sz_bot/sz_top. Not an official called-strike rate.',
            'view':'catcher perspective; positive x right; 2026+ middle-of-plate, through 2025 front-of-plate'}
