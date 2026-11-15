#!/usr/bin/env python3
"""Switch regular i3 workspace pairs and remember one previous workspace label."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys


LABELS = {str(n % 10): f'{n}:{n % 10}' for n in range(1, 11)}
LABELS.update({f'F{n}': f'{n + 10}:F{n}' for n in range(1, 11)})
NAMES = {name: label for label, name in LABELS.items()}


def ipc(kind, command=None):
    args = ['i3-msg', '-r', '-t', kind]
    if command is not None:
        args.append(command)
    reply = json.loads(subprocess.check_output(args, text=True, timeout=5))
    if kind == 'command' and not all(item.get('success') for item in reply):
        raise RuntimeError(f'i3 command failed: {reply}')
    return reply


def state_path():
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}')
    if not runtime.is_dir() or runtime.stat().st_uid != os.getuid():
        raise RuntimeError('A user-owned XDG_RUNTIME_DIR is required')
    return runtime / 'i3-workspace-pair'


def switch(target, state):
    spaces = ipc('get_workspaces')
    visible = [ws for ws in spaces if ws['visible']]
    current = next((ws for ws in spaces if ws['focused']), None)
    if (len(visible) != 2 or len({ws['output'] for ws in visible}) != 2
            or current is None or any(ws['name'] not in NAMES for ws in visible)
            or sum(NAMES[ws['name']].startswith('F') for ws in visible) != 1):
        raise RuntimeError('Expected one known left and one known right workspace on two outputs')
    number = 10 if target == '0' else int(target)
    left, right = LABELS[f'F{number}'], LABELS[target]
    same = {ws['name'] for ws in visible} == {left, right}
    ipc('command', f'workspace --no-auto-back-and-forth number {left}; '
                   f'workspace --no-auto-back-and-forth number {right}')
    after = ipc('get_workspaces')
    if ({ws['name'] for ws in after if ws['visible']} != {left, right}
            or not any(ws['name'] == right and ws['focused'] for ws in after)):
        raise RuntimeError('Pair switch did not reach the expected workspaces and focus')
    if not same:
        state.seek(0)
        state.write(NAMES[current['name']] + '\n')
        state.truncate()
        state.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['reset'] + [str(n) for n in range(10)])
    target = parser.parse_args().target
    path = state_path()
    # Reset existing contents without replacing the inode used by waiting callers.
    if target == 'reset' and not path.exists():
        return
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+', encoding='utf-8') as state:
        fcntl.flock(state, fcntl.LOCK_EX)
        os.fchmod(state.fileno(), 0o600)
        if target == 'reset':
            state.truncate(0)
        else:
            switch(target, state)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'workspace-pair: {error}', file=sys.stderr)
        sys.exit(1)
