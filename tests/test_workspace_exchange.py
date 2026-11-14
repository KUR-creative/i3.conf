from pathlib import Path
import re
import runpy
import unittest

exchange = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                             'scripts/exchange-workspace-pair.py'))


class ExchangeTest(unittest.TestCase):
    def state(self, left=12, right=5, focus_left=False, targets=True, empty=False):
        specs = [(left, 'DP-1', True, focus_left), (right, 'HDMI-0', True, not focus_left)]
        if targets:
            specs += [(n, out, False, False) for n, out in [(11, 'DP-1'), (1, 'HDMI-0')]
                      if n not in (left, right)]
        ws, children = [], []
        for n, output, visible, focused in specs:
            name = f'{n}:{n % 10}' if n <= 10 else f'{n}:F{n - 10}'
            ws.append(dict(id=n, num=n, name=name, output=output, visible=visible, focused=focused))
            leaf = dict(id=n + 100, window=n + 1000, layout='splith', focused=focused,
                        fullscreen_mode=1 if n == left else 0)
            children.append(dict(id=n, type='workspace', name=name, focused=focused and empty,
                                 nodes=[] if empty else [leaf], floating_nodes=[]))
        return ws, dict(id=9999, nodes=children, floating_nodes=[])

    def simulate(self, ws, commands):
        names = {w['name']: w['id'] for w in ws}
        for command in commands:
            match = re.fullmatch(r'rename workspace "([^"]+)" to "([^"]+)"', command)
            if match:
                old, new = match.groups()
                self.assertNotIn(new, names, 'rename must not collide')
                names[new] = names.pop(old)
        return names

    def test_exchange_both_sides_without_merging(self):
        ws, tree = self.state()
        commands, expected, focused = exchange['plan'](ws, tree, token='test')
        names = self.simulate(ws, commands)
        self.assertEqual(names, {'11:F1': 12, '12:F2': 11, '1:1': 5, '5:5': 1})
        self.assertEqual(expected, {12: '11:F1', 11: '12:F2', 5: '1:1', 1: '5:5'})
        self.assertEqual(commands[-1], '[con_id=105] focus')
        self.assertEqual(focused, 105)

    def test_left_focus_and_empty_focus(self):
        for empty, wanted in [(False, 112), (True, 12)]:
            ws, tree = self.state(focus_left=True, empty=empty)
            commands, _, focused = exchange['plan'](ws, tree)
            self.assertEqual(focused, wanted)
            self.assertEqual(commands[-1], f'[con_id={wanted}] focus')

    def test_missing_targets_and_same_side(self):
        ws, tree = self.state(left=11, targets=False)
        commands, expected, _ = exchange['plan'](ws, tree)
        self.assertEqual(self.simulate(ws, commands), {'11:F1': 11, '1:1': 5})
        self.assertEqual(expected[11], '11:F1')
        self.assertEqual(len(commands), 3)

    def test_already_at_pair_is_noop(self):
        ws, tree = self.state(left=11, right=1)
        self.assertEqual(exchange['plan'](ws, tree)[0], [])

    def test_invalid_output_and_global_fullscreen_rejected(self):
        ws, tree = self.state()
        ws[0]['output'] = 'HDMI-0'
        with self.assertRaises(ValueError):
            exchange['plan'](ws, tree)
        ws, tree = self.state()
        tree['nodes'][0]['nodes'][0]['fullscreen_mode'] = 2
        with self.assertRaises(ValueError):
            exchange['plan'](ws, tree)

    def test_signatures_cover_floating_layout_and_fullscreen(self):
        ws, tree = self.state()
        node = tree['nodes'][0]
        original = exchange['signature'](node)
        node['name'] = '11:F1'
        node['focused'] = True
        self.assertEqual(exchange['signature'](node), original)
        node['nodes'][0]['layout'] = 'tabbed'
        self.assertNotEqual(exchange['signature'](node), original)
        node['floating_nodes'] = [node['nodes'].pop()]
        self.assertNotEqual(exchange['signature'](node), original)


if __name__ == '__main__':
    unittest.main()
