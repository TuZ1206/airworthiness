import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_build_and_report_commands_create_real_outputs(self):
        self.assertIsNotNone(importlib.util.find_spec('airworthiness.cli'))
        cli = importlib.import_module('airworthiness.cli')
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / 'test.sqlite3'
            output = Path(tmp) / 'report.md'
            self.assertEqual(cli.main(['build', '--database', str(database)]), 0)
            self.assertTrue(database.is_file())
            self.assertEqual(cli.main(['report', '--database', str(database), '--output', str(output)]), 0)
            self.assertIn('189', output.read_text(encoding='utf-8'))
            self.assertIn('九章', output.read_text(encoding='utf-8'))
