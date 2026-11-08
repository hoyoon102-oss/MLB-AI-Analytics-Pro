"""Diagnostics remain opt-in and bilingual; production storage is never touched."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class PerformanceUITests(unittest.TestCase):
    def test_hidden_by_default(self):
        with patch.dict(os.environ, MLB_ANALYTICS_DEVELOPER='0'):
            app=AppTest.from_string('from components.system_performance_ui import page\npage()').run()
            self.assertEqual(len(app.title),0)
            self.assertEqual(len(app.exception),0)

    def test_bilingual_isolated_database(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                MLB_ANALYTICS_DEVELOPER='1',MLB_ANALYTICS_DB_PATH=str(Path(directory)/'test.db')):
            for language,title in [('ko','시스템 상태'),('en','System Performance')]:
                app=AppTest.from_string('from components.system_performance_ui import page\npage()')
                app.session_state['ui_language']=language
                app.run()
                self.assertEqual(len(app.exception),0)
                self.assertEqual(app.title[0].value,title)
                self.assertTrue(app.button[-1].disabled)
