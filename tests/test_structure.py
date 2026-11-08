"""Package boundaries and working-directory independent asset/storage paths."""
import ast
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from utils.paths import PROJECT_ROOT
from utils.favorites import favorites_path
from utils.i18n import ROOT, settings_path, catalog


class StructureTests(unittest.TestCase):
    def test_paths_from_another_directory(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('MLB_ANALYTICS_DATA_DIR', None)
            try:
                os.chdir(directory)
                self.assertEqual(favorites_path(), PROJECT_ROOT/'data/favorites.json')
                self.assertEqual(settings_path(), PROJECT_ROOT/'data/settings.json')
                self.assertEqual(ROOT, PROJECT_ROOT/'translations')
                self.assertTrue(catalog('ko'))
                self.assertTrue(catalog('en'))
                self.assertTrue((PROJECT_ROOT/'components/ui_styles.css').is_file())
            finally:
                os.chdir(previous)

    def test_import_graph_is_acyclic(self):
        files = [p for folder in ('analytics','components','services','utils')
                 for p in (PROJECT_ROOT/folder).glob('*.py')]
        names = {'.'.join(p.relative_to(PROJECT_ROOT).with_suffix('').parts) for p in files}
        graph = {}
        for p in files:
            name = '.'.join(p.relative_to(PROJECT_ROOT).with_suffix('').parts)
            edges = set()
            for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Import):
                    edges.update(a.name for a in node.names if a.name in names)
                elif isinstance(node, ast.ImportFrom) and node.module in names:
                    edges.add(node.module)
            graph[name] = edges
        done, visiting = set(), set()
        def visit(name):
            self.assertNotIn(name, visiting, 'Circular import: '+name)
            if name in done:
                return
            visiting.add(name)
            for child in graph[name]:
                visit(child)
            visiting.remove(name)
            done.add(name)
        for name in graph:
            visit(name)
        self.assertFalse((PROJECT_ROOT/'pages').exists())
