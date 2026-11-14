from pathlib import Path
import runpy
import unittest

plan = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                         'scripts/switch-workspace-pair.py'))['plan']


class PairTest(unittest.TestCase):
    def workspaces(self, focus='DP-1'):
        return [dict(name='12:F2', num=12, output='DP-1', visible=True, focused=focus == 'DP-1'),
                dict(name='5:5', num=5, output='HDMI-0', visible=True, focused=focus == 'HDMI-0')]

    def test_source_monitor_is_focused_last(self):
        self.assertEqual(plan(self.workspaces()),
                         ['workspace --no-auto-back-and-forth "1:1"',
                          'workspace --no-auto-back-and-forth "11:F1"'])
        self.assertEqual(plan(self.workspaces('HDMI-0')),
                         ['workspace --no-auto-back-and-forth "11:F1"',
                          'workspace --no-auto-back-and-forth "1:1"'])

    def test_already_visible_pair_is_noop(self):
        ws = self.workspaces()
        ws[0].update(name='11:F1', num=11)
        ws[1].update(name='1:1', num=1)
        self.assertEqual(plan(ws), [])

    def test_one_side_already_target_still_restores_focus(self):
        ws = self.workspaces()
        ws[0].update(name='11:F1', num=11)
        self.assertEqual(len(plan(ws)), 2)
        self.assertTrue(plan(ws)[-1].endswith('"11:F1"'))

    def test_missing_output_and_wrong_target_rejected(self):
        with self.assertRaises(ValueError):
            plan(self.workspaces()[:1])
        for change in [dict(name='11:wrong', num=11), dict(name='1:1', num=1)]:
            ws = self.workspaces()
            ws[0].update(change)
            with self.assertRaises(ValueError):
                plan(ws)

    def test_inactive_target_on_correct_output_is_allowed(self):
        ws = self.workspaces()
        ws.append(dict(name='11:F1', num=11, output='DP-1', visible=False, focused=False))
        self.assertEqual(len(plan(ws)), 2)


if __name__ == '__main__':
    unittest.main()
