#!/usr/bin/env python3
"""Exercise workspace bindings on an isolated Xvfb/i3 session with real key events."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time


CONFIG = Path(__file__).resolve().parents[1] / 'config.d/workspaces.conf'
KEYPAD = [87, 88, 89, 83, 84, 85, 79, 80, 81, 90]
MARK = '_i3_move_follow'
PAIR_SCRIPT = CONFIG.parents[1] / 'scripts/workspace-pair.py'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def walk(node):
    yield node
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from walk(child)


def workspace(side, number):
    return f'{number + 10}:F{number}' if side == 'left' else f'{number}:{number % 10}'


def opposite(side):
    return 'left' if side == 'right' else 'right'


class Desktop:
    def __init__(self, source, xvfb, timeout):
        self.source, self.xvfb, self.timeout = source, xvfb, timeout
        self.processes, self.logs = [], []
        self.display = None

    def launch(self, args, **kwargs):
        log = tempfile.TemporaryFile()
        self.logs.append(log)
        process = subprocess.Popen(args, env=self.env, stdout=log, stderr=log, **kwargs)
        self.processes.append(process)
        return process

    def wait(self, predicate, label):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.03)
        raise AssertionError(f'Timed out: {label}')

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='i3-workspace-regression-')
        self.root = Path(self.temp.name)
        runtime = self.root / 'runtime'
        runtime.mkdir(mode=0o700)
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime))
        # Never inherit a real desktop's IPC socket or X authentication settings.
        for key in ('DISPLAY', 'I3SOCK', 'I3_SOCKET_PATH', 'XAUTHORITY'):
            self.env.pop(key, None)
        try:
            read_fd, write_fd = os.pipe()
            try:
                self.launch([self.xvfb, '-displayfd', str(write_fd), '-screen', '0',
                             '1600x600x24', '-nolisten', 'tcp', '-ac'], pass_fds=(write_fd,))
                os.close(write_fd)
                write_fd = None
                ready, _, _ = select.select([read_fd], [], [], self.timeout)
                require(ready, 'Xvfb did not allocate a display')
                number = os.read(read_fd, 32).decode().strip()
                require(number.isdigit(), f'Invalid Xvfb display: {number!r}')
            finally:
                os.close(read_fd)
                if write_fd is not None:
                    os.close(write_fd)
            self.env['DISPLAY'] = ':' + number
            source = self.source.read_text().replace('DP-1', 'fake-0').replace('HDMI-0', 'fake-1')
            source = source.replace('~/.config/i3/scripts/workspace-pair.py', str(PAIR_SCRIPT))
            config = self.root / 'config'
            config.write_text('font pango:monospace 8\nset $mod Mod4\n'
                              'fake-outputs 800x600+0+0,800x600+800+0\n'
                              'focus_follows_mouse yes\nworkspace_auto_back_and_forth yes\n' + source)
            subprocess.run(['i3', '-C', '-c', str(config)], env=self.env,
                           check=True, capture_output=True, text=True, timeout=10)
            self.launch(['i3', '-a', '-c', str(config)])

            def ready():
                result = subprocess.run(['i3', '--get-socketpath'], env=self.env,
                                        capture_output=True, text=True, timeout=3)
                socket = result.stdout.strip()
                if result.returncode or not socket:
                    return False
                # Pin every subsequent command and exec child to the test server.
                require(str(runtime) in socket, f'IPC socket is outside test runtime: {socket}')
                self.env['I3SOCK'] = socket
                return len([o for o in self.ipc('get_outputs') if o['active']]) == 2

            self.wait(ready, 'isolated i3 outputs')
            self.keys = Keyboard(self.env['DISPLAY'])
            self.ids = {}
            for side in ('left', 'right'):
                self.show(workspace(side, 1))
                for role in ('source', 'existing'):
                    title = f'{side}-{role}'
                    self.launch(['xmessage', '-name', title, '-title', title, '-buttons', 'OK:0', title])
                    self.wait(lambda: title in self.locations(), 'test window ' + title)
                    self.ids[title] = self.locations()[title][1]['id']
                    self.command(f'[con_id={self.ids[title]}] floating disable')
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def ipc(self, kind):
        return json.loads(subprocess.check_output(['i3-msg', '-r', '-t', kind], env=self.env,
                                                 text=True, stderr=subprocess.DEVNULL, timeout=5))

    @property
    def history_path(self):
        return Path(self.env['XDG_RUNTIME_DIR']) / 'i3-workspace-pair'

    def history(self):
        return self.history_path.read_text() if self.history_path.exists() else ''

    def previous(self):
        raw = self.history().strip()
        try:
            return json.loads(raw)['previous'] if raw else None
        except json.JSONDecodeError:
            return raw

    def command(self, command):
        replies = json.loads(subprocess.check_output(['i3-msg', command], env=self.env,
                                                    text=True, timeout=5))
        require(all(r.get('success') for r in replies), f'IPC failed: {replies}')

    def show(self, name):
        self.command('workspace --no-auto-back-and-forth number ' + json.dumps(name))

    def move(self, title, name):
        self.command(f'[con_id={self.ids[title]}] move --no-auto-back-and-forth '
                     'container to workspace number ' + json.dumps(name))

    def focus(self, title):
        self.command(f'[con_id={self.ids[title]}] focus')

    def locations(self):
        result = {}
        for ws in (n for n in walk(self.ipc('get_tree')) if n['type'] == 'workspace'):
            for node in walk(ws):
                if node.get('window'):
                    result[node.get('name')] = (ws['name'], node)
        return result

    def visible(self):
        return {w['name'] for w in self.ipc('get_workspaces') if w['visible']}

    def check(self, expected, focused, visible):
        def correct():
            current = self.locations()
            return (all(current[t][0] == ws for t, ws in expected.items())
                    and current[focused][1].get('focused')
                    and self.visible() == visible
                    and not any(MARK in n.get('marks', []) for n in walk(self.ipc('get_tree'))))
        self.wait(correct, f'locations/focus/mark: {expected}, focus={focused}')
        time.sleep(.1)
        require(correct(), 'Focus or window location changed after settling')

    def park_pointer(self, title):
        self.keys.pointer(self.locations()[title][1]['rect'])
        time.sleep(.03)
        self.focus(title)

    def __exit__(self, kind, value, traceback):
        if kind:
            print(f'FAIL: {value}', file=sys.stderr)
            if hasattr(self, 'ids'):
                try:
                    actual = {title: {'workspace': ws, 'focused': node.get('focused'),
                                      'marks': node.get('marks', [])}
                              for title, (ws, node) in self.locations().items()}
                    print('Actual state: ' + json.dumps(actual), file=sys.stderr)
                    print('Visible: ' + json.dumps(sorted(self.visible())), file=sys.stderr)
                except (OSError, subprocess.SubprocessError):
                    pass
            for process, log in zip(self.processes, self.logs):
                if process.poll() not in (None, 0):
                    log.seek(0)
                    print(log.read().decode(errors='replace')[-1200:], file=sys.stderr)
        if hasattr(self, 'keys'):
            self.keys.close()
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(self.processes):
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in self.logs:
            log.close()
        self.temp.cleanup()


class Keyboard:
    def __init__(self, display):
        self.x = ctypes.CDLL('libX11.so.6')
        self.xt = ctypes.CDLL('libXtst.so.6')
        self.x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.x.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x.XStringToKeysym.restype = ctypes.c_ulong
        self.x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x.XKeysymToKeycode.restype = ctypes.c_uint
        self.x.XkbLockModifiers.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
        self.x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.xt.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.xt.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self.display = self.x.XOpenDisplay(display.encode())
        require(self.display, 'Could not open isolated X display')

    def code(self, symbol):
        code = self.x.XKeysymToKeycode(self.display, self.x.XStringToKeysym(symbol.encode()))
        require(code, f'Unknown keysym: {symbol}')
        return code

    def press(self, key, shift=False, numlock=False):
        self.x.XkbLockModifiers(self.display, 0x100, 16, 16 if numlock else 0)
        codes = [self.code('Super_L')]
        if shift:
            codes.append(self.code('Shift_L'))
        codes.append(key if isinstance(key, int) else self.code(key))
        for code in codes:
            require(self.xt.XTestFakeKeyEvent(self.display, code, 1, 0), 'Key press failed')
        for code in reversed(codes):
            require(self.xt.XTestFakeKeyEvent(self.display, code, 0, 0), 'Key release failed')
        self.x.XSync(self.display, False)

    def pointer(self, rect):
        self.xt.XTestFakeMotionEvent(self.display, 0, rect['x'] + rect['width'] // 2,
                                    rect['y'] + rect['height'] // 2, 0)
        self.x.XSync(self.display, False)

    def close(self):
        self.x.XCloseDisplay(self.display)


def switching(desktop):
    count = 0
    for numlock in (False, True):
        for side in ('right', 'left'):
            for n in range(1, 11):
                views = {s: workspace(s, n % 10 + 1) for s in ('left', 'right')}
                for ws in views.values():
                    desktop.show(ws)
                before = {t: v[0] for t, v in desktop.locations().items()}
                key = f'F{n}' if side == 'left' else str(n % 10)
                desktop.keys.press(key, numlock=numlock)
                # Main number keys switch pairs; function keys switch only the left workspace.
                if side == 'right':
                    views = {s: workspace(s, n) for s in ('left', 'right')}
                else:
                    views[side] = workspace(side, n)
                desktop.wait(lambda: desktop.visible() == set(views.values()), key + ' switch')
                time.sleep(.1)
                require(next(w for w in desktop.ipc('get_workspaces') if w['focused'])['name']
                        == workspace(side, n), 'Wrong focused workspace')
                require({t: v[0] for t, v in desktop.locations().items()} == before, 'Switch moved windows')
                count += 1
        for n, code in enumerate(KEYPAD, 1):
            before = {t: v[0] for t, v in desktop.locations().items()}
            # All keypad keys switch only the right workspace.
            left = next(w['name'] for w in desktop.ipc('get_workspaces')
                        if w['visible'] and w['output'] == 'fake-0')
            target = {left, workspace('right', n)}
            desktop.keys.press(code, numlock=numlock)
            desktop.wait(lambda: desktop.visible() == target, 'keypad switch')
            require(next(w for w in desktop.ipc('get_workspaces') if w['focused'])['name']
                    == workspace('right', n), 'Keypad switch must focus right')
            require({t: v[0] for t, v in desktop.locations().items()} == before, 'Keypad switch moved windows')
            count += 1
        for side in ('left', 'right'):
            desktop.show(workspace(side, 2))
        before = {t: v[0] for t, v in desktop.locations().items()}
        for _ in range(2):
            desktop.keys.press('grave', numlock=numlock)
            desktop.wait(lambda: desktop.visible() == {workspace('left', 10), workspace('right', 10)},
                         'grave alias for pair 10')
            time.sleep(.1)
            require(next(w for w in desktop.ipc('get_workspaces') if w['focused'])['name']
                    == workspace('right', 10), 'Grave must focus right')
        require({t: v[0] for t, v in desktop.locations().items()} == before, 'Grave moved windows')
        count += 1
    return count


def single_moves(desktop):
    count = 0
    moving = 'left-source'
    for numlock in (False, True):
        for side in ('right', 'left'):
            for n in range(1, 11):
                source_side = opposite(side) if n % 2 else side
                source = workspace(source_side, n % 10 + 1)
                destination = workspace(side, n)
                views = {s: workspace(s, n) for s in ('left', 'right')}
                views[source_side] = source
                desktop.command(f'[con_id={desktop.ids[moving]}] fullscreen disable')
                desktop.command(f'[con_id={desktop.ids[moving]}] floating disable')
                for title, ws in [(moving, source), ('right-source', source),
                                  (side + '-existing', destination),
                                  (opposite(side) + '-existing', views[opposite(side)])]:
                    desktop.move(title, ws)
                for ws in views.values():
                    desktop.show(ws)
                desktop.focus(moving)
                desktop.command('mark --add user-existing')
                if n == 3:
                    desktop.command('floating enable')
                if n == 4:
                    desktop.command('fullscreen enable')
                desktop.park_pointer(moving)
                expected = {t: v[0] for t, v in desktop.locations().items()}
                expected[moving] = destination
                views[side] = destination
                key = f'F{n}' if side == 'left' else KEYPAD[n - 1]
                desktop.keys.press(key, shift=True, numlock=numlock)
                desktop.check(expected, moving, set(views.values()))
                require('user-existing' in desktop.locations()[moving][1]['marks'], 'User mark lost')
                desktop.keys.press(key, shift=True, numlock=numlock)
                desktop.check(expected, moving, set(views.values()))
                count += 1
    return count


def pair_moves(desktop):
    count = 0
    for numlock in (False, True):
        for n, key in [(n, str(n % 10)) for n in range(1, 11)] + [(10, 'grave')]:
            for side in ('left', 'right'):
                for role, number in [('source', n % 10 + 1), ('existing', n)]:
                    desktop.move(f'{side}-{role}', workspace(side, number))
                desktop.show(workspace(side, n % 10 + 1))
            focus = 'left-source' if n % 2 else 'right-source'
            desktop.park_pointer(focus)
            expected = {t: workspace(t.split('-')[0], n) for t in desktop.ids}
            visible = {workspace(s, n) for s in ('left', 'right')}
            recorded = desktop.history()
            desktop.keys.press(key, shift=True, numlock=numlock)
            desktop.check(expected, focus, visible)
            desktop.keys.press(key, shift=True, numlock=numlock)
            desktop.check(expected, focus, visible)
            require(desktop.history() == recorded, 'Shift pair move changed previous location')
            count += 1
    return count



def previous_pairs(desktop):
    count = 0
    # Missing, empty, and invalid records must never execute a workspace command.
    for record in (None, '', 'F11\n', '1\nF2\n', '3; kill\n',
                   '{', '[]', '{"previous": "F1", "focus": ["F1"]}',
                   json.dumps({'previous': [], 'focus': list(range(10))})):
        if record is None:
            desktop.history_path.unlink(missing_ok=True)
        else:
            desktop.history_path.write_text(record)
        before = desktop.visible()
        focus = next(ws['name'] for ws in desktop.ipc('get_workspaces') if ws['focused'])
        desktop.keys.press('Tab')
        time.sleep(.2)
        require(desktop.visible() == before, 'Invalid history changed visible workspaces')
        require(next(ws['name'] for ws in desktop.ipc('get_workspaces') if ws['focused'])
                == focus, 'Invalid history changed focus')
        require((desktop.history_path.read_text() if desktop.history_path.exists() else None)
                == record, 'Invalid history was overwritten')
    for numlock in (False, True):
        for side in ('left', 'right'):
            for n in range(1, 11):
                desktop.history_path.unlink(missing_ok=True)
                destination = n % 10 + 1
                for s in ('left', 'right'):
                    desktop.move(f'{s}-source', workspace(s, n))
                    desktop.move(f'{s}-existing', workspace(s, destination))
                    desktop.show(workspace(s, n))
                focus = side + '-source'
                desktop.park_pointer(focus)
                expected = {t: v[0] for t, v in desktop.locations().items()}
                label = f'F{n}' if side == 'left' else str(n % 10)
                desktop.keys.press(str(destination % 10), numlock=numlock)
                desktop.check(expected, 'right-existing',
                              {workspace(s, destination) for s in ('left', 'right')})
                desktop.wait(lambda: desktop.previous() == label, 'history before return')
                desktop.park_pointer('right-existing')
                desktop.keys.press('Tab', numlock=numlock)
                desktop.check(expected, focus, {workspace(s, n) for s in ('left', 'right')})
                desktop.wait(lambda: desktop.previous() == str(destination % 10),
                             'history swapped on return')
                desktop.park_pointer(focus)
                desktop.keys.press('Tab', numlock=numlock)
                desktop.check(expected, 'right-existing',
                              {workspace(s, destination) for s in ('left', 'right')})
                desktop.wait(lambda: desktop.previous() == label, 'history after round trip')
                count += 1
    for numlock in (False, True):
        for side in ('left', 'right'):
            desktop.history_path.unlink(missing_ok=True)
            # Mixed source views restore the regular pair of the focused workspace.
            for title, ws in [('left-source', workspace('left', 2)),
                              ('right-source', workspace('right', 5)),
                              ('left-existing', workspace('left', 3)),
                              ('right-existing', workspace('right', 3))]:
                desktop.move(title, ws)
            desktop.show(workspace('left', 2))
            desktop.show(workspace('right', 5))
            focus = side + '-source'
            desktop.park_pointer(focus)
            expected = {t: v[0] for t, v in desktop.locations().items()}
            desktop.keys.press('3', numlock=numlock)
            desktop.check(expected, 'right-existing', {workspace(s, 3) for s in ('left', 'right')})
            desktop.keys.press('Tab', numlock=numlock)
            number = 2 if side == 'left' else 5
            desktop.check(expected, focus, {workspace(s, number) for s in ('left', 'right')})
            count += 1
            desktop.history_path.unlink(missing_ok=True)
            # Multiple windows in the departure workspace: restore the last one exactly.
            other = opposite(side)
            for title in (side + '-source', side + '-existing'):
                desktop.move(title, workspace(side, 10))
            desktop.move(other + '-source', workspace(other, 10))
            desktop.move(other + '-existing', workspace('right', 3))
            for ws in (workspace('left', 10), workspace('right', 10)):
                desktop.show(ws)
            desktop.park_pointer(focus)
            expected = {t: v[0] for t, v in desktop.locations().items()}
            desktop.keys.press('3', numlock=numlock)
            desktop.check(expected, other + '-existing', {workspace(s, 3) for s in ('left', 'right')})
            desktop.keys.press('Tab', numlock=numlock)
            desktop.check(expected, focus, {workspace(s, 10) for s in ('left', 'right')})
            count += 1
        desktop.history_path.unlink(missing_ok=True)
        # Empty departed workspaces are recreated and focused without inventing a window.
        for ws in (workspace('left', 8), workspace('right', 8)):
            desktop.show(ws)
        desktop.command('focus output fake-0')
        desktop.keys.press('3', numlock=numlock)
        desktop.wait(lambda: desktop.previous() == 'F8', 'empty departure')
        desktop.keys.press('Tab', numlock=numlock)
        desktop.wait(lambda: desktop.visible() == {workspace(s, 8) for s in ('left', 'right')}
                     and any(ws['name'] == workspace('left', 8) and ws['focused']
                             for ws in desktop.ipc('get_workspaces')), 'empty workspace restored')
        desktop.wait(lambda: desktop.previous() == '3', 'empty return saved departure')
        # Six simultaneous invocations must serialize into three complete round trips.
        processes = [subprocess.Popen([sys.executable, str(PAIR_SCRIPT), 'previous'], env=desktop.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(6)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            require(process.returncode == 0, f'Concurrent previous failed: {stderr!r}')
        require(desktop.visible() == {workspace(s, 8) for s in ('left', 'right')}
                and desktop.previous() == '3', 'Concurrent previous lost a round trip')
        count += 1
    return count


def remembered_pairs(desktop):
    count = 0
    for numlock in (False, True):
        for side in ('left', 'right'):
            for n in range(1, 11):
                desktop.history_path.unlink(missing_ok=True)
                destination = n % 10 + 1
                other = opposite(side)
                for title in (side + '-source', side + '-existing'):
                    desktop.move(title, workspace(side, n))
                desktop.move(other + '-source', workspace(other, n))
                desktop.move(other + '-existing', workspace('right', destination))
                for ws in (workspace('left', n), workspace('right', n)):
                    desktop.show(ws)
                focus = side + '-source'
                desktop.park_pointer(focus)
                expected = {t: v[0] for t, v in desktop.locations().items()}
                desktop.keys.press(str(destination % 10), numlock=numlock)
                desktop.check(expected, other + '-existing',
                              {workspace(s, destination) for s in ('left', 'right')})
                desktop.keys.press(str(n % 10), numlock=numlock)
                desktop.check(expected, focus, {workspace(s, n) for s in ('left', 'right')})
                label = f'F{n}' if side == 'left' else str(n % 10)
                saved = json.loads(desktop.history())
                require(saved['focus'][n - 1] == label, 'Wrong remembered side')
                require(saved['previous'] == str(destination % 10), 'Previous pair not saved')
                # Re-selecting this pair records current focus without changing previous.
                desktop.park_pointer(other + '-source')
                desktop.keys.press(str(n % 10), numlock=numlock)
                desktop.check(expected, other + '-source',
                              {workspace(s, n) for s in ('left', 'right')})
                saved = json.loads(desktop.history())
                other_label = f'F{n}' if other == 'left' else str(n % 10)
                require(saved['focus'][n - 1] == other_label, 'Same-pair focus not updated')
                require(saved['previous'] == str(destination % 10), 'Same-pair previous overwritten')
                # Tab and main numbers share the same per-pair memory.
                desktop.keys.press('Tab', numlock=numlock)
                desktop.check(expected, other + '-existing',
                              {workspace(s, destination) for s in ('left', 'right')})
                desktop.keys.press(str(n % 10), numlock=numlock)
                desktop.check(expected, other + '-source',
                              {workspace(s, n) for s in ('left', 'right')})
                count += 1
    # A live legacy record is migrated on successful restore, then main/grave reuse its side.
    for label, focus in [('F10', 'left-source'), ('0', 'right-source')]:
        for title, ws in [('left-source', workspace('left', 10)),
                          ('left-existing', workspace('left', 10)),
                          ('right-source', workspace('right', 10)),
                          ('right-existing', workspace('right', 3))]:
            desktop.move(title, ws)
        for ws in (workspace('left', 10), workspace('right', 10)):
            desktop.show(ws)
        desktop.focus(focus)
        desktop.show(workspace('left', 3))
        desktop.show(workspace('right', 3))
        desktop.park_pointer('right-existing')
        expected = {t: v[0] for t, v in desktop.locations().items()}
        desktop.history_path.write_text(label + '\n')
        desktop.keys.press('Tab')
        desktop.check(expected, focus, {workspace(s, 10) for s in ('left', 'right')})
        saved = json.loads(desktop.history())
        require(saved['previous'] == '3' and saved['focus'][9] == label, 'Legacy migration lost focus')
        desktop.keys.press('3')
        desktop.check(expected, 'right-existing', {workspace(s, 3) for s in ('left', 'right')})
        desktop.keys.press('grave')
        desktop.check(expected, focus, {workspace(s, 10) for s in ('left', 'right')})
        count += 1
    return count


def history_recording(desktop):
    count = 0
    for numlock in (False, True):
        for side in ('left', 'right'):
            for n in range(1, 11):
                desktop.history_path.unlink(missing_ok=True)
                destination = n % 10 + 1
                for s in ('left', 'right'):
                    desktop.move(f'{s}-source', workspace(s, n))
                    desktop.move(f'{s}-existing', workspace(s, destination))
                    desktop.show(workspace(s, n))
                focus = side + '-source'
                desktop.park_pointer(focus)
                expected = {t: v[0] for t, v in desktop.locations().items()}
                label = f'F{n}' if side == 'left' else str(n % 10)
                desktop.keys.press(str(destination % 10), numlock=numlock)
                desktop.check(expected, 'right-existing',
                              {workspace(s, destination) for s in ('left', 'right')})
                desktop.wait(lambda: desktop.previous() == label, 'departure label ' + label)
                require(desktop.history_path.stat().st_mode & 0o777 == 0o600, 'History permissions')
                desktop.keys.press(str(destination % 10), numlock=numlock)
                desktop.check(expected, 'right-existing',
                              {workspace(s, destination) for s in ('left', 'right')})
                require(desktop.previous() == label, 'Same pair overwrote previous location')
                count += 1
    # Individual workspace and mouse focus changes must not update pair history.
    recorded = desktop.history()
    desktop.keys.press('F2')
    desktop.wait(lambda: workspace('left', 2) in desktop.visible(), 'independent left switch')
    desktop.keys.press(KEYPAD[4])
    desktop.wait(lambda: workspace('right', 5) in desktop.visible(), 'independent right switch')
    require(desktop.history() == recorded, 'Independent switching changed pair history')
    # Reload preserves history; explicit new-session reset clears it.
    desktop.command('reload')
    time.sleep(.15)
    require(desktop.history() == recorded, 'Reload cleared history')
    subprocess.run([sys.executable, str(PAIR_SCRIPT), 'reset'], env=desktop.env,
                   check=True, timeout=5)
    require(desktop.history() == '', 'New-session reset did not clear history')
    # An unmanaged workspace must not produce a false pair record or switch.
    desktop.command('rename workspace to 99:unmanaged')
    before = desktop.visible()
    result = subprocess.run([sys.executable, str(PAIR_SCRIPT), '3'], env=desktop.env,
                            capture_output=True, text=True, timeout=5)
    require(result.returncode != 0, 'Unmanaged workspace accepted')
    require(desktop.visible() == before and desktop.history() == '', 'Failed switch changed state')
    return count


def layout_preserving_moves(desktop):
    def workspace_node(name):
        return next(node for node in walk(desktop.ipc('get_tree'))
                    if node['type'] == 'workspace' and node['name'] == name)

    def windows(node):
        return {child['window'] for child in walk(node) if child.get('window')}

    def shape(node):
        if node.get('window'):
            return ('window', node['window'])
        children = node.get('nodes', [])
        # An outer group with one child does not change the source arrangement.
        if len(children) == 1:
            return shape(children[0])
        return (node['layout'], tuple((round(child.get('percent') or 0, 6), shape(child))
                                      for child in children))

    extras = []
    try:
        for side in ('left', 'right'):
            for suffix in ('a', 'b'):
                title = f'{side}-layout-{suffix}'
                desktop.launch(['xmessage', '-name', title, '-title', title, '-buttons', 'OK:0', title])
                desktop.wait(lambda: title in desktop.locations(), 'layout fixture ' + title)
                desktop.ids[title] = desktop.locations()[title][1]['id']
                extras.append(title)
        count = 0
        for occupied in (False, True):
            for index, layout in enumerate(('splith', 'tabbed', 'stacking')):
                for title, node_id in desktop.ids.items():
                    desktop.command(f'[con_id={node_id}] fullscreen disable; '
                                    f'[con_id={node_id}] floating disable')
                    desktop.move(title, workspace(title.split('-')[0], 9))
                for side in ('left', 'right'):
                    desktop.show(workspace(side, 9))
                sources = {'left': workspace('left', 5), 'right': workspace('right', 6)}
                for side in ('left', 'right'):
                    desktop.show(sources[side])
                    for title in (side + '-source', side + '-existing',
                                  side + '-layout-a', side + '-layout-b'):
                        desktop.move(title, sources[side])
                    if occupied:
                        desktop.move(side + '-existing', workspace(side, 3))
                    desktop.focus(side + '-source')
                    desktop.command('split v; focus parent; mark --add _layout_build')
                    desktop.command(f'[con_id={desktop.ids[side + "-layout-a"]}] '
                                    'move container to mark _layout_build; unmark _layout_build')
                    desktop.focus(side + '-source')
                    desktop.command('resize grow height 0 px or 17 ppt; focus parent; '
                                    'resize grow width 0 px or 13 ppt')
                    root = workspace_node(sources[side])
                    desktop.command(f'[con_id={root["id"]}] layout {layout}')
                    desktop.focus(side + '-source')
                    desktop.command('mark --add layout-user-' + side)
                focus_side = 'left' if (index + occupied) % 2 == 0 else 'right'
                focused = focus_side + '-source'
                if layout == 'stacking':
                    desktop.focus('right-layout-b')
                    desktop.command('floating enable')
                    desktop.focus('left-layout-b')
                    desktop.command('fullscreen enable')
                    focused = focus_side + '-layout-b'
                desktop.park_pointer(focused)
                before = {side: workspace_node(name) for side, name in sources.items()}
                states = {title: (node['floating'], node['fullscreen_mode'], sorted(node['marks']))
                          for title, (_, node) in desktop.locations().items()}
                expected = {title: workspace(title.split('-')[0], 3) for title in desktop.ids}
                recorded = desktop.history()
                desktop.keys.press('3', shift=True, numlock=bool(index % 2))
                desktop.check(expected, focused, {workspace(s, 3) for s in ('left', 'right')})
                require(desktop.history() == recorded, 'Layout move changed JSON history')
                for side in ('left', 'right'):
                    source_ids = set().union(*(windows(child) for child in before[side]['nodes']))
                    candidates = [node for node in walk(workspace_node(workspace(side, 3)))
                                  if windows(node) == source_ids]
                    require(any(shape(node) == shape(before[side]) for node in candidates),
                            f'{side} source layout/ratios lost: occupied={occupied}, layout={layout}')
                require({title: (node['floating'], node['fullscreen_mode'], sorted(node['marks']))
                         for title, (_, node) in desktop.locations().items()} == states,
                        'Floating/fullscreen/user marks changed')
                after = {side: shape(workspace_node(workspace(side, 3))) for side in ('left', 'right')}
                desktop.keys.press('3', shift=True, numlock=bool(index % 2))
                desktop.check(expected, focused, {workspace(s, 3) for s in ('left', 'right')})
                require({side: shape(workspace_node(workspace(side, 3)))
                         for side in ('left', 'right')} == after, 'Same target changed layout again')
                count += 1
        # No tiling tree: one floating window or both source workspaces empty.
        for only_float in (True, False):
            for title, node_id in desktop.ids.items():
                desktop.command(f'[con_id={node_id}] fullscreen disable; '
                                f'[con_id={node_id}] floating disable')
                desktop.move(title, workspace(title.split('-')[0], 9))
            for side in ('left', 'right'):
                desktop.show(workspace(side, 9))
                desktop.show(workspace(side, 5))
            if only_float:
                desktop.move('right-source', workspace('right', 5))
                desktop.focus('right-source')
                desktop.command('floating enable')
            else:
                desktop.command('focus output fake-0')
            expected = {title: name for title, (name, _) in desktop.locations().items()}
            if only_float:
                expected['right-source'] = workspace('right', 10)
            recorded = desktop.history()
            desktop.keys.press('grave', shift=True)
            if only_float:
                desktop.check(expected, 'right-source',
                              {workspace(s, 10) for s in ('left', 'right')})
            else:
                desktop.wait(lambda: desktop.visible() == {workspace(s, 10) for s in ('left', 'right')},
                             'empty pair move')
                time.sleep(.1)
                require(next(ws['name'] for ws in desktop.ipc('get_workspaces') if ws['focused'])
                        == workspace('right', 10), 'Empty pair must finish on the right')
                require({title: name for title, (name, _) in desktop.locations().items()} == expected,
                        'Empty move changed hidden windows')
            require(desktop.history() == recorded, 'Empty/floating move changed history')
            count += 1
        return count
    finally:
        for title in extras:
            desktop.command(f'[con_id={desktop.ids.pop(title)}] kill')
        desktop.wait(lambda: all(title not in desktop.locations() for title in extras), 'layout fixtures closed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG, help='workspace config to test; never modified')
    parser.add_argument('--xvfb', default=shutil.which('Xvfb'), help='Xvfb executable (default: PATH)')
    parser.add_argument('--group', choices=['all', 'switch', 'single', 'pair', 'history', 'back', 'remember', 'layout'], default='all')
    parser.add_argument('--timeout', type=float, default=4, help='seconds to wait for each expected state')
    args = parser.parse_args()
    if not args.xvfb:
        parser.error('Xvfb is required; install it or pass --xvfb /path/to/Xvfb')
    for tool in ('i3', 'i3-msg', 'xmessage'):
        if not shutil.which(tool):
            parser.error(f'Missing executable: {tool}')
    groups = {'switch': switching, 'single': single_moves, 'pair': pair_moves,
              'back': previous_pairs, 'remember': remembered_pairs, 'layout': layout_preserving_moves, 'history': history_recording}
    selected = groups if args.group == 'all' else {args.group: groups[args.group]}
    with Desktop(args.config.resolve(), args.xvfb, args.timeout) as desktop:
        for name, test in selected.items():
            count = test(desktop)
            print(f'PASS {name}: {count} key combinations (including both Num Lock states)', flush=True)
    print('All selected regression checks passed. Physical desktop validation remains separate.')


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, OSError, subprocess.SubprocessError) as error:
        print(f'workspace regression: {error}', file=sys.stderr)
        sys.exit(1)
