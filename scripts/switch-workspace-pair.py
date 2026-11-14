#!/usr/bin/env python3
"""Display pair 1, ending on the previously focused monitor."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys


TARGETS = {'DP-1': '11:F1', 'HDMI-0': '1:1'}


def plan(workspaces):
    visible = [w for w in workspaces if w['visible']]
    if len(visible) != 2 or {w['output'] for w in visible} != set(TARGETS):
        raise ValueError('Pair switching requires DP-1 and HDMI-0, with one visible workspace each.')
    focused = [w for w in visible if w['focused']]
    if len(focused) != 1:
        raise ValueError('Expected exactly one focused workspace.')
    for output, target in TARGETS.items():
        number = int(target.split(':')[0])
        matches = [w for w in workspaces if w['num'] == number or w['name'] == target]
        if len(matches) > 1 or any(w['name'] != target or w['output'] != output for w in matches):
            raise ValueError(f'Unexpected workspace at target {target}.')
    if all(w['name'] == TARGETS[w['output']] for w in visible):
        return []
    current_output = focused[0]['output']
    other_output = next(output for output in TARGETS if output != current_output)
    # Finish on the source monitor, including when its target is already visible.
    return [f'workspace --no-auto-back-and-forth {json.dumps(TARGETS[output])}'
            for output in (other_output, current_output)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    # Serialize key repeats without queueing extra switches.
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    with (runtime / 'i3-workspace-pair.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        workspaces = json.loads(subprocess.check_output(['i3-msg', '-t', 'get_workspaces'], text=True))
        commands = plan(workspaces)
        if args.dry_run:
            print('\n'.join(commands) if commands else 'Pair 1 is already visible; no change.')
            return
        if commands:
            replies = json.loads(subprocess.check_output(['i3-msg', '; '.join(commands)], text=True))
            if len(replies) != len(commands) or not all(r.get('success') for r in replies):
                raise ValueError(f'Pair switch failed; partial changes possible: {replies}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'workspace pair: {error}', file=sys.stderr)
        sys.exit(1)
