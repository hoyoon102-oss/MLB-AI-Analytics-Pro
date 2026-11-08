"""Existing standard hitting labels and finite-number conversion."""
import math
RATE_KEYS = ("avg", "obp", "slg", "ops")

METRICS = {"AVG": "avg", "OBP": "obp", "SLG": "slg", "OPS": "ops", "홈런 (HR)": "homeRuns", "타점 (RBI)": "rbi"}

def numeric(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None

