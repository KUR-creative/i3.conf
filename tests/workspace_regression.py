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
                key = f'F{n}' if side == 'left' else str(n % 10)
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
        for n, code in enumerate(KEYPAD, 1):
            for side in ('left', 'right'):
                for role, number in [('source', n % 10 + 1), ('existing', n)]:
                    desktop.move(f'{side}-{role}', workspace(side, number))
                desktop.show(workspace(side, n % 10 + 1))
            focus = 'left-source' if n % 2 else 'right-source'
            desktop.park_pointer(focus)
            expected = {t: workspace(t.split('-')[0], n) for t in desktop.ids}
            visible = {workspace(s, n) for s in ('left', 'right')}
            desktop.keys.press(code, shift=True, numlock=numlock)
            desktop.check(expected, focus, visible)
            desktop.keys.press(code, shift=True, numlock=numlock)
            desktop.check(expected, focus, visible)
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG, help='workspace config to test; never modified')
    parser.add_argument('--xvfb', default=shutil.which('Xvfb'), help='Xvfb executable (default: PATH)')
    parser.add_argument('--group', choices=['all', 'switch', 'single', 'pair'], default='all')
    parser.add_argument('--timeout', type=float, default=4, help='seconds to wait for each expected state')
    args = parser.parse_args()
    if not args.xvfb:
        parser.error('Xvfb is required; install it or pass --xvfb /path/to/Xvfb')
    for tool in ('i3', 'i3-msg', 'xmessage'):
        if not shutil.which(tool):
            parser.error(f'Missing executable: {tool}')
    groups = {'switch': switching, 'single': single_moves, 'pair': pair_moves}
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
