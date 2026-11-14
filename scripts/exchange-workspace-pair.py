#!/usr/bin/env python3
"""Exchange the visible workspaces with pair 1, preserving container trees."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid


TARGETS = {'DP-1': '11:F1', 'HDMI-0': '1:1'}


def nodes(tree):
    yield tree
    for child in tree.get('nodes', []) + tree.get('floating_nodes', []):
        yield from nodes(child)


def signature(workspace):
    """Compare content IDs/layout/fullscreen without mutable focus or geometry."""
    def content(node):
        return (node['id'], node.get('window'), node.get('layout'),
                node.get('fullscreen_mode'),
                tuple(content(n) for n in node.get('nodes', [])),
                tuple(content(n) for n in node.get('floating_nodes', [])))
    return (tuple(content(n) for n in workspace.get('nodes', [])),
            tuple(content(n) for n in workspace.get('floating_nodes', [])))


def plan(workspaces, tree, token=None):
    visible = [w for w in workspaces if w['visible']]
    if len(visible) != 2 or {w['output'] for w in visible} != set(TARGETS):
        raise ValueError('Both DP-1 and HDMI-0 must have one visible workspace.')
    focused = [w for w in visible if w['focused']]
    if len(focused) != 1:
        raise ValueError('Expected one focused workspace.')
    # Validate canonical names and outputs before using rename's assignment rules.
    seen = set()
    for w in workspaces:
        n = w['num']
        if not 1 <= n <= 20 or n in seen:
            raise ValueError('Unexpected or duplicate workspace number.')
        seen.add(n)
        name = f'{n}:{n % 10}' if n <= 10 else f'{n}:F{n - 10}'
        output = 'HDMI-0' if n <= 10 else 'DP-1'
        if w['name'] != name or w['output'] != output:
            raise ValueError(f"Unexpected name/output: {w['name']} on {w['output']}")
    all_nodes = list(nodes(tree))
    if any(n.get('fullscreen_mode') == 2 for n in all_nodes):
        raise ValueError('Exit global fullscreen before exchanging workspaces.')
    focused_nodes = [n for n in all_nodes if n.get('focused')]
    if len(focused_nodes) != 1:
        raise ValueError('Expected one focused container.')
    focused_id = focused_nodes[0]['id']
    tree_ws = {n['id']: n for n in all_nodes if n.get('type') == 'workspace'}
    if focused[0]['id'] not in tree_ws or not any(
            n['id'] == focused_id for n in nodes(tree_ws[focused[0]['id']])):
        raise ValueError('Focus changed during inspection; try again.')
    names = {w['name']: w for w in workspaces}
    expected = {w['id']: w['name'] for w in workspaces}
    commands = []
    token = token or uuid.uuid4().hex
    quote = json.dumps
    for source in visible:
        target = TARGETS[source['output']]
        if source['name'] == target:
            continue
        temporary = f'i3-exchange-{token}-{source["id"]}'
        if temporary in names:
            raise ValueError('Temporary workspace name collision.')
        commands.append(f'rename workspace {quote(source["name"])} to {quote(temporary)}')
        if target in names:
            commands.append(f'rename workspace {quote(target)} to {quote(source["name"])}')
            expected[names[target]['id']] = source['name']
        commands.append(f'rename workspace {quote(temporary)} to {quote(target)}')
        expected[source['id']] = target
    if commands:
        # Renaming keeps the visible workspace containers. Explicitly restore the
        # exact focused container, also when it is an empty workspace or a split.
        commands.append(f'[con_id={focused_id}] focus')
    return commands, expected, focused_id


def ipc(kind):
    return json.loads(subprocess.check_output(['i3-msg', '-t', kind], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    with (runtime / 'i3-pair-exchange.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        before, tree = ipc('get_workspaces'), ipc('get_tree')
        commands, expected, focused_id = plan(before, tree)
        if args.dry_run:
            print('\n'.join(commands) if commands else 'Pair 1 already visible; no change.')
            return
        if not commands:
            return
        snapshot_path = runtime / 'i3-pair-exchange-last.json'
        with tempfile.NamedTemporaryFile(mode='w', dir=runtime, delete=False) as saved:
            json.dump({'before': before, 'commands': commands,
                       'expected': expected, 'focused_id': focused_id}, saved, indent=2)
        os.replace(saved.name, snapshot_path)
        if ipc('get_workspaces') != before:
            raise ValueError('Workspaces changed before exchange; try again.')
        # One IPC request reduces intermediate redraws; it is not a transaction.
        replies = json.loads(subprocess.check_output(['i3-msg', '; '.join(commands)], text=True))
        if len(replies) != len(commands) or not all(r.get('success') for r in replies):
            raise ValueError(f'Partial exchange possible. Inspect {snapshot_path}: {replies}')
        after = {w['id']: w for w in ipc('get_workspaces')}
        after_tree = ipc('get_tree')
        after_ws = {n['id']: n for n in nodes(after_tree) if n.get('type') == 'workspace'}
        before_ws = {n['id']: n for n in nodes(tree) if n.get('type') == 'workspace'}
        for w in before:
            current = after.get(w['id'])
            # Empty inactive workspaces may be cleaned up by i3.
            if current is None and not w['visible'] and signature(before_ws[w['id']]) == ((), ()):
                continue
            if current is None or current['name'] != expected[w['id']] or any(
                    current[k] != w[k] for k in ('output', 'visible', 'focused')):
                raise ValueError(f'Unexpected workspace state. Inspect {snapshot_path}.')
            if signature(before_ws[w['id']]) != signature(after_ws[w['id']]):
                raise ValueError(f'Window/layout state changed. Inspect {snapshot_path}.')
        if not any(n['id'] == focused_id and n.get('focused') for n in nodes(after_tree)):
            raise ValueError(f'Focus changed. Inspect {snapshot_path}.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'workspace exchange: {error}', file=sys.stderr)
        sys.exit(1)
