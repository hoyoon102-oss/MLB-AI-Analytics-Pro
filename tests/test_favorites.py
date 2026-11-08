from utils.paths import PROJECT_ROOT
"""Favorites tests use isolated temporary directories, never personal data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import utils.favorites as favorites
import tests.test_search as test_search

PLAYER = {"id": 10, "fullName": "Sho Example", "birthDate": "1994-01-01",
          "currentTeam": {"id": 999, "name": "Stale Team"}}


class FavoritesStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested" / "favorites.json"

    def test_missing_and_empty_files(self):
        self.assertEqual(favorites.load_favorites(self.path), ([], None))
        self.assertTrue(self.path.parent.is_dir())
        self.path.write_text("", encoding="utf-8")
        people, warning = favorites.load_favorites(self.path)
        self.assertEqual(people, [])
        self.assertTrue(warning)

    def test_add_remove_and_no_stale_team_metadata(self):
        people, added = favorites.toggle_favorite(PLAYER, self.path)
        self.assertTrue(added)
        self.assertEqual(people[0]["id"], 10)
        self.assertNotIn("currentTeam", people[0])
        self.assertEqual(favorites.load_favorites(self.path)[0], people)
        people, added = favorites.toggle_favorite(PLAYER, self.path)
        self.assertFalse(added)
        self.assertEqual(people, [])
        self.assertEqual(favorites.load_favorites(self.path)[0], [])

    def test_duplicate_ids_and_identical_names(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({"players": [PLAYER, PLAYER,
            dict(PLAYER, id=20)]}), encoding="utf-8")
        people, _ = favorites.load_favorites(self.path)
        self.assertEqual({person["id"] for person in people}, {10, 20})
        self.assertEqual(len(people), 2)

    def test_corrupted_file_preserved_then_backed_up_on_save(self):
        self.path.parent.mkdir()
        raw = b'{"broken JSON'
        self.path.write_bytes(raw)
        people, warning = favorites.load_favorites(self.path)
        self.assertEqual(people, [])
        self.assertTrue(warning)
        self.assertEqual(self.path.read_bytes(), raw)
        favorites.toggle_favorite(PLAYER, self.path)
        backups = list(self.path.parent.glob("utils.favorites.backup.*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), raw)
        self.assertEqual(favorites.load_favorites(self.path)[0][0]["id"], 10)

    def test_partial_invalid_schema_and_invalid_utf8(self):
        self.path.parent.mkdir()
        for raw in (b'null', b'{"players":null}', b'\xff'):
            self.path.write_bytes(raw)
            self.assertTrue(favorites.load_favorites(self.path)[1])
        self.path.write_text(json.dumps({"players": [PLAYER, {"id": True}, None]}), encoding="utf-8")
        people, warning = favorites.load_favorites(self.path)
        self.assertEqual(len(people), 1)
        self.assertTrue(warning)

    def test_atomic_write_failure_preserves_previous_file(self):
        favorites.toggle_favorite(PLAYER, self.path)
        original = self.path.read_bytes()
        with patch("utils.favorites.os.replace", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                favorites.toggle_favorite(dict(PLAYER, id=20), self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".favorites-*.tmp")), [])

    def test_persists_in_new_python_process(self):
        favorites.toggle_favorite(PLAYER, self.path)
        result = subprocess.run([sys.executable, "-c",
            "from utils.favorites import load_favorites; import sys; print(load_favorites(sys.argv[1])[0][0]['id'])",
            str(self.path)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "10")


class FavoritesUITests(unittest.TestCase):
    component = test_search.SearchUITests.component
    request = test_search.SearchUITests.request
    select = test_search.SearchUITests.select
    def setUp(self):
        test_search.SearchUITests.setUp(self)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "favorites.json"
        environment = patch.dict(os.environ, {"MLB_ANALYTICS_DATA_DIR": directory.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_initial_default_name_search_and_no_auto_selection(self):
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        self.assertEqual(ui.radio(key="dashboard_mode").value, "이름 검색")
        self.assertEqual(ui.radio(key="dashboard_mode").options, ["이름 검색", "즐겨찾기"])
        self.assertFalse(ui.metric)
        self.assertFalse(ui.button(key="dashboard_reset").disabled)
        ui.sidebar.radio[0].set_value("선수 비교").run()
        for key in ("compare_0", "compare_1"):
            self.assertEqual(ui.radio(key=f"{key}_mode").value, "이름 검색")
        self.assertFalse(ui.table)
        self.assertFalse(ui.exception)

    def test_add_remove_star_preserves_selected_season_and_team(self):
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        ui.selectbox(key="dashboard_team").set_value(1).run()
        self.select(ui, "dashboard")
        self.assertEqual(ui.button(key="dashboard_star").label, "☆")
        ui.button(key="dashboard_star").click().run()
        self.assertEqual(ui.button(key="dashboard_star").label, "★")
        self.assertEqual(len(favorites.load_favorites(self.path)[0]), 1)
        self.assertEqual(ui.selectbox(key="dashboard_team").value, 1)
        self.assertEqual(ui.selectbox(key="selected_season").value, 2024)
        self.assertEqual(len(ui.metric), 6)
        ui.button(key="dashboard_star").click().run()
        self.assertEqual(ui.button(key="dashboard_star").label, "☆")
        self.assertEqual(favorites.load_favorites(self.path)[0], [])
        self.assertEqual(len(ui.metric), 6)
        self.assertEqual(ui.selectbox(key="dashboard_team").value, 1)

    def test_shared_favorites_and_removal_does_not_clear_comparison(self):
        favorites.toggle_favorite(PLAYER, self.path)
        favorites.toggle_favorite({"id": 20, "fullName": "Same Name"}, self.path)
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        ui.sidebar.radio[0].set_value("선수 비교").run()
        for key, value in (("compare_0", 10), ("compare_1", 20)):
            ui.radio(key=f"{key}_mode").set_value("즐겨찾기").run()
            self.assertEqual(len(ui.selectbox(key=f"{key}_favorite_choice").options), 2)
            self.assertIsNone(ui.selectbox(key=f"{key}_favorite_choice").value)
            ui.selectbox(key=f"{key}_favorite_choice").set_value(value).run()
        self.assertEqual(len(ui.table), 1)
        ui.button(key="compare_0_star").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.button(key="compare_0_star").label, "☆")
        self.assertEqual(len(ui.selectbox(key="compare_1_favorite_choice").options), 1)
        self.assertEqual(len(ui.table), 1)
        self.assertEqual(ui.session_state["compare_0_chosen"]["id"], 10)

    def test_favorite_removal_empty_state_keeps_current_stats(self):
        favorites.toggle_favorite(PLAYER, self.path)
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        ui.radio(key="dashboard_mode").set_value("즐겨찾기").run()
        ui.selectbox(key="dashboard_favorite_choice").set_value(10).run()
        ui.button(key="dashboard_star").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.metric), 6)
        self.assertTrue(any("저장한 즐겨찾기가 없습니다" in info.value for info in ui.info))
        self.assertEqual(ui.button(key="dashboard_star").label, "☆")

    def test_navigation_and_reruns_preserve_player_and_filters(self):
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        ui.selectbox(key="dashboard_team").set_value(1).run()
        self.select(ui, "dashboard")
        ui.sidebar.radio[0].set_value("선수 비교").run()
        ui.sidebar.radio[0].set_value("선수 기록").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox(key="dashboard_team").value, 1)
        self.assertEqual(ui.session_state["dashboard_chosen"]["id"], 10)
        self.assertEqual(len(ui.metric), 6)

    def test_file_error_warning_and_failed_star_preserve_selection(self):
        self.path.write_text("broken", encoding="utf-8")
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        self.assertTrue(any("손상" in warning.value for warning in ui.warning))
        self.select(ui, "dashboard")
        with patch("utils.favorites.os.replace", side_effect=OSError("denied")):
            ui.button(key="dashboard_star").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.button(key="dashboard_star").label, "☆")
        self.assertEqual(len(ui.metric), 6)
        self.assertTrue(any("저장하지 못했습니다" in warning.value for warning in ui.warning))

    def test_favorite_season_affiliation_uses_roster_not_saved_team(self):
        favorites.toggle_favorite(PLAYER, self.path)
        ui = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
        ui.radio(key="dashboard_mode").set_value("즐겨찾기").run()
        ui.selectbox(key="dashboard_favorite_choice").set_value(10).run()
        ui.selectbox(key="selected_season").set_value(2020).run()
        self.assertFalse(ui.exception)
        captions = " ".join(item.value for item in ui.caption)
        self.assertIn("2020", captions)
        self.assertIn("Alpha Club", captions)
        self.assertNotIn("Stale Team", captions)
        self.assertEqual(ui.session_state["dashboard_chosen"]["id"], 10)
        self.assertEqual(ui.selectbox(key="selected_season").value, 2020)
        self.assertTrue(ui.info)  # Fixture contains 2024 stats only, never invent 2020 values.


if __name__ == "__main__":
    unittest.main()
