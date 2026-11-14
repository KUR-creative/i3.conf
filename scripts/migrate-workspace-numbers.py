#!/usr/bin/env python3
"""One-time N1 migration. Preview by default; --apply changes the live session."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import uuid


FORWARD = {str(n): str(10 + (n + 1) // 2 if n % 2 else n // 2)
           for n in range(1, 11)}


def plan(workspaces, reverse=False, token=None):
    mapping = {v: k for k, v in FORWARD.items()} if reverse else FORWARD
    if {w['output'] for w in workspaces} != {'DP-1', 'HDMI-0'}:
        raise ValueError('Both DP-1 and HDMI-0 must be present, with no other outputs.')
    names = [w['name'] for w in workspaces]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate workspace names.')
    for w in workspaces:
        if w['name'] not in mapping:
            raise ValueError(f"Unexpected workspace: {w['name']!r}; no changes made.")
        old = mapping[w['name']] if reverse else w['name']
        expected = 'DP-1' if int(old) % 2 else 'HDMI-0'
        if w['output'] != expected:
            raise ValueError(f"Workspace {w['name']} is on {w['output']}, expected {expected}.")
    token = token or uuid.uuid4().hex
    temporary = {n: f'n1-migrate-{token}-{n}' for n in names}
    quote = json.dumps
    commands = [f'rename workspace {quote(n)} to {quote(temporary[n])}' for n in names]
    # Old output rules must not apply when the final numeric names are assigned.
    commands.append('reload')
    commands.extend(f'rename workspace {quote(temporary[n])} to {quote(mapping[n])}'
                    for n in names)
    return commands, {w['id']: mapping[w['name']] for w in workspaces}


def ipc(kind):
    return json.loads(subprocess.check_output(['i3-msg', '-t', kind], text=True))


def verify(before, after, expected):
    by_id = {w['id']: w for w in after}
    if set(by_id) != set(expected):
        raise ValueError('Workspace IDs changed; inspect the saved snapshot.')
    for w in before:
        actual = by_id[w['id']]
        if actual['name'] != expected[w['id']]:
            raise ValueError(f"Unexpected final name: {actual['name']}")
        for key in ('output', 'visible', 'focused'):
            if actual[key] != w[key]:
                raise ValueError(f"Workspace {actual['name']}: {key} changed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reverse', action='store_true',
                        help='Restore old numbering; restore old config BEFORE applying.')
    parser.add_argument('--config', default=str(Path.home() / '.config/i3/config'))
    args = parser.parse_args()
    before = ipc('get_workspaces')
    commands, expected = plan(before, args.reverse)
    config = Path(args.config).expanduser().resolve()
    active = ipc('get_version').get('loaded_config_file_name')
    if not active or Path(active).expanduser().resolve() != config:
        raise ValueError(f'Active config differs from {config}: {active!r}')
    # Guard against a second application, or reversing with the new config.
    workspace_config = config.parent / 'config.d/workspaces.conf'
    marker = 'set $ws1 "1"' if args.reverse else 'set $left1 "11"'
    if marker not in workspace_config.read_text():
        raise ValueError('Config does not match the requested migration direction.')
    subprocess.run(['i3', '-C', '-c', str(config)], check=True)
    print('\n'.join(commands), flush=True)
    if not args.apply:
        print('Preview only. Add --apply to rename workspaces and reload.')
        return
    with tempfile.NamedTemporaryFile(mode='w', prefix='i3-n1-', suffix='.json',
                                     dir='/tmp', delete=False) as saved:
        json.dump({'before': before, 'commands': commands}, saved, indent=2)
        print(f'Snapshot: {saved.name}', flush=True)
    # Recheck before mutation in case the session changed during validation.
    if ipc('get_workspaces') != before:
        raise ValueError('Workspace state changed. Run again.')
    replies = json.loads(subprocess.check_output(['i3-msg', '; '.join(commands)], text=True))
    if len(replies) != len(commands) or not all(r.get('success') for r in replies):
        raise ValueError(f'IPC command failed; partial changes possible: {replies}')
    verify(before, ipc('get_workspaces'), expected)
    print('Migration verified: workspace IDs, outputs, visibility and focus preserved.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'workspace migration: {error}') from error
