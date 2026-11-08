"""Atomic local preset storage. Existing data is never silently replaced or deleted."""
import json
import os
from pathlib import Path
import tempfile
from utils.paths import PROJECT_ROOT


def presets_path():
    return Path(os.environ.get('MLB_ANALYTICS_DATA_DIR',str(PROJECT_ROOT/'data')))/'leaderboard_presets.json'


def load_presets(path=None):
    from utils.config import cloud
    if cloud():
        import copy
        import streamlit as st
        return copy.deepcopy(st.session_state.get('_cloud_presets', {}))
    path=Path(path or presets_path())
    if not path.exists():
        return {}
    payload=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(payload,dict) or payload.get('version')!=1 or not isinstance(payload.get('presets'),dict):
        raise ValueError('lb_presets_error')
    if any(not isinstance(name,str) or not isinstance(config,dict) for name,config in payload['presets'].items()):
        raise ValueError('lb_presets_error')
    return payload['presets']


def _name(name):
    name=str(name).strip()
    if not name or len(name)>80:
        raise ValueError('lb_preset_name_error')
    return name


def _write(presets,path):
    from utils.config import cloud
    if cloud():
        import copy
        import streamlit as st
        st.session_state['_cloud_presets'] = copy.deepcopy(presets)
        return
    path=Path(path or presets_path())
    path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps({'version':1,'presets':presets},ensure_ascii=False,indent=2,allow_nan=False)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',dir=path.parent,encoding='utf-8',delete=False,suffix='.tmp') as stream:
            temporary=Path(stream.name)
            stream.write(content+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def save_preset(name,config,path=None):
    presets=load_presets(path)
    name=_name(name)
    if name in presets or len(presets)>=100 or not isinstance(config,dict):
        raise ValueError('lb_preset_exists')
    presets[name]=config
    _write(presets,path)


def rename_preset(name,new_name,path=None):
    presets=load_presets(path)
    new_name=_name(new_name)
    if name not in presets or new_name in presets:
        raise ValueError('lb_preset_exists')
    presets[new_name]=presets.pop(name)
    _write(presets,path)


def delete_preset(name,confirmed=False,path=None):
    if not confirmed:
        raise ValueError('lb_delete_confirm')
    presets=load_presets(path)
    if name not in presets:
        raise ValueError('lb_presets_error')
    del presets[name]
    _write(presets,path)
