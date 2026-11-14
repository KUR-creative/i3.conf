import runpy
from pathlib import Path
import unittest

labels = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/label-workspaces.py'))


class LabelsTest(unittest.TestCase):
    def workspaces(self):
        return [dict(id=n, num=n, name=str(n),
                     output='HDMI-0' if n <= 10 else 'DP-1') for n in range(1, 21)]

    def test_labels_and_round_trip(self):
        before = self.workspaces()
        commands, expected = labels['plan'](before)
        self.assertEqual(commands[0], 'reload')
        self.assertEqual(len(commands), 21)
        self.assertEqual(expected[10], '10:0')
        self.assertEqual(expected[11], '11:F1')
        self.assertEqual(expected[20], '20:F10')
        after = [dict(w, name=expected[w['id']]) for w in before]
        self.assertEqual(labels['plan'](after)[0], ['reload'])
        self.assertEqual(labels['plan'](after, reverse=True)[1],
                         {w['id']: w['name'] for w in before})

    def test_duplicate_number_unknown_name_and_wrong_output(self):
        for change in [dict(num=2, name='2'), dict(name='11:custom'), dict(output='DP-1')]:
            workspaces = self.workspaces()
            workspaces[0].update(change)
            with self.assertRaises(ValueError):
                labels['plan'](workspaces)


if __name__ == '__main__':
    unittest.main()
