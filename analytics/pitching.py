"""Pitching metrics: baseball IP notation is never treated as a decimal."""
import math
import re

PITCHING_METRICS = {
    "ERA · 평균자책점": "era", "WHIP · 이닝당 출루 허용": "whip",
    "W · 승": "wins", "L · 패": "losses", "SO · 탈삼진": "strikeOuts",
    "IP · 투구 이닝": "inningsPitched", "BB · 볼넷 허용": "baseOnBalls",
    "H · 피안타": "hits", "HR · 피홈런": "homeRuns", "GS · 선발 등판": "gamesStarted",
    "SV · 세이브": "saves", "K/9 · 9이닝당 탈삼진": "strikeoutsPer9Inn",
    "BB/9 · 9이닝당 볼넷": "walksPer9Inn", "K/BB · 탈삼진/볼넷": "strikeoutWalkRatio",
}
PITCH_HISTORY_KEYS = ("era", "whip", "strikeOuts", "inningsPitched", "strikeoutsPer9Inn")
PITCH_COMPARE_KEYS = ("era", "whip", "strikeOuts", "inningsPitched", "strikeoutsPer9Inn", "walksPer9Inn")


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def innings_to_outs(value):
    """6.1 -> 19 outs; reject 6.3 and ambiguous fractional notation."""
    if value is None or isinstance(value, bool):
        return None
    match = re.fullmatch(r"(\d+)(?:\.([012]))?", str(value).strip())
    if not match:
        return None
    return int(match[1]) * 3 + int(match[2] or 0)


def outs_to_innings(outs):
    return f"{outs // 3}.{outs % 3}"


def pitching_stats(stats):
    """Retain valid API rates; derive missing rates only with valid denominators."""
    result = dict(stats)
    derived = []
    outs = innings_to_outs(stats.get("inningsPitched"))
    if outs is None:
        raw_outs = number(stats.get("outs"))
        if raw_outs is not None and raw_outs.is_integer():
            outs = int(raw_outs)
            derived.append("inningsPitched")
    result["inningsPitched"] = outs_to_innings(outs) if outs is not None else None
    result["_outs"] = outs
    ip = outs / 3 if outs is not None else None
    so, bb, hits, er = (number(stats.get(key)) for key in
                        ("strikeOuts", "baseOnBalls", "hits", "earnedRuns"))
    formulas = {
        "era": (er * 9 / ip if er is not None and ip else None),
        "whip": ((bb + hits) / ip if bb is not None and hits is not None and ip else None),
        "strikeoutsPer9Inn": (so * 9 / ip if so is not None and ip else None),
        "walksPer9Inn": (bb * 9 / ip if bb is not None and ip else None),
        "strikeoutWalkRatio": (so / bb if so is not None and bb else None),
    }
    for key, calculated in formulas.items():
        value = stats.get(key)
        if (key != "strikeoutWalkRatio" and outs == 0) or (key == "strikeoutWalkRatio" and bb == 0):
            result[key] = None
        elif number(value) is not None:
            result[key] = value
        elif calculated is not None:
            result[key] = f"{calculated:.2f}"
            derived.append(key)
        else:
            result[key] = None
    result["_derived"] = derived
    result["_group"] = "pitching"
    return result


def chart_value(stats, key):
    if key == "inningsPitched":
        outs = innings_to_outs((stats or {}).get(key))
        return outs / 3 if outs is not None else None
    return number((stats or {}).get(key))
