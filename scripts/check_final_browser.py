"""Offline Edge smoke/screenshots with a source snapshot and isolated user storage."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import requests
from playwright.sync_api import sync_playwright, expect
from utils.paths import PROJECT_ROOT

WRAPPER = r'''import json
import requests
import streamlit as st
from unittest.mock import Mock, patch
from components.dashboard import main
from utils.paths import PROJECT_ROOT
examples = json.loads((PROJECT_ROOT / 'tests/advanced-verified-examples.json').read_text(encoding='utf-8'))

def response(url, params=None, **kwargs):
    result = Mock()
    if url.endswith('/awards'):
        result.json.return_value = {'awards': []}
    elif '/stats' in url:
        category = (params or {}).get('group', 'hitting')
        rows = [{'season': str(e['season']), 'stat': e['stats']} for e in examples
                if e['player_id'] == 660271 and e['category'] == category]
        result.json.return_value = {'stats': [{'group': {'displayName': category}, 'splits': rows}]}
    elif url.endswith('/people/660271'):
        result.json.return_value = {'people': [{'id': 660271, 'fullName': 'Shohei Ohtani', 'primaryPosition': {'abbreviation': 'DH'}}]}
    else:
        raise requests.ConnectionError('Offline screenshot: source not requested')
    return result

st.session_state.setdefault('dashboard_chosen', {'id': 660271, 'fullName': 'Shohei Ohtani'})
st.session_state.setdefault('dashboard_mode', '즐겨찾기')
st.session_state.setdefault('pro_page', '선수 기록')
st.session_state.setdefault('selected_season', 2024)
with patch('requests.get', side_effect=response), patch('components.dashboard.resolve_seasons', return_value={'latest': 2024, 'years': [2024], 'warning': None}):
    main()
st.caption('QA screenshot: saved 2024 statistics snapshot; not a live query. Profile and supplementary sources are offline.')
'''


def main():
    output = PROJECT_ROOT / 'docs/images'
    output.mkdir(exist_ok=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryDirectory() as temporary:
        wrapper = Path(temporary) / 'preview.py'
        wrapper.write_text('import sys\nsys.path.insert(0, ' + repr(str(PROJECT_ROOT)) + ')\n' + WRAPPER, encoding='utf-8')
        env = dict(os.environ, MLB_ANALYTICS_MODE='LOCAL', MLB_CACHE_DISABLED='1',
                   MLB_ANALYTICS_DATA_DIR=temporary, MLB_ANALYTICS_DB_PATH=str(Path(temporary)/'test.db'),
                   MLB_ANALYTICS_DEVELOPER='0')
        with (Path(temporary)/'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(wrapper),
                '--server.headless=true', '--server.address=127.0.0.1', '--server.port='+str(port)],
                cwd=PROJECT_ROOT, env=env, stdout=log, stderr=log)
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    for _ in range(80):
                        if server.poll() is not None:
                            raise RuntimeError('Preview server exited')
                        try:
                            if session.get(f'http://127.0.0.1:{port}/_stcore/health', timeout=1).status_code == 200:
                                break
                        except requests.RequestException:
                            pass
                        time.sleep(.25)
                    else:
                        raise RuntimeError('Preview startup timeout')
                observations = []
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel='msedge', headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
                    page.set_default_timeout(30000)
                    page.goto(f'http://127.0.0.1:{port}')
                    expect(page.locator('.pro-eyebrow')).to_contain_text('VERSION 4.9')
                    expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
                    for width, height in [(1440, 1100), (390, 844)]:
                        page.set_viewport_size({'width': width, 'height': height})
                        page.wait_for_timeout(500)
                        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                        overflow = page.evaluate('document.documentElement.scrollWidth > window.innerWidth + 2')
                        if overflow:
                            raise AssertionError('Horizontal overflow at '+str(width))
                        page.screenshot(path=str(output/f'v49-player-{width}.png'), full_page=True)
                        observations.append({'width': width, 'exceptions': 0, 'horizontal_overflow': False})
                    browser.close()
                (PROJECT_ROOT/'docs/final-browser-checks.json').write_text(json.dumps({'scope': 'Offline current UI with saved 2024 fixture; no live profile or supplementary sources', 'viewports': observations}, indent=2), encoding='utf-8')
                print('PASS: current 4.9 player UI, 1440/390 widths, no exception or horizontal overflow')
            finally:
                if os.name == 'nt' and server.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], capture_output=True, check=True)
                elif server.poll() is None:
                    server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


if __name__ == '__main__':
    main()
