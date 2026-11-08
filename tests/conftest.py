"""Offline by default; every test receives disposable user storage."""
import socket
import pytest

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv('MLB_ANALYTICS_MODE', 'LOCAL')
    monkeypatch.setenv('MLB_ANALYTICS_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('MLB_ANALYTICS_DB_PATH', str(tmp_path / 'cache.db'))
    monkeypatch.setenv('MLB_ANALYTICS_DEVELOPER', '0')
    monkeypatch.setenv('MLB_CACHE_DISABLED', '1')
    original_connect = socket.socket.connect
    def denied(sock, address):
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return original_connect(sock, address)
        raise AssertionError('Network access forbidden in offline tests; mock the source')
    import requests
    def denied_http(*args, **kwargs):
        raise AssertionError('Unmocked HTTP forbidden in offline tests')
    monkeypatch.setattr(requests.Session, 'send', denied_http)
    monkeypatch.setattr(socket.socket, 'connect', denied)
    import streamlit as st
    st.cache_data.clear()
    yield
    st.cache_data.clear()

def pytest_collection_modifyitems(items):
    for item in items:
        name = item.path.name
        item.add_marker(pytest.mark.regression)
        if any(x in name for x in ('ui', 'app', 'pro_', 'smart')):
            item.add_marker(pytest.mark.ui)
        elif 'database' in name:
            item.add_marker(pytest.mark.database)
        elif any(x in name for x in ('search', 'league', 'awards')):
            item.add_marker(pytest.mark.api)
        else:
            item.add_marker(pytest.mark.unit)
