"""Central catalogs and a public-API Streamlit presentation adapter.

Legacy Korean labels remain stable internal widget values. Only their displayed
labels/format functions are localized, so switching language cannot change IDs,
filters, player selection, stored records or cache keys. New UI uses t(key).
"""
from utils.paths import PROJECT_ROOT
from functools import lru_cache, wraps
import inspect
import json
import os
from pathlib import Path
import re
import tempfile

import streamlit as raw_st

ROOT = PROJECT_ROOT / "translations"
LANGUAGES = {"ko": "한국어 (Korean)", "en": "English"}


@lru_cache(maxsize=4)
def catalog(language):
    try:
        value = json.loads((ROOT / f"{language}.json").read_text(encoding="utf-8"))
        return {key: text for key, text in value.items() if isinstance(text, str)} if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def current_language():
    value = raw_st.session_state.get("ui_language", "ko")
    return value if value in LANGUAGES else "ko"


def t(key, locale=None, **values):
    language = locale or current_language()
    text = catalog(language).get(key, catalog("ko").get(key, key))
    try:
        return text.format(**values) if values else text
    except (KeyError, ValueError, IndexError):
        return text


@lru_cache(maxsize=2)
def substitutions(language):
    source, target = catalog("ko"), catalog(language)
    return sorted(((value, target.get(key, value)) for key, value in source.items() if value != target.get(key, value)),
                  key=lambda item: len(item[0]), reverse=True)


def tr(text, language=None):
    """Render legacy source labels; never apply this to user/AI message bodies."""
    language = language or current_language()
    if not isinstance(text, str) or language == "ko":
        return text
    for source, target in substitutions(language):
        if text == source:
            return target
    for source, target in substitutions(language):
        if source not in text:
            continue
        if len(source) == 1:
            text = re.sub(r"(?<![가-힣])" + re.escape(source) + r"(?![가-힣])", lambda _: target, text)
        else:
            text = text.replace(source, target)
    return text


def settings_path():
    return Path(os.environ.get("MLB_ANALYTICS_DATA_DIR", str(PROJECT_ROOT / "data"))) / "settings.json"


def load_language(path=None):
    from utils.config import cloud
    if cloud():
        return raw_st.session_state.get('_cloud_language', 'ko')
    try:
        settings = json.loads(Path(path or settings_path()).read_text(encoding="utf-8-sig"))
        return settings.get("language", "ko") if settings.get("language") in LANGUAGES else "ko"
    except (OSError, ValueError, TypeError, AttributeError):
        return "ko"


def save_language(language, path=None):
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    from utils.config import cloud
    if cloud():
        raw_st.session_state['_cloud_language'] = language
        return
    path = Path(path or settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(settings, dict):
            settings = {}
    except (OSError, ValueError):
        settings = {}
    settings["language"] = language
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".settings-", suffix=".tmp",
                                         encoding="utf-8", delete=False) as file:
            temporary = Path(file.name)
            json.dump(settings, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _save_selection(reset_search_display=None):
    # Public session-state assignment asks Streamlit to reserialize existing
    # choices with their new display formatter without changing their values.
    for key in raw_st.session_state.get("i18n_choice_keys", []):
        if key != "ui_language" and key in raw_st.session_state:
            raw_st.session_state[key] = raw_st.session_state[key]
    if reset_search_display is not None:
        reset_search_display()
    try:
        save_language(current_language())
        raw_st.session_state.pop("language_save_error", None)
    except OSError:
        raw_st.session_state["language_save_error"] = True


def language_selector(reset_search_display=None):
    if "ui_language" not in raw_st.session_state:
        raw_st.session_state["ui_language"] = load_language()
    raw_st.sidebar.selectbox(t("language_label"), list(LANGUAGES), key="ui_language",
                            format_func=LANGUAGES.get, on_change=_save_selection,
                            args=(reset_search_display,), persist_state="session")
    if raw_st.session_state.get("language_save_error"):
        raw_st.sidebar.warning(t("language_save_error"))


def localize_figure(figure):
    # Clone the figure so legend filtering and original trace names stay stable.
    def visit(value):
        if isinstance(value, str):
            return tr(value)
        if isinstance(value, dict):
            return {key: visit(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [visit(item) for item in value]
        return value
    return visit(figure.to_plotly_json()) if hasattr(figure, "to_plotly_json") else figure


def _data(value):
    if isinstance(value, str):
        return tr(value)
    if isinstance(value, list):
        return [_data(item) for item in value]
    if isinstance(value, dict):
        return {tr(key): _data(item) for key, item in value.items()}
    return value


TEXT_METHODS = {"title", "header", "subheader", "caption", "markdown", "write", "text", "info", "warning",
                "error", "success", "toast", "button", "form_submit_button", "selectbox", "radio", "multiselect",
                "toggle", "checkbox", "number_input", "text_input", "chat_input", "slider", "metric", "spinner",
                "expander", "tabs", "dataframe", "table", "plotly_chart"}
LAYOUT_METHODS = {"columns", "container", "expander", "tabs", "chat_message", "empty"}


class LocalizedStreamlit:
    """A facade, not a patch of Streamlit internals or global functions."""
    def __init__(self, target):
        self._target = target

    def __enter__(self):
        self._target.__enter__()
        return self

    def __exit__(self, *args):
        return self._target.__exit__(*args)

    def __getattr__(self, name):
        original = getattr(self._target, name)
        if name == "sidebar":
            return LocalizedStreamlit(original)
        if name not in TEXT_METHODS | LAYOUT_METHODS:
            return original

        @wraps(original)
        def render(*args, **kwargs):
            bound = inspect.signature(original).bind_partial(*args, **kwargs)
            params = bound.arguments
            for field in ("label", "body", "text", "help", "placeholder", "caption"):
                if isinstance(params.get(field), str):
                    params[field] = tr(params[field])
            if name == "write":
                params["args"] = tuple(_data(value) for value in params.get("args", ()))
            if name in ("selectbox", "radio", "multiselect"):
                key = params.get("key")
                if key:
                    keys = raw_st.session_state.setdefault("i18n_choice_keys", [])
                    if key not in keys:
                        keys.append(key)
                formatter = params.get("format_func", str)
                language = current_language()
                params["format_func"] = lambda value: tr(formatter(value), language)
                if "captions" in params and params["captions"]:
                    params["captions"] = [tr(value) for value in params["captions"]]
            if name == "metric" and isinstance(params.get("value"), str):
                params["value"] = tr(params["value"])
            if name == "tabs":
                params["tabs"] = [tr(value) for value in params["tabs"]]
            if name in ("table", "dataframe") and "data" in params:
                params["data"] = _data(params["data"])
            if name == "plotly_chart" and "figure_or_data" in params:
                params["figure_or_data"] = localize_figure(params["figure_or_data"])
            result = original(*bound.args, **bound.kwargs)
            if name in LAYOUT_METHODS:
                return [LocalizedStreamlit(item) for item in result] if isinstance(result, (list, tuple)) else LocalizedStreamlit(result)
            return result
        return render


st = LocalizedStreamlit(raw_st)
