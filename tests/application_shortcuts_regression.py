#!/usr/bin/env python3
"""Check launch-mode routing and X11 key delivery on an isolated i3 display."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from unittest.mock import patch

from workspace_regression import CONFIG, Desktop, require, workspace


SHORTCUTS = CONFIG.parents[1] / 'config.d/shortcuts.conf'


def run(shortcuts, xvfb):
    with tempfile.TemporaryDirectory(prefix='i3-launch-regression-') as temporary:
        root = Path(temporary)
        binary = root / 'bin'
        binary.mkdir()
        log = root / 'launches.jsonl'
        mock = binary / 'ptyxis'
        mock.write_text('''#!/usr/bin/python3
import json, os, sys
with open(os.environ['I3_LAUNCH_TEST_LOG'], 'a') as log:
    print(json.dumps({'args': sys.argv[1:], 'overlay': os.environ.get('G_RESOURCE_OVERLAYS')}), file=log)
''')
        mock.chmod(0o755)
        source = root / 'workspaces-and-shortcuts.conf'
        source.write_text(CONFIG.read_text() + '\n' + shortcuts.read_text())
        # The real Ptyxis executable and the real desktop are never used.
        with patch.dict(os.environ, {'PATH': str(binary) + os.pathsep + os.environ['PATH'],
                                     'I3_LAUNCH_TEST_LOG': str(log)}):
            with Desktop(source, xvfb, 4) as desktop:
                def xdo(*arguments):
                    subprocess.run(['xdotool', *arguments], env=desktop.env,
                                   check=True, capture_output=True, text=True, timeout=5)

                def mode():
                    return desktop.ipc('get_binding_state')['name']

                def launches():
                    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

                def enter_mode():
                    xdo('key', '--clearmodifiers', 'super+Return')
                    desktop.wait(lambda: mode().startswith('Launch:'), 'launch mode entered')

                def launch():
                    enter_mode()
                    xdo('key', 'Return')
                    desktop.wait(lambda: mode() == 'default', 'launch mode exited')

                title = 'launch-key-fixture'
                desktop.launch(['stdbuf', '-oL', 'xev', '-name', title, '-event', 'keyboard'])
                events = desktop.logs[-1]
                desktop.wait(lambda: title in desktop.locations(), 'key receiver mapped')
                node = desktop.locations()[title][1]
                desktop.ids[title] = node['id']

                def set_class(value):
                    xdo('set_window', '--class', value, str(node['window']))
                    desktop.wait(lambda: desktop.locations()[title][1]['window_properties']['class'] == value,
                                 'window class ' + value)
                    desktop.park_pointer(title)

                def new_window_chords():
                    events.seek(0)
                    output = events.read().decode(errors='replace')
                    count = 0
                    for event in output.split('KeyPress event')[1:]:
                        state = re.search(r'state 0x([0-9a-f]+)', event)
                        if state and int(state[1], 16) & 5 == 5 and 'keysym 0x4e, N' in event:
                            count += 1
                    return count

                set_class('ptyxis')
                for expected in (1, 2):
                    launch()
                    try:
                        desktop.wait(lambda: new_window_chords() == expected, 'Ctrl+Shift+N received')
                    except AssertionError:
                        events.seek(0)
                        print('Key receiver log:', events.read().decode(errors='replace')[-2600:])
                        desktop.logs[1].seek(0)
                        print('i3 log:', desktop.logs[1].read().decode(errors='replace')[-1800:])
                        print('Fallback launches:', launches())
                        raise
                    time.sleep(.1)
                    require(not launches(), 'Ptyxis branch also launched a generic window')
                print('PASS: focused Ptyxis receives Ctrl+Shift+N after launch mode exits', flush=True)

                set_class('Google-chrome')
                launch()
                desktop.wait(lambda: len(launches()) == 1, 'non-terminal fallback')
                time.sleep(.1)
                require(len(launches()) == 1 and new_window_chords() == 2,
                        'Non-terminal route duplicated launch or received terminal keys')
                require(launches()[0]['args'] == ['--new-window'], 'Fallback arguments changed')
                require(launches()[0]['overlay'] == '/org/gnome/Ptyxis=' + str(Path.home() / '.config/ptyxis-no-header'),
                        'Header overlay was not preserved')
                print('PASS: other app launches exactly one terminal with header overlay', flush=True)

                for side in ('left', 'right'):
                    desktop.show(workspace(side, 8))
                launch()
                desktop.wait(lambda: len(launches()) == 2, 'empty-workspace fallback')
                time.sleep(.1)
                require(len(launches()) == 2, 'Empty workspace duplicated launch')
                print('PASS: empty workspace launches exactly one terminal', flush=True)

                enter_mode()
                xdo('key', 'Escape')
                desktop.wait(lambda: mode() == 'default', 'launch cancelled')
                time.sleep(.1)
                require(len(launches()) == 2, 'Escape launched an application')
                print('PASS: Escape cancels without launching', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shortcuts', type=Path, default=SHORTCUTS)
    parser.add_argument('--xvfb', default=shutil.which('Xvfb'))
    args = parser.parse_args()
    if not args.xvfb:
        parser.error('Xvfb is required; pass --xvfb /path/to/Xvfb')
    for name in ('i3', 'i3-msg', 'xdotool', 'xprop', 'xmessage', 'xev', 'stdbuf'):
        if not shutil.which(name):
            parser.error('Missing executable: ' + name)
    run(args.shortcuts, args.xvfb)
