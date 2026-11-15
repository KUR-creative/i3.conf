#!/usr/bin/env python3
"""Switch regular i3 workspace pairs and remember previous and per-pair focus."""
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


def pair_number(label):
    return int(label[1:]) if label.startswith('F') else (10 if label == '0' else int(label))


def read_history(state):
    raw = state.read().strip()
    defaults = {'previous': None, 'focus': [str(n % 10) for n in range(1, 11)]}
    # Upgrade the old single-label format after the next successful switch.
    if raw in LABELS:
        defaults['previous'] = raw
        defaults['focus'][pair_number(raw) - 1] = raw
        return defaults
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return defaults
    if not isinstance(data, dict):
        return defaults
    previous, focus = data.get('previous'), data.get('focus')
    if previous is not None and (not isinstance(previous, str) or previous not in LABELS):
        return defaults
    if (not isinstance(focus, list) or len(focus) != 10
            or any(value not in (f'F{n}', str(n % 10)) for n, value in enumerate(focus, 1))):
        return defaults
    return {'previous': previous, 'focus': focus}


def switch(target, state):
    history = read_history(state)
    restoring = target == 'previous'
    if restoring and history['previous'] is None:
        return
    spaces = ipc('get_workspaces')
    visible = [ws for ws in spaces if ws['visible']]
    current = next((ws for ws in spaces if ws['focused']), None)
    if (len(visible) != 2 or len({ws['output'] for ws in visible}) != 2
            or current is None or any(ws['name'] not in NAMES for ws in visible)
            or sum(NAMES[ws['name']].startswith('F') for ws in visible) != 1):
        raise RuntimeError('Expected one known left and one known right workspace on two outputs')
    departure = NAMES[current['name']]
    history['focus'][pair_number(departure) - 1] = departure
    target = history['previous'] if restoring else history['focus'][pair_number(target) - 1]
    number = pair_number(target)
    left, right = LABELS[f'F{number}'], LABELS[str(number % 10)]
    focused = LABELS[target]
    same = {ws['name'] for ws in visible} == {left, right}
    first, last = (right, left) if target.startswith('F') else (left, right)
    ipc('command', f'workspace --no-auto-back-and-forth number {first}; '
                   f'workspace --no-auto-back-and-forth number {last}')
    after = ipc('get_workspaces')
    if ({ws['name'] for ws in after if ws['visible']} != {left, right}
            or not any(ws['name'] == focused and ws['focused'] for ws in after)):
        raise RuntimeError('Pair switch did not reach the expected workspaces and focus')
    if restoring or not same:
        history['previous'] = departure
    history['focus'][number - 1] = target
    state.seek(0)
    json.dump(history, state, indent=2)
    state.write('\n')
    state.truncate()
    state.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['reset', 'previous'] + [str(n) for n in range(10)])
    target = parser.parse_args().target
    path = state_path()
    # Reset existing contents without replacing the inode used by waiting callers.
    if target in ('reset', 'previous') and not path.exists():
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
