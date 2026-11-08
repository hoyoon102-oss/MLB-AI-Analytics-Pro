"""Local single-user favorites. Team affiliations are deliberately not persisted."""
from utils.paths import PROJECT_ROOT
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from datetime import datetime, timezone

_LOCK = threading.RLock()


def favorites_path():
    directory = os.environ.get("MLB_ANALYTICS_DATA_DIR")
    return (Path(directory) if directory else PROJECT_ROOT / "data") / "favorites.json"


def clean_player(person):
    if (not isinstance(person, dict) or isinstance(person.get("id"), bool)
            or not isinstance(person.get("id"), int) or person["id"] <= 0
            or not isinstance(person.get("fullName"), str) or not person["fullName"].strip()):
        raise ValueError("유효한 선수 ID와 이름이 필요합니다.")
    result = {"id": person["id"], "fullName": person["fullName"].strip()}
    if isinstance(person.get("birthDate"), str):
        result["birthDate"] = person["birthDate"]
    return result


def load_favorites(path=None):
    from utils.config import cloud
    if cloud():
        import streamlit as st
        return [dict(p) for p in st.session_state.get('_cloud_favorites', [])], None
    path = Path(path) if path is not None else favorites_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return [], None
        raw = path.read_text(encoding="utf-8-sig")
        if not raw.strip():
            return [], "즐겨찾기 파일이 비어 있어 빈 목록으로 시작합니다."
        payload = json.loads(raw)
        rows = payload.get("players") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("목록 형식 오류")
        people, invalid = {}, False
        for row in rows:
            try:
                person = clean_player(row)
                people[person["id"]] = person
            except ValueError:
                invalid = True
        return sorted(people.values(), key=lambda p: (p["fullName"].casefold(), p["id"])), (
            "일부 즐겨찾기 항목을 읽을 수 없어 유효한 항목만 표시합니다." if invalid else None)
    except (ValueError, UnicodeError):
        return [], "즐겨찾기 파일이 손상되어 빈 목록으로 시작합니다. 저장할 때 원본을 백업합니다."
    except OSError:
        return [], "즐겨찾기 파일을 읽을 수 없습니다. 폴더 접근 권한을 확인해 주세요."


def toggle_favorite(person, path=None):
    from utils.config import cloud
    if cloud():
        import streamlit as st
        person = clean_player(person)
        players, _ = load_favorites()
        by_id = {p['id']: p for p in players}
        added = person['id'] not in by_id
        if added:
            by_id[person['id']] = person
        else:
            del by_id[person['id']]
        players = sorted(by_id.values(), key=lambda p: (p['fullName'].casefold(), p['id']))
        st.session_state['_cloud_favorites'] = players
        return players, added
    path = Path(path) if path is not None else favorites_path()
    person = clean_player(person)
    with _LOCK:
        players, warning = load_favorites(path)
        by_id = {player["id"]: player for player in players}
        added = person["id"] not in by_id
        if added:
            by_id[person["id"]] = person
        else:
            del by_id[person["id"]]
        players = sorted(by_id.values(), key=lambda p: (p["fullName"].casefold(), p["id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        if warning and path.exists():
            suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            shutil.copy2(path, path.with_name(f"utils.favorites.backup.{suffix}.json"))
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".favorites-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"version": 1, "players": players}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        return players, added
