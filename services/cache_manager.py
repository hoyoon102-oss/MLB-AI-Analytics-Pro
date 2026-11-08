"""Persist validated service results without modifying their values or formulas."""
from functools import wraps
from inspect import signature
import hashlib
import json
import math
import os
import sqlite3
import time
import threading
from services.database import connection
from utils.config import cloud
from services.cache_policy import ttl
from analytics.performance_monitor import record

_local = threading.local()
_metadata = {}
_metadata_lock = threading.Lock()


def begin_view():
    _local.view = []


def view_status():
    return list(getattr(_local, 'view', []))


def cache_key(function, scope):
    encoded = json.dumps(pack(scope), sort_keys=True, allow_nan=False)
    return hashlib.sha256((function.__module__ + '.' + function.__name__ + ':v1:' + encoded).encode()).hexdigest()


def note(key, namespace, source, retrieved, expires, mode):
    _local.serial = getattr(_local, 'serial', 0) + 1
    with _metadata_lock:
        if len(_metadata) >= 2048:
            _metadata.clear()
        _metadata[key] = dict(dataset=namespace, source=source, retrieved_at=retrieved,
                              expires_at=expires, mode=mode)


def observe(function):
    """Outside Streamlit's decorator: observe memory hits without database I/O."""
    sig = signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        if os.environ.get('MLB_CACHE_DISABLED') == '1' or cloud():
            return function(*args, **kwargs)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        key = cache_key(function, dict(bound.arguments))
        serial = getattr(_local, 'serial', 0)
        result = function(*args, **kwargs)
        memory = serial == getattr(_local, 'serial', 0)
        if memory:
            record('memory_hit')
        with _metadata_lock:
            item = dict(_metadata.get(key, {}))
        if item:
            if memory:
                item['mode'] = 'memory'
            if not hasattr(_local, 'view'):
                _local.view = []
            _local.view.append(item)
        return result
    # Preserve existing refresh controls and regression-test fixtures.
    wrapped.clear = function.clear
    return wrapped


def pack(value):
    # Tagged containers preserve integer keys, tuples and sets across restarts.
    if isinstance(value, dict):
        return {'d': [[pack(k), pack(v)] for k, v in value.items()]}
    if isinstance(value, (list, tuple, set)):
        return {('t' if isinstance(value, tuple) else 's' if isinstance(value, set) else 'l'): [pack(v) for v in value]}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError('Unsupported cache value')


def unpack(value):
    if not isinstance(value, dict):
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return value
        raise ValueError('Invalid cache scalar')
    if len(value) != 1:
        raise ValueError('Invalid cache container')
    tag, items = next(iter(value.items()))
    if tag not in ('d', 't', 's', 'l') or not isinstance(items, list):
        raise ValueError('Invalid cache tag')
    if tag == 'd':
        if any(not isinstance(pair, list) or len(pair) != 2 for pair in items):
            raise ValueError('Invalid cache pairs')
        return {unpack(k): unpack(v) for k, v in items}
    values = [unpack(v) for v in items]
    return tuple(values) if tag == 't' else set(values) if tag == 's' else values



def eligible(value):
    if value is None:
        return False
    if isinstance(value, tuple) and value and value[0] is None:
        return False
    # History is (records, failed_seasons, timestamp); career exposes problems.
    if isinstance(value, tuple) and len(value) == 3 and isinstance(value[1], list) and value[1]:
        return False
    if isinstance(value, dict) and (value.get('errors') or value.get('calendar_error') or value.get('problems')):
        return False
    return True


def persistent(namespace, source='MLB Stats API'):
    def decorate(function):
        sig = signature(function)
        @wraps(function)
        def wrapped(*args, **kwargs):
            if os.environ.get('MLB_CACHE_DISABLED') == '1' or cloud():
                return function(*args, **kwargs)
            _local.serial = getattr(_local, 'serial', 0) + 1
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            scope = dict(bound.arguments)
            season = scope.get('season')
            player_id = scope.get('player_id')
            if player_id is not None and (isinstance(player_id, bool) or not isinstance(player_id, int) or player_id <= 0):
                raise ValueError('Invalid player ID')
            key = cache_key(function, scope)
            now = time.time()
            try:
                with connection() as db:
                    row = db.execute('SELECT payload,expires_at,retrieved_at FROM datasets WHERE cache_key=?', (key,)).fetchone()
                # Reserve the entire 60-second L1 lifetime; never warm L1 with
                # a persistent result that is about to expire.
                if row and row[1] > now + 65:
                    result = unpack(json.loads(row[0]))
                    if not eligible(result):
                        raise ValueError('Incomplete cached dataset')
                    record('persistent_hit')
                    note(key,namespace,source,row[2],row[1],'sqlite')
                    return result
                record('expired' if row else 'not_stored')
            except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RecursionError):
                record('database_error')
            record('persistent_miss')
            with _metadata_lock:
                _metadata.pop(key, None)
            started = time.perf_counter()
            try:
                result = function(*args, **kwargs)
            except Exception:
                record('source_error', time.perf_counter()-started)
                raise
            record('source_success', time.perf_counter()-started)
            if eligible(result):
                try:
                    payload = json.dumps(pack(result), allow_nan=False, ensure_ascii=False)
                    retrieved = time.time()
                    note(key,namespace,source,retrieved,retrieved+ttl(namespace,season),'source')
                    with connection() as db, db:
                        db.execute('''INSERT OR REPLACE INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?,1)''',
                                   (key, namespace, season, player_id, scope.get('category'), scope.get('game_type','R'),
                                    source, payload, retrieved, retrieved+ttl(namespace,season)))
                        if namespace == 'profile' and isinstance(result, dict) and result.get('id') == player_id and result.get('fullName'):
                            db.execute('INSERT OR REPLACE INTO players VALUES (?,?,?,?,?,?,?,?)',
                                       (player_id,result['fullName'],(result.get('primaryPosition') or {}).get('abbreviation'),
                                        (result.get('batSide') or {}).get('code'),(result.get('pitchHand') or {}).get('code'),
                                        result.get('mlbDebutDate'),json.dumps(result),retrieved))
                        if namespace == 'teams' and isinstance(result, list):
                            for team in result:
                                if isinstance(team,dict) and team.get('id') and team.get('name'):
                                    db.execute('INSERT OR REPLACE INTO teams VALUES (?,?,?,?,?,?,?)',
                                               (team['id'],season,team['name'],team.get('abbreviation'),
                                                str(team.get('league','')),json.dumps(team),retrieved))
                except (sqlite3.Error, OSError, ValueError, TypeError):
                    record('database_error')
            return result
        return wrapped
    return decorate
