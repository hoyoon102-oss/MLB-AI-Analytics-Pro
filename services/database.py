"""Versioned local SQLite store. Connections are short-lived and never shared."""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import time

SCHEMA_VERSION = 1


def database_path():
    override = os.environ.get('MLB_ANALYTICS_DB_PATH')
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
    return base / 'MLB-AI-Analytics' / 'mlb_analytics.db'


@contextmanager
def connection(path=None):
    from utils.config import cloud
    if cloud():
        raise sqlite3.OperationalError('Persistent SQLite is disabled in CLOUD mode')
    target = Path(path) if path else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=10)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        # DELETE journaling also works for explicit synchronized-directory overrides.
        db.execute('PRAGMA journal_mode=DELETE')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise sqlite3.DatabaseError('Database schema is newer than this application')
        if version < 1:
            with db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('''CREATE TABLE IF NOT EXISTS datasets (
                    cache_key TEXT PRIMARY KEY, namespace TEXT NOT NULL,
                    season INTEGER, player_id INTEGER CHECK(player_id > 0),
                    category TEXT, game_type TEXT NOT NULL, source TEXT NOT NULL,
                    payload TEXT NOT NULL, retrieved_at REAL NOT NULL,
                    expires_at REAL NOT NULL, complete INTEGER NOT NULL CHECK(complete=1))''')
                db.execute('CREATE INDEX IF NOT EXISTS datasets_scope ON datasets(namespace,season,category,game_type)')
                db.execute('CREATE INDEX IF NOT EXISTS datasets_expiry ON datasets(expires_at)')
                db.execute('''CREATE TABLE IF NOT EXISTS players (
                    player_id INTEGER PRIMARY KEY CHECK(player_id>0), full_name TEXT NOT NULL,
                    position TEXT, bat_side TEXT, throw_side TEXT, debut TEXT,
                    metadata TEXT NOT NULL, updated_at REAL NOT NULL)''')
                db.execute('''CREATE TABLE IF NOT EXISTS teams (
                    team_id INTEGER NOT NULL CHECK(team_id>0), season INTEGER NOT NULL,
                    name TEXT NOT NULL, abbreviation TEXT, league TEXT,
                    metadata TEXT NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY(team_id,season))''')
                db.execute('PRAGMA user_version=1')
        yield db
    finally:
        db.close()


def integrity(path=None):
    with connection(path) as db:
        return db.execute('PRAGMA integrity_check').fetchone()[0]


def backup(destination, path=None):
    destination = Path(destination)
    if destination.resolve() == Path(path or database_path()).resolve():
        raise ValueError('Backup must use a different path')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of an existing backup.
    with destination.open('xb'):
        pass
    with connection(path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise sqlite3.DatabaseError('Backup integrity check failed')
    return destination


def inspect(path=None):
    with connection(path) as db:
        counts = dict(db.execute('SELECT namespace,count(*) FROM datasets GROUP BY namespace'))
        rows = db.execute('''SELECT namespace,season,category,game_type,source,retrieved_at,
                          expires_at,length(payload) FROM datasets ORDER BY retrieved_at DESC LIMIT 100''').fetchall()
        return dict(status='ok', bytes=Path(path or database_path()).stat().st_size,
                    players=db.execute('SELECT count(*) FROM players').fetchone()[0],
                    teams=db.execute('SELECT count(*) FROM teams').fetchone()[0], counts=counts,
                    datasets=rows, last_update=db.execute('SELECT max(retrieved_at) FROM datasets').fetchone()[0])


def clear_cache(*, confirmed=False, expired_only=False, path=None):
    if not confirmed:
        raise ValueError('Explicit confirmation is required')
    with connection(path) as db, db:
        if expired_only:
            return db.execute('DELETE FROM datasets WHERE expires_at <= ?', (time.time(),)).rowcount
        return db.execute('DELETE FROM datasets').rowcount
