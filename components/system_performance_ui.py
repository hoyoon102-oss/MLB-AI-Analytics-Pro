"""Opt-in local developer diagnostics; never display filesystem paths."""
from datetime import datetime, timezone
import os
import sqlite3
import time
import streamlit as st
from utils.i18n import current_language
from services import database
from analytics.performance_monitor import snapshot, reset


def label(ko, en):
    return en if current_language() == 'en' else ko


def freshness():
    from utils.config import cloud
    if cloud():
        st.caption(label('클라우드: 공개 통계 메모리 캐시 사용 · 개인 설정은 현재 세션에만 보관됩니다.', 'Cloud: public statistics use memory cache; personal settings are session-only.'))
        return
    from services.cache_manager import view_status
    entries = view_status()
    if entries:
        with st.expander(label('현재 화면 데이터의 출처·갱신 시각', 'Current view data sources and freshness')):
            for item in entries:
                at = datetime.fromtimestamp(item['retrieved_at'], timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                modes = {'memory':label('메모리 캐시','memory cache'), 'sqlite':label('SQLite 캐시','SQLite cache'), 'source':label('원본에서 조회','fetched from source')}
                state = modes[item['mode']] if item['expires_at'] > time.time() else label('만료·새로고침 필요','expired · refresh required')
                st.text(f"{item['dataset']} · {item['source']} · {at} · {state}")
    stats = snapshot()
    if stats['database_error']:
        st.warning(label('SQLite 캐시를 사용할 수 없었던 요청이 있습니다. 원본 API로 계속 조회합니다. 앱을 종료하고 DB 백업·무결성을 확인하세요.',
                         'Some SQLite cache operations failed. Source API access continues. Close the app and check database backups and integrity.'))
    st.caption(label('메모리 → SQLite → 원본 API · 만료된 데이터는 반환하지 않습니다.',
                     'Memory → SQLite → source API · expired data is never returned.'))
    if os.environ.get('MLB_CACHE_DISABLED') == '1':
        return
    try:
        info = database.inspect()
        if info['last_update']:
            updated = datetime.fromtimestamp(info['last_update'], timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            with st.expander(label('저장된 데이터의 출처·갱신 시각', 'Stored dataset sources and freshness')):
                st.caption(label('전체 로컬 캐시의 최근 10개 항목입니다. 현재 화면 데이터와 다를 수 있습니다.',
                                 'Ten most recently stored local datasets; these may differ from the current view.'))
                for namespace, season, category, game_type, source, retrieved, expires, size in info['datasets'][:10]:
                    at = datetime.fromtimestamp(retrieved, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                    state = label('저장됨·유효', 'cached · valid') if expires > time.time() else label('만료·재조회 필요', 'expired · refresh required')
                    st.text(f'{namespace} · {season or "—"} · {category or "—"} · {source} · {at} · {state}')
    except (sqlite3.Error, OSError, ValueError):
        st.warning(label('SQLite 접근 실패. 원본 API 조회는 계속 사용할 수 있습니다.', 'SQLite is unavailable. Source API access remains available.'))


def page():
    from utils.config import cloud
    if cloud() or os.environ.get('MLB_ANALYTICS_DEVELOPER') != '1':
        return
    st.title(label('시스템 상태', 'System Performance'))
    st.caption(label('프로세스 시작 또는 초기화 이후 측정입니다. hit_rate는 SQLite 접근, overall_hit_rate는 메모리 포함입니다. 원본 조회 시간·오류는 서비스 단위이며 개별 HTTP 요청과 다릅니다.',
                     'Measured since process start or reset. hit_rate covers SQLite; overall_hit_rate includes memory. Source durations and errors measure service calls, not individual HTTP requests.'))
    try:
        info = database.inspect()
        stats = snapshot()
        st.json(dict(database_status=info['status'], database_bytes=info['bytes'], players=info['players'],
                     teams=info['teams'], datasets=info['counts'], measurements=stats,
                     last_successful_update_utc=datetime.fromtimestamp(info['last_update'], timezone.utc).isoformat() if info['last_update'] else None))
        columns = ['dataset', 'season', 'category', 'game_type', 'source', 'retrieved_at_utc', 'expires_at_utc', 'payload_bytes', 'status']
        rows = []
        for row in info['datasets']:
            row = list(row)
            expires = row[6]
            row[5:7] = [datetime.fromtimestamp(value, timezone.utc).isoformat() for value in row[5:7]]
            row.append('fresh persistent cache' if expires > time.time() else 'expired — refresh required')
            rows.append(dict(zip(columns, row)))
        st.dataframe(rows, hide_index=True)
        if st.button(label('무결성 검사', 'Check integrity')):
            st.success(database.integrity())
        if st.button(label('DB 백업 생성', 'Back up database')):
            destination = database.database_path().parent / 'backups' / ('mlb-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.db')
            database.backup(destination)
            st.success(label('로컬 DB 폴더의 backups 폴더에 검증된 백업을 생성했습니다.', 'Verified backup created in the local database backups folder.'))
        if st.button(label('측정 초기화', 'Reset measurements')):
            reset()
            st.rerun()
        confirmed = st.checkbox(label('통계 캐시 삭제 확인 (즐겨찾기·설정은 유지)', 'Confirm statistics cache deletion (favorites and settings retained)'))
        expired = st.checkbox(label('만료된 항목만 삭제', 'Delete expired entries only'), value=True)
        if st.button(label('캐시 정리', 'Clean cache'), disabled=not confirmed):
            database.clear_cache(confirmed=confirmed, expired_only=expired)
            st.cache_data.clear()
            st.rerun()
    except (sqlite3.Error, OSError, ValueError):
        st.error(label('DB 접근 실패. 앱을 종료하고 마지막 검증된 백업으로 복구하세요. 기존 DB는 삭제하지 마세요.',
                       'Database access failed. Close the app and restore the last verified backup. Preserve the existing database.'))
