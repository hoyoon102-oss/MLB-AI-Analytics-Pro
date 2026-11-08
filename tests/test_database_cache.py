"""All persistence tests use isolated temporary databases and no network."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from services import database
from services.cache_manager import persistent, pack, unpack, observe, begin_view, view_status
from services.cache_policy import season_state, ttl
from analytics.performance_monitor import reset, snapshot


class DatabaseCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'cache.db'
        env = patch.dict(os.environ, MLB_ANALYTICS_DB_PATH=str(self.path), MLB_CACHE_DISABLED='0')
        env.start()
        self.addCleanup(env.stop)
        reset()

    def test_init_version_indexes(self):
        for _ in range(2):
            with database.connection() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
                self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
                self.assertGreaterEqual(len(db.execute("PRAGMA index_list('datasets')").fetchall()),3)
        self.assertEqual(database.integrity(),'ok')

    def test_future_schema_rejected(self):
        with database.connection() as db:
            db.execute('PRAGMA user_version=99')
        with self.assertRaises(sqlite3.DatabaseError):
            database.inspect()

    def test_transaction_rollback(self):
        with self.assertRaises(RuntimeError):
            with database.connection() as db, db:
                db.execute("INSERT INTO players VALUES (1,'Test',NULL,NULL,NULL,NULL,'{}',0)")
                raise RuntimeError()
        self.assertEqual(database.inspect()['players'],0)

    def test_codec_exact(self):
        value = ({2024:{'x':None,'rate':.333},'tuple':(1,2),'set':{3,4}},'UTC')
        self.assertEqual(unpack(json.loads(json.dumps(pack(value)))),value)

    def test_memory_observation_and_current_view(self):
        import streamlit as st
        @observe
        @st.cache_data(ttl=60,show_spinner=False)
        @persistent('test')
        def loader(player_id,season):
            return {'value':player_id}
        loader.clear()
        self.addCleanup(loader.clear)
        begin_view()
        loader(1,2024)
        self.assertEqual(view_status()[-1]['mode'],'source')
        begin_view()
        loader(1,2024)
        self.assertEqual(view_status()[-1]['mode'],'memory')
        self.assertEqual(snapshot()['memory_hit'],1)
        loader.clear()
        begin_view()
        loader(1,2024)
        self.assertEqual(view_status()[-1]['mode'],'sqlite')

    def test_hit_restart_duplicate_and_scope(self):
        calls=[]
        @persistent('player_stats')
        def loader(player_id,season,category='hitting',game_type='R'):
            calls.append(1)
            return ({'pa':10,'rate':.333},'timestamp')
        first=loader(1,2024)
        self.assertEqual(loader(1,2024),first)
        self.assertEqual(len(calls),1)
        loader(1,2024,'pitching')
        loader(1,2024,game_type='P')
        self.assertEqual(database.inspect()['counts']['player_stats'],3)
        self.assertEqual(snapshot()['persistent_hit'],1)

    def test_expiration_and_failure_no_stale(self):
        fail=False
        @persistent('test')
        def loader(season):
            if fail:
                raise TimeoutError('offline')
            return {'value':3}
        loader(2024)
        with database.connection() as db, db:
            db.execute('UPDATE datasets SET expires_at=0')
        fail=True
        with self.assertRaises(TimeoutError):
            loader(2024)
        self.assertEqual(snapshot()['source_error'],1)
        self.assertEqual(database.inspect()['counts']['test'],1)

    def test_missing_and_partial_not_cached(self):
        for value in [None,(None,'timestamp'),{'errors':['partial']},{'calendar_error':'missing'}]:
            @persistent('test')
            def loader():
                return value
            loader()
        self.assertEqual(database.inspect()['counts'],{})

    def test_id_validation(self):
        @persistent('profile')
        def loader(player_id):
            return {'id':player_id,'fullName':'Test'}
        for invalid in [True,0,-1,'1']:
            with self.assertRaises(ValueError):
                loader(invalid)
        loader(123)
        self.assertEqual(database.inspect()['players'],1)

    def test_policy(self):
        today=date(2026,11,5)
        self.assertEqual(season_state(2025,today),'completed')
        self.assertEqual(season_state(2026,today),'active')
        self.assertEqual(season_state(2027,today),'upcoming')
        self.assertGreater(ttl('leaderboard',2025,today),ttl('leaderboard',2026,today))
        self.assertEqual(ttl('leaderboard',2026,today),ttl('leaderboard',2027,today))

    def test_backup_restore_and_confirmation(self):
        @persistent('test')
        def loader():
            return {2024:[1,2]}
        loader()
        target=Path(self.directory.name)/'backup.db'
        database.backup(target)
        self.assertEqual(database.integrity(target),'ok')
        with self.assertRaises(ValueError):
            database.clear_cache()
        database.clear_cache(confirmed=True)
        self.assertEqual(database.inspect()['counts'],{})
        # Restore from the verified snapshot using SQLite backup, while closed.
        with sqlite3.connect(target) as src, sqlite3.connect(self.path) as dst:
            src.backup(dst)
        self.assertEqual(database.inspect()['counts']['test'],1)
        with self.assertRaises(FileExistsError):
            database.backup(target)

    def test_concurrent_connections(self):
        @persistent('test')
        def loader(player_id):
            return {'value':player_id}
        with ThreadPoolExecutor(max_workers=6) as pool:
            self.assertEqual(list(pool.map(loader,range(1,19))),[{'value':i} for i in range(1,19)])
        self.assertEqual(database.integrity(),'ok')
        self.assertEqual(database.inspect()['counts']['test'],18)

    def test_database_failure_source_continues(self):
        @persistent('test')
        def loader():
            return {'ok':True}
        with patch('services.cache_manager.connection',side_effect=sqlite3.OperationalError('locked')):
            self.assertEqual(loader(),{'ok':True})
        self.assertTrue(snapshot()['database_error'])

    def test_refresh_and_cleanup_preserve_json(self):
        favorites=Path(self.directory.name)/'favorites.json'
        favorites.write_text('{"players":[]}',encoding='utf-8')
        before=favorites.read_bytes()
        database.clear_cache(confirmed=True)
        self.assertEqual(favorites.read_bytes(),before)


class FinalCacheRegressionTests(unittest.TestCase):
    def test_partial_history_and_career_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                MLB_ANALYTICS_DB_PATH=str(Path(directory) / 'test.db'), MLB_CACHE_DISABLED='0'):
            for value in [({2024: None}, [2024], 'timestamp'),
                          {'records': {2024: None}, 'problems': {2024: 'ambiguous'}}]:
                calls = []
                @persistent('test')
                def loader():
                    calls.append(1)
                    return value
                loader()
                loader()
                self.assertEqual(len(calls), 2)
            self.assertEqual(database.inspect()['counts'], {})

    def test_old_partial_entry_is_retried(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                MLB_ANALYTICS_DB_PATH=str(Path(directory) / 'test.db'), MLB_CACHE_DISABLED='0'):
            calls = []
            @persistent('test')
            def loader():
                calls.append(1)
                return {'records': {2024: {'hits': 1}}, 'problems': {}}
            loader()
            with database.connection() as db, db:
                db.execute('UPDATE datasets SET payload=?',
                           (json.dumps(pack({'problems': {2024: 'failed'}})),))
            result = loader()
            self.assertEqual(len(calls), 2)
            self.assertEqual(result['problems'], {})

    def test_codec_rejects_raw_containers_and_nonfinite_values(self):
        for value in [[], [1], float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                unpack(value)
