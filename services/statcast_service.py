"""Bounded, serial Baseball Savant CSV access. No pybaseball dependency or ID lookup."""
import csv
from services.cache_manager import persistent, observe
from datetime import date, datetime, timedelta, timezone
import io
import time
import threading

import requests
import streamlit as st

BASE = 'https://baseballsavant.mlb.com'
DOCS = BASE + '/csv-docs'
MAX_BYTES = 16_000_000
MAX_ROWS = 25000
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST = 0.


def pace_requests():
    global _LAST_REQUEST
    with _REQUEST_LOCK:
        delay = 1. - (time.monotonic() - _LAST_REQUEST)
        if delay > 0:
            time.sleep(delay)
        _LAST_REQUEST = time.monotonic()


class StatcastError(ValueError):
    """Source unavailable or response cannot safely be interpreted."""


def date_range(season, start, end):
    if isinstance(season, bool) or int(season) < 2015:
        raise StatcastError('sc_coverage')
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if start > end or start.year != int(season) or end.year != int(season):
        raise StatcastError('sc_dates_error')
    return start, end


def chunks(start, end, days=31):
    if days < 1 or days > 31:
        raise StatcastError('sc_dates_error')
    while start <= end:
        stop = min(start + timedelta(days=days-1), end)
        yield start, stop
        start = stop + timedelta(days=1)


def parse_csv(text):
    text = text.lstrip('\ufeff')
    if text.lstrip().startswith('<'):
        raise StatcastError('sc_schema_error')
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise StatcastError('sc_schema_error')
    try:
        rows = list(reader)
    except csv.Error as error:
        raise StatcastError('sc_schema_error') from error
    if any(None in row for row in rows):
        raise StatcastError('sc_schema_error')
    return reader.fieldnames, rows


def csv_request(path, params):
    """Retry transient failures only; never bypass 403/429 access restrictions."""
    for attempt in range(3):
        try:
            pace_requests()
            with requests.get(BASE+path, params=params, timeout=(5,45), stream=True) as response:
                if response.status_code in (403, 429):
                    raise StatcastError('sc_access_error')
                response.raise_for_status()
                parts, size = [], 0
                for block in response.iter_content(chunk_size=65536):
                    size += len(block)
                    if size > MAX_BYTES:
                        raise StatcastError('sc_size_error')
                    parts.append(block)
                fields, rows = parse_csv(b''.join(parts).decode('utf-8-sig'))
                return fields, rows, response.url
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise StatcastError('sc_network_error')
        except requests.HTTPError as error:
            if error.response is None or error.response.status_code < 500 or attempt == 2:
                raise StatcastError('sc_network_error') from error
        time.sleep(1 * 2**attempt)


def integer(value):
    try:
        parsed = float(value)
        return int(parsed) if parsed.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def validate_rows(rows, player_id, season, category, start, end):
    identity = 'batter' if category == 'hitting' else 'pitcher'
    unique, excluded, duplicate_count = {}, 0, 0
    for row in rows:
        if integer(row.get(identity)) != player_id:
            raise StatcastError('sc_identity_error')
        try:
            day = date.fromisoformat(row['game_date'][:10])
        except (KeyError, TypeError, ValueError) as error:
            raise StatcastError('sc_schema_error') from error
        if day.year != int(season) or not start <= day <= end or row.get('game_type') != 'R':
            excluded += 1
            continue
        key = tuple(integer(row.get(k)) for k in ('game_pk','at_bat_number','pitch_number'))
        if any(v is None or v < 1 for v in key):
            raise StatcastError('sc_schema_error')
        if key in unique:
            if unique[key] != row:
                raise StatcastError('sc_duplicate_conflict')
            duplicate_count += 1
        else:
            unique[key] = row
    ordered = sorted(unique.values(), key=lambda r: (r['game_date'], *(integer(r[k]) for k in ('game_pk','at_bat_number','pitch_number'))))
    return ordered, {'excluded_scope':excluded, 'duplicates_removed':duplicate_count}


