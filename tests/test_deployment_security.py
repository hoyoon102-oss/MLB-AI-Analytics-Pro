import json
from unittest.mock import patch
import pytest
from services.cache_manager import unpack, persistent
from services import database
from services.ai_analyst import list_models, AIError
from utils.config import mode

pytestmark = [pytest.mark.security, pytest.mark.integration]

@pytest.mark.parametrize('payload', [{}, {'unknown': []}, {'l': 1}, {'d': [1]}, {'l': [], 't': []}])
def test_corrupt_codec(payload):
    with pytest.raises((ValueError, TypeError)):
        unpack(payload)

def test_corrupt_cache_recovers(monkeypatch):
    monkeypatch.setenv('MLB_CACHE_DISABLED', '0')
    calls = []
    @persistent('test')
    def load():
        calls.append(1)
        return {'ok': True}
    load()
    with database.connection() as db, db:
        db.execute('UPDATE datasets SET payload=?', (json.dumps({}),))
    assert load() == {'ok': True}
    assert len(calls) == 2
    assert database.integrity() == 'ok'

def test_cloud_no_local_services(monkeypatch):
    monkeypatch.setenv('MLB_ANALYTICS_MODE', 'CLOUD')
    with patch('requests.Session') as http, patch('services.cache_manager.connection') as connection:
        with pytest.raises(AIError):
            list_models()
        @persistent('test')
        def loader():
            return {'ok': True}
        assert loader() == {'ok': True}
        http.assert_not_called()
        connection.assert_not_called()
    import sqlite3
    with pytest.raises(sqlite3.OperationalError):
        with database.connection():
            pass

def test_cloud_user_storage_isolated(monkeypatch, tmp_path):
    from utils.favorites import toggle_favorite, load_favorites
    from utils.leaderboard_presets import save_preset, load_presets
    from utils.i18n import save_language, load_language
    monkeypatch.setenv('MLB_ANALYTICS_MODE', 'CLOUD')
    first, second = {}, {}
    with patch('streamlit.session_state', first):
        toggle_favorite({'id': 1, 'fullName': '<script>test</script>'})
        save_preset('test', {'season': 2024})
        save_language('en')
        assert load_language() == 'en'
    with patch('streamlit.session_state', second):
        assert load_favorites() == ([], None)
        assert load_presets() == {}
        assert load_language() == 'ko'
    with patch('streamlit.session_state', first):
        assert len(load_favorites()[0]) == 1
        assert 'test' in load_presets()
    assert not (tmp_path / 'data').exists()

def test_mode_fail_closed(monkeypatch):
    monkeypatch.setenv('MLB_ANALYTICS_MODE', 'typo')
    with pytest.raises(ValueError):
        mode()

def test_bad_ttl_uses_default(monkeypatch):
    from services.cache_policy import ttl
    monkeypatch.setenv('MLB_CACHE_TTL_HISTORICAL', 'invalid')
    assert ttl('test', 2000) == 30 * 86400


def test_cloud_ui_smoke(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from unittest.mock import patch
    monkeypatch.setenv('MLB_ANALYTICS_MODE', 'CLOUD')
    import requests
    with patch('requests.get', side_effect=requests.Timeout()), patch('components.dashboard.resolve_seasons', return_value={'latest': 2024, 'years': [2024], 'warning': None}):
        from utils.paths import PROJECT_ROOT
        ui = AppTest.from_file(str(PROJECT_ROOT / 'app.py')).run(timeout=30)
    assert not ui.exception
    assert ui.session_state['ai_enabled'] is False
