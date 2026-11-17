#!/usr/bin/env python3
"""Exercise the installed i3-swap-focus against an isolated i3 session."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from workspace_regression import CONFIG, Desktop, require, workspace


WATCHER = Path.home() / '.local/bin/i3-swap-focus'


@contextmanager
def start_watcher(desktop, config):
    startup = [line for line in config.read_text().splitlines()
               if line.startswith('exec_always ') and 'i3-swap-focus' in line]
    require(len(startup) == 1, 'Expected one watcher startup command')
    pid_file = Path(desktop.env['XDG_RUNTIME_DIR']) / 'swap_focus.pid'
    # Reproduce first installation: reload reads the new directive but does not run it.
    with (desktop.root / 'config').open('a') as stream:
        stream.write('\n' + startup[0] + '\n')
    desktop.command('reload')
    time.sleep(.2)
    require(not pid_file.exists(), 'Reload unexpectedly started the watcher')
    print('PASS: first reload alone does not start the new watcher', flush=True)
    pid = None
    try:
        # Use the configured shell command through i3, as for applying it to a live session.
        desktop.command(startup[0].replace('exec_always ', 'exec ', 1))
        desktop.wait(lambda: pid_file.exists() and pid_file.read_text().strip().isdigit(),
                     'watcher PID')
        pid = int(pid_file.read_text())
        time.sleep(.2)
        require(Path(f'/proc/{pid}').exists(), 'Watcher exited during startup')
        yield pid
    finally:
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def run(config, xvfb):
    require('exec_always --no-startup-id flock -n -F "$XDG_RUNTIME_DIR/i3-swap-focus.lock" '
            '~/.local/bin/i3-swap-focus' in config.read_text(), 'Missing guarded startup')
    with Desktop(config, xvfb, 4) as desktop, start_watcher(desktop, config) as watcher_pid:
        runtime = Path(desktop.env['XDG_RUNTIME_DIR'])
        pid_file = runtime / 'swap_focus.pid'
        guard = ['flock', '-n', '-F', str(runtime / 'i3-swap-focus.lock'), str(WATCHER)]
        before_history = desktop.history()

        def focus(title):
            desktop.focus(title)
            desktop.wait(lambda: desktop.locations()[title][1]['focused'], 'focus ' + title)
            time.sleep(.06)

        def back(title, numlock=False):
            desktop.keys.press('Tab', numlock=numlock, modifier='Alt_L')
            desktop.wait(lambda: desktop.locations()[title][1]['focused'], 'return to ' + title)
            time.sleep(.1)
            require(desktop.locations()[title][1]['focused'], 'Return focus did not settle')
            require(desktop.history() == before_history, 'Global return changed pair JSON')

        # No focus events have occurred since startup: no prior window to return to.
        initial = next(title for title, (_, node) in desktop.locations().items() if node['focused'])
        back(initial)
        print('PASS: empty focus history leaves the current window alone', flush=True)

        for numlock in (False, True):
            for first, second in [('left-source', 'left-existing'),
                                  ('left-source', 'right-source'),
                                  ('left-source', 'right-existing')]:
                desktop.move('left-source', workspace('left', 1))
                desktop.move('left-existing', workspace('left', 1))
                desktop.move('right-source', workspace('left', 3))
                desktop.move('right-existing', workspace('right', 5))
                # Make two distinct focus events, including when the first was already active.
                seed = next(title for title in desktop.ids if title not in (first, second))
                focus(seed)
                focus(first)
                focus(second)
                locations = {title: name for title, (name, _) in desktop.locations().items()}
                desktop.keys.press('grave', numlock=numlock)
                time.sleep(.1)
                require(desktop.locations()[second][1]['focused'],
                        'Removed Mod+grave binding still changed focus')
                back(first, numlock)
                back(second, numlock)
                require({title: name for title, (name, _) in desktop.locations().items()} == locations,
                        'Global return moved windows')
        print('PASS: same-workspace, other-workspace and other-output round trips; both Num Lock states',
              flush=True)

        # Mouse changes must enter the same event-based history.
        desktop.show(workspace('left', 1))
        desktop.show(workspace('right', 5))
        desktop.park_pointer('left-source')
        time.sleep(.08)
        desktop.keys.pointer(desktop.locations()['right-existing'][1]['rect'])
        desktop.wait(lambda: desktop.locations()['right-existing'][1]['focused'], 'mouse focus')
        time.sleep(.08)
        back('left-source')
        print('PASS: pointer-driven focus participates in history', flush=True)

        result = subprocess.run(guard, env=desktop.env, capture_output=True, timeout=5)
        require(result.returncode == 1, 'Second watcher was not rejected by flock')
        desktop.command('reload')
        time.sleep(.2)
        require(Path(f'/proc/{watcher_pid}').exists() and int(pid_file.read_text()) == watcher_pid,
                'Reload replaced or stopped the watcher')
        focus('left-source')
        focus('right-existing')
        back('left-source')
        print('PASS: single-instance guard and focus history survive reload', flush=True)

        # Upstream only remembers two windows. A closed prior target is a no-op, not a move.
        focus('left-source')
        focus('right-existing')
        desktop.command(f'[con_id={desktop.ids["left-source"]}] kill')
        desktop.wait(lambda: 'left-source' not in desktop.locations(), 'closed prior target')
        desktop.ids.pop('left-source')
        back('right-existing')
        require(Path(f'/proc/{watcher_pid}').exists(), 'Closed target terminated watcher')
        focus('left-existing')
        focus('right-existing')
        back('left-existing')
        print('PASS: closed prior window is harmless and later focus events still work', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--xvfb', default=shutil.which('Xvfb'))
    args = parser.parse_args()
    if not args.xvfb:
        parser.error('Xvfb is required; pass --xvfb /path/to/Xvfb')
    if not WATCHER.is_file():
        parser.error('Install i3-swap-focus first')
    run(args.config, args.xvfb)
