import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'migration', Path(__file__).resolve().parents[1] / 'scripts/migrate-workspace-numbers.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationTest(unittest.TestCase):
    def workspaces(self):
        return [dict(id=n, name=str(n), output='DP-1' if n % 2 else 'HDMI-0',
                     visible=n <= 2, focused=n == 1) for n in range(1, 11)]

    def test_colliding_numbers_use_temporary_names_before_reload(self):
        commands, expected = migration.plan(self.workspaces(), token='test')
        self.assertEqual(commands[10], 'reload')
        self.assertTrue(all('to "n1-migrate-' in c for c in commands[:10]))
        self.assertTrue(all('rename workspace "n1-migrate-' in c for c in commands[11:]))
        self.assertEqual(expected, {1: '11', 2: '1', 3: '12', 4: '2', 5: '13',
                                    6: '3', 7: '14', 8: '4', 9: '15', 10: '5'})

    def test_round_trip_and_verification(self):
        before = self.workspaces()
        _, expected = migration.plan(before)
        after = [dict(w, name=expected[w['id']]) for w in before]
        migration.verify(before, after, expected)
        _, reverse = migration.plan(after, reverse=True)
        self.assertEqual(reverse, {w['id']: w['name'] for w in before})
        after[0]['output'] = 'HDMI-0'
        with self.assertRaises(ValueError):
            migration.verify(before, after, expected)

    def test_unexpected_names_or_outputs_are_rejected(self):
        for field, value in [('name', 'custom'), ('output', 'HDMI-0')]:
            workspaces = self.workspaces()
            workspaces[0][field] = value
            with self.assertRaises(ValueError):
                migration.plan(workspaces)

    def test_two_visible_workspaces_only(self):
        _, expected = migration.plan(self.workspaces()[:2])
        self.assertEqual(expected, {1: '11', 2: '1'})


if __name__ == '__main__':
    unittest.main()
