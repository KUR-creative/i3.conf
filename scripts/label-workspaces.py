#!/usr/bin/env python3
"""P2 workspace labels: preview by default, --apply to rename and reload."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


LABELS = {str(n): f'{n}:{n % 10}' if n <= 10 else f'{n}:F{n - 10}'
          for n in range(1, 21)}


def plan(workspaces, reverse=False):
    if {w['output'] for w in workspaces} != {'DP-1', 'HDMI-0'}:
        raise ValueError('Both DP-1 and HDMI-0 must be present, with no other outputs.')
    commands = ['reload']
    expected = {}
    numbers = set()
    for w in workspaces:
        number = str(w['num'])
        if number not in LABELS or w['name'] not in (number, LABELS[number]):
            raise ValueError(f"Unexpected workspace: {w['name']!r}")
        if number in numbers:
            raise ValueError(f'Duplicate workspace number: {number}')
        numbers.add(number)
        output = 'HDMI-0' if int(number) <= 10 else 'DP-1'
        if w['output'] != output:
            raise ValueError(f"Workspace {w['name']} must be on {output}.")
        name = number if reverse else LABELS[number]
        expected[w['id']] = name
        if w['name'] != name:
            commands.append(f'rename workspace {json.dumps(w["name"])} to {json.dumps(name)}')
    return commands, expected


def ipc(kind):
    return json.loads(subprocess.check_output(['i3-msg', '-t', kind], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reverse', action='store_true',
                        help='Remove labels after reverting the P2 config.')
    args = parser.parse_args()
    config = Path.home() / '.config/i3/config'
    active = ipc('get_version').get('loaded_config_file_name')
    if not active or Path(active).resolve() != config.resolve():
        raise ValueError('A different i3 config is active.')
    marker = 'set $left1 "11"' if args.reverse else 'set $left1 "11:F1"'
    if marker not in (config.parent / 'config.d/workspaces.conf').read_text():
        raise ValueError('Config does not match the requested migration direction.')
    before = ipc('get_workspaces')
    commands, expected = plan(before, args.reverse)
    subprocess.run(['i3', '-C', '-c', str(config)], check=True)
    print('\n'.join(commands), flush=True)
    if not args.apply:
        print('Preview only. Add --apply to reload and rename.')
        return
    with tempfile.NamedTemporaryFile(mode='w', prefix='i3-p2-', suffix='.json',
                                     dir='/tmp', delete=False) as saved:
        json.dump({'before': before, 'commands': commands}, saved, indent=2)
        print(f'Snapshot: {saved.name}', flush=True)
    if ipc('get_workspaces') != before:
        raise ValueError('Workspace state changed. Run again.')
    replies = json.loads(subprocess.check_output(['i3-msg', '; '.join(commands)], text=True))
    if len(replies) != len(commands) or not all(r.get('success') for r in replies):
        raise ValueError(f'IPC failure; partial changes possible: {replies}')
    after = {w['id']: w for w in ipc('get_workspaces')}
    if set(after) != set(expected):
        raise ValueError('Workspace IDs changed; inspect the saved snapshot.')
    for w in before:
        current = after[w['id']]
        if current['name'] != expected[w['id']] or any(
                current[k] != w[k] for k in ('num', 'output', 'visible', 'focused')):
            raise ValueError('Workspace state differs from the plan; inspect the snapshot.')
    print('Labels applied; workspace IDs, numbers, outputs, visibility and focus preserved.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'workspace labels: {error}') from error
