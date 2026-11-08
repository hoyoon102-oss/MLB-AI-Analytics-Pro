from utils.paths import PROJECT_ROOT
"""Explicit restored-selection fixtures; no predefined players in the application."""
from streamlit.testing.v1 import AppTest
from unittest.mock import patch


def seeded_app():
    ui = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
    ui.session_state["selected_season"] = 2024
    for key, person in {"dashboard": {"id": 660271, "fullName": "Shohei Ohtani"},
                        "compare_0": {"id": 660271, "fullName": "Shohei Ohtani"},
                        "compare_1": {"id": 592450, "fullName": "Aaron Judge"}}.items():
        ui.session_state[f"{key}_mode"] = "즐겨찾기"
        ui.session_state[f"{key}_chosen"] = person
    return ui.run(timeout=30)


def choose_restored(ui, key, name):
    ids = {"Shohei Ohtani": 660271, "Aaron Judge": 592450, "Gerrit Cole": 543037}
    ui.session_state[f"{key}_chosen"] = {"id": ids[name], "fullName": name}
    return ui.run()


def fix_seasons(test_case):
    patcher = patch("components.dashboard.resolve_seasons", return_value={"latest": 2024, "years": list(range(2020, 2027)), "warning": None})
    patcher.start()
    test_case.addCleanup(patcher.stop)
