"""Process-lifetime observations; reset on restart or explicit developer reset."""
from collections import Counter
from threading import Lock
import time

_lock = Lock()
_counts = Counter()
_started = time.time()
_duration = 0.
_db_error = False


def record(event, duration=0.):
    global _duration, _db_error
    with _lock:
        _counts[event] += 1
        if event == 'source_success' or event == 'source_error':
            _duration += duration
        if event == 'database_error':
            _db_error = True


def snapshot():
    with _lock:
        count = _counts['source_success'] + _counts['source_error']
        accesses = _counts['persistent_hit'] + _counts['persistent_miss']
        total = accesses + _counts['memory_hit']
        return dict(_counts, started_at=_started, database_error=_db_error,
                    hit_rate=_counts['persistent_hit']/accesses if accesses else None,
                    overall_hit_rate=(_counts['persistent_hit']+_counts['memory_hit'])/total if total else None,
                    average_source_seconds=_duration/count if count else None)


def reset():
    global _started, _duration, _db_error
    with _lock:
        _counts.clear()
        _started, _duration, _db_error = time.time(), 0., False