@observe
@st.cache_data(ttl=60, show_spinner=False, max_entries=256)
@persistent('statcast_chunk', 'Baseball Savant · selected player/date range')
def fetch_chunk(player_id, season, category, start, end):
    start, end = date_range(season, start, end)
    if category not in ('hitting','pitching') or isinstance(player_id,bool) or integer(player_id) != player_id or player_id <= 0 or (end-start).days > 30:
        raise StatcastError('sc_identity_error')
    role = 'batter' if category == 'hitting' else 'pitcher'
    fields, rows, url = csv_request('/statcast_search/csv', {
        'all':'true','type':'details','player_type':role, role+'s_lookup[]':player_id,
        'game_date_gt':start.isoformat(),'game_date_lt':end.isoformat(), 'hfGT':'R|',
        'min_pitches':0, 'min_results':0, 'group_by':'name', 'sort_col':'pitches'})
    if not {'game_pk','at_bat_number','pitch_number',role,'game_date','game_type'} <= set(fields):
        raise StatcastError('sc_schema_error')
    if len(rows) >= MAX_ROWS:
        raise StatcastError('sc_size_error')
    rows, quality = validate_rows(rows, player_id, season, category, start, end)
    return {'rows':rows,'quality':quality,'source':url,'retrieved_at':datetime.now(timezone.utc).isoformat()}


def fetch_period(player_id, season, category, start, end, progress=None):
    start, end = date_range(season, start, end)
    periods = list(chunks(start,end))
    rows, sources, times = [], [], []
    quality = {'excluded_scope':0,'duplicates_removed':0}
    for index, (first,last) in enumerate(periods):
        result = fetch_chunk(player_id, season, category, first.isoformat(),last.isoformat())
        rows.extend(result['rows'])
        sources.append(result['source'])
        times.append(result['retrieved_at'])
        for key in quality:
            quality[key] += result['quality'][key]
        if progress:
            progress((index+1)/len(periods))
        if index+1 < len(periods):
            time.sleep(.3)
    rows, final_quality = validate_rows(rows,player_id,season,category,start,end)
    for key in quality:
        quality[key] += final_quality[key]
    return {'player_id':player_id,'season':int(season),'category':category,'game_type':'R',
            'start':start.isoformat(),'end':end.isoformat(),'rows':rows,'quality':quality,
            'sources':sources,'retrieved_at':max(times),'chunk_retrieved_at':times,
            'scope':'selected_date_range', 'documentation':DOCS}


@observe
@st.cache_data(ttl=60, show_spinner=False, max_entries=32)
@persistent('statcast_summary', 'Baseball Savant')
def published_table(season, category, table):
    if int(season) < 2015 or category not in ('hitting','pitching') or table not in ('contact','expected'):
        raise StatcastError('sc_coverage')
    role = 'batter' if category == 'hitting' else 'pitcher'
    path = '/leaderboard/statcast' if table == 'contact' else '/leaderboard/expected_statistics'
    fields, rows, url = csv_request(path, {'type':role, 'year':int(season), 'position':'','team':'',
                                          'min':0,'filterType':'pa','csv':'true'})
    if 'player_id' not in fields:
        raise StatcastError('sc_schema_error')
    return {'rows':rows,'source':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'season':int(season),'category':category,'game_type':'R','scope':'published_full_season'}


def published_player(season, category, player_id):
    output = {'season':int(season),'category':category,'player_id':player_id,'tables':{},'errors':[]}
    for table in (('contact','expected') if category == 'hitting' else ('expected',)):
        try:
            result = published_table(season,category,table)
            matches = [r for r in result['rows'] if integer(r.get('player_id')) == player_id]
            if len(matches) > 1:
                raise StatcastError('sc_identity_error')
            row = matches[0] if matches else {}
            if row.get('year') and integer(row['year']) != int(season):
                raise StatcastError('sc_identity_error')
            output['tables'][table] = dict(result,rows=None,row=row)
        except (StatcastError, requests.RequestException, UnicodeError, ValueError) as error:
            output['errors'].append(str(error))
    return output
