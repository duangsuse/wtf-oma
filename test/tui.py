"""Black-box TUI test framework: runs menu.py in an 80x24 pty, emulates the
screen with pyte, records asciicast v2.

    uvx --with pyte python test/tui.py [test/01.py ...]   (default: test/[0-9]*.py)

A test file holds only `def _NN(c):` functions; the docstring is the test
name. `c - "keys"` sends input and waits '、' (next change, then stable);
`c - [UP, grep, "Learn", BS, back]` runs a sequence: strings are input steps,
a callable takes as many following items as it has parameters after `c`.
`grep, re` fails when nothing matches and starts a selection that
`only_fg, color` narrows and `chr_count, N` (or "x<k>" vs the first frame) checks.
All tests of a file share one menu.py process, in name order.
"""
import fcntl, glob, importlib.util, inspect, json, os, pty, re, select, signal, struct, sys
import termios, threading, time

import pyte

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "test", "out")
COLS, ROWS = 80, 24
CMD = ["python3", os.path.join(ROOT, "menu.py")]


def fg_name(fg):
    """Basic colour name of a pyte fg: 'brightgreen' -> 'green'; hex -> the
    clearly dominant channel ('red'/'green'/'blue') or the hex itself."""
    if fg.startswith("bright"):
        return fg[6:]
    if len(fg) == 6:
        try:
            rgb = [int(fg[i:i + 2], 16) for i in (0, 2, 4)]
        except ValueError:
            return fg
        m = max(rgb)
        if m >= 96 and sorted(rgb)[1] + 40 < m:
            return ("red", "green", "blue")[rgb.index(m)]
    return fg


class Frame:
    """Immutable copy of the emulated screen."""

    def __init__(self, screen):
        self.cells = [[(screen.buffer[y][x].data, screen.buffer[y][x].fg,
                        screen.buffer[y][x].bg, screen.buffer[y][x].bold,
                        screen.buffer[y][x].reverse)
                       for x in range(COLS)] for y in range(ROWS)]
        self.cursor = (screen.cursor.x, screen.cursor.y)

    @property
    def lines(self):
        return ["".join(c[0] for c in row) for row in self.cells]

    @property
    def text(self):
        return "\n".join(self.lines)

    def _row(self, y):
        """Row text plus, per character, its cell x (wide chars leave "" cells)."""
        chars, xs = [], []
        for x, c in enumerate(self.cells[y]):
            for ch in c[0]:
                chars.append(ch)
                xs.append(x)
        return "".join(chars), xs

    def find(self, s):
        for y in range(ROWS):
            line, xs = self._row(y)
            i = line.find(s)
            if i >= 0:
                return xs[i], y
        return None

    def grep(self, pattern):
        """Cells (x, y) of all regex matches, each match stripped of blank cells
        at both ends (rows without any cell left drop out)."""
        sel = []
        for y in range(ROWS):
            line, xs = self._row(y)
            for m in re.finditer(pattern, line):
                cells = sorted({xs[i] for i in range(m.start(), m.end())})
                while cells and not self.cells[y][cells[0]][0].strip():
                    cells.pop(0)
                while cells and not self.cells[y][cells[-1]][0].strip():
                    cells.pop()
                sel += [(x, y) for x in cells]
        return sel

    def __eq__(self, other):
        return isinstance(other, Frame) and self.cells == other.cells

    def to_json(self):
        return {"cells": self.cells, "cursor": self.cursor}


class Session:
    def __init__(self, cast_path, env=None):
        self.cast_path = cast_path
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)
        self.lock = threading.Lock()
        self.events = []
        self.raw = b""
        self.version = 0          # bumps on every output chunk
        self.last_out = None      # monotonic time of last output
        self.first_out = None
        e = dict(os.environ, TERM="xterm-256color", COLUMNS=str(COLS),
                 LINES=str(ROWS), OMA_GRA="0")
        e.update(env or {})
        self.t0 = time.monotonic()
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe(CMD[0], CMD, e)
        self.pid, self.fd = pid, fd
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        self.alive = True
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        dec_buf = b""
        while True:
            try:
                r, _, _ = select.select([self.fd], [], [], 0.05)
                if not r:
                    if not self.alive:
                        return
                    continue
                data = os.read(self.fd, 65536)
            except OSError:
                data = b""
            if not data:
                self.alive = False
                return
            now = time.monotonic()
            with self.lock:
                self.stream.feed(data)
                self.raw += data
                dec_buf += data
                try:
                    text = dec_buf.decode()
                    dec_buf = b""
                except UnicodeDecodeError:
                    text = None  # incomplete utf-8 sequence; wait for more
                if text:
                    self.events.append([round(now - self.t0, 6), "o", text])
                self.version += 1
                self.last_out = now
                if self.first_out is None:
                    self.first_out = now - self.t0

    def frame(self):
        with self.lock:
            return Frame(self.screen)

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        with self.lock:
            self.events.append([round(time.monotonic() - self.t0, 6), "i",
                                data.decode(errors="replace")])
        os.write(self.fd, data)

    def wait_stable(self, quiet=0.15, timeout=5.0, since=None):
        """'、': wait for the next screen change after `since` (a version),
        then until no output for `quiet` seconds. Returns True if a change
        happened."""
        end = time.monotonic() + timeout
        if since is not None:
            while time.monotonic() < end:
                with self.lock:
                    if self.version != since:
                        break
                time.sleep(0.005)
            else:
                return False
        while time.monotonic() < end:
            with self.lock:
                last = self.last_out
            if last is not None and time.monotonic() - last >= quiet:
                return True
            time.sleep(0.01)
        return True

    def act(self, data, **kw):
        """Send input, then wait for change + stability. Returns new Frame."""
        with self.lock:
            v = self.version
        self.send(data)
        changed = self.wait_stable(since=v, **kw)
        return self.frame(), changed

    # --- mouse -----------------------------------------------------------
    def mouse_mode(self):
        r = self.raw
        sgr = r.rfind(b"\x1b[?1006h") > r.rfind(b"\x1b[?1006l")
        return "sgr" if sgr else "x10"

    def _mouse(self, btn, x, y, release=False):
        # x, y are 0-based screen cells
        if self.mouse_mode() == "sgr":
            return f"\x1b[<{btn};{x + 1};{y + 1}{'m' if release else 'M'}"
        b = 3 if release else btn
        return "\x1b[M" + chr(32 + b) + chr(33 + x) + chr(33 + y)

    def press(self, x, y):
        return self._mouse(0, x, y)

    def drag(self, x, y):
        return self._mouse(32, x, y)

    def release(self, x, y):
        return self._mouse(0, x, y, release=True)

    def close(self):
        if self.alive:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass
        self.alive = False
        self.reader.join(1)
        header = {"version": 2, "width": COLS, "height": ROWS,
                  "timestamp": int(time.time()),
                  "env": {"TERM": "xterm-256color", "SHELL": "/bin/sh"},
                  "title": os.path.basename(self.cast_path)}
        with open(self.cast_path, "w") as f:
            f.write(json.dumps(header) + "\n")
            for ev in self.events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")


# ====================================================================== DSL
UP, DOWN, LEFT, RIGHT = "\x1b[A", "\x1b[B", "\x1b[C", "\x1b[D"
BS, DEL, ESC, ENTER = "\x7f", "\x1b[3~", "\x1b", "\r"
KEY_NAMES = {UP: "↑", DOWN: "↓", LEFT: "←", RIGHT: "→", BS: "退格", DEL: "DEL",
             ESC: "ESC", ENTER: "回车"}


def paste(text):
    """Bracketed paste of `text`."""
    return "\x1b[200~" + text + "\x1b[201~"


class Fail(Exception):
    pass


def _label(keys):
    if keys in KEY_NAMES:
        return KEY_NAMES[keys]
    if keys.startswith("\x1b[200~"):
        return f"粘贴 {keys[6:-6]!r}"
    return repr(keys)


class C:
    """Per-test context. `first`: frame when the test started; `frame`: current;
    `chain`: the last grep and its filters, re-applicable to any frame."""

    def __init__(self, session, frame):
        self.s, self.first, self.frame, self.log = session, frame, frame, []
        self.chain = []

    def check(self, ok, msg):
        self.log.append(("✓ " if ok else "✗ ") + msg)
        if not ok:
            raise Fail(msg)

    def send(self, data, label):
        """Send raw input, then '、'. Fails if nothing changes or menu.py exits."""
        f, changed = self.s.act(data, timeout=2.0)
        self.frame = f
        self.log.append(f"{label}、" if changed else f"✗ {label}: 无变化")
        if not changed:
            raise Fail(f"{label} 后画面无变化")
        time.sleep(0.05)
        if not self.s.alive:
            self.check(False, f"{label} 后 menu.py 退出了")

    def __sub__(self, ops):
        ops = [ops] if isinstance(ops, str) else list(ops)
        while ops:
            op = ops.pop(0)
            if isinstance(op, str):
                self.send(op, _label(op))
            elif callable(op):
                n = len(inspect.signature(op).parameters) - 1
                args, ops = ops[:n], ops[n:]
                op(self, *args)
            else:
                raise TypeError(f"bad op {op!r}")
        return self


def _find(c, frame, text):
    p = frame.find(text)
    if p is None:
        c.check(False, f"找到 {text!r}")
    return p


def opened(c, secs):
    """First paint within `secs` of spawning."""
    t = c.s.first_paint
    c.check(t is not None and t <= secs,
            f"{secs}s 内出首帧 ({'无画面' if t is None else f'{t:.3f}s'})")


def _select(frame, chain):
    sel = []
    for kind, arg in chain:
        if kind == "grep":
            sel = frame.grep(arg)
        elif kind == "fg":
            sel = [(x, y) for x, y in sel if fg_name(frame.cells[y][x][1]) == arg]
    return sel


def grep(c, pattern):
    """Regex on the screen; fails if no match. Starts a new selection (the
    matched cells, each match stripped of blank ends) for only_fg/chr_count."""
    c.chain = [("grep", pattern)]
    sel = _select(c.frame, c.chain)
    c.check(bool(sel), f"grep /{pattern}/ ({len(sel)} 格)")


def only_fg(c, color):
    """Keep only selected cells whose foreground is `color` ('green', 'red', ...)."""
    if not c.chain:
        c.check(False, f"only_fg {color!r} 前没有 grep")
    c.chain.append(("fg", color))
    c.log.append(f"only_fg {color!r} → {len(_select(c.frame, c.chain))} 格")


def chr_count(c, n):
    """Non-blank chars in the selection == n (int), or == k × the same selection
    on the test's first frame (n = "x<k>")."""
    count = lambda f: sum(1 for x, y in _select(f, c.chain) if f.cells[y][x][0].strip())
    got = count(c.frame)
    if isinstance(n, str):
        base, k = count(c.first), float(n.lstrip("x×"))
        c.check(got == k * base, f"字符数 = 初始×{n.lstrip('x×')} ({base} → {got})")
    else:
        c.check(got == n, f"字符数 = {n} ({got})")


def back(c):
    """Whole screen (chars + colours + attributes) equals the test's first frame."""
    a, b = c.first, c.frame
    if a == b:
        return c.check(True, "整屏回到初始")
    n = sum(1 for y in range(ROWS) for x in range(COLS) if a.cells[y][x] != b.cells[y][x])
    kind = "文字相同, 仅颜色/属性不同" if a.text == b.text else "文字不同"
    c.check(False, f"整屏回到初始: {n} 格不同 ({kind})")


def changed(c, text):
    """`text` (as in the first frame) changed glyph or position."""
    p0 = _find(c, c.first, text)
    p1 = c.frame.find(text)
    c.check(p1 != p0, f"{text!r} 变了 ({p0} → {p1 if p1 else '消失'})")


def moved(c, text, dx, dy):
    """`text` is now (dx, dy) cells away from where it was in the first frame."""
    x, y = _find(c, c.first, text)
    p1 = c.frame.find(text)
    c.check(p1 == (x + dx, y + dy), f"{text!r} 位移 ({dx},{dy}) ({(x, y)} → {p1})")


def drag(c, text, dx, dy):
    """Press on `text`, move by (dx, dy), release; then '、'."""
    x, y = _find(c, c.frame, text)
    s = c.s
    c.send(s.press(x, y) + s.drag(x + dx, y + dy) + s.release(x + dx, y + dy),
           f"拖 {text!r} ({dx},{dy})")


def click(c, text, dx, dy):
    """Click (dx, dy) away from `text`; then '、'."""
    x, y = _find(c, c.frame, text)
    x, y = x + dx, y + dy
    c.send(c.s.press(x, y) + c.s.release(x, y), f"点击 {text!r}+({dx},{dy})")


__all__ = ["UP", "DOWN", "LEFT", "RIGHT", "BS", "DEL", "ESC", "ENTER", "paste",
           "opened", "grep", "only_fg", "chr_count", "back", "changed", "moved",
           "drag", "click"]


# =================================================================== runner
def _segment_cast(path, title, first, events, t_from, t_to):
    """Cast that paints `first`, then replays output in (t_from, t_to]."""
    from frames import render
    header = {"version": 2, "width": COLS, "height": ROWS, "title": title,
              "env": {"TERM": "xterm-256color"}}
    with open(path, "w") as f:
        f.write(json.dumps(header) + "\n")
        f.write(json.dumps([0.0, "o", "\x1b[?25l\x1b[2J" + render(first.cells)],
                           ensure_ascii=False) + "\n")
        for t, kind, data in events:
            if kind == "o" and t_from < t <= t_to:
                f.write(json.dumps([round(t - t_from, 6), "o", data],
                                   ensure_ascii=False) + "\n")
        f.write(json.dumps([round(t_to - t_from + 0.5, 6), "o", ""]) + "\n")


def run_file(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(f"t{stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tests = sorted((k, v) for k, v in vars(mod).items()
                   if re.fullmatch(r"_\d\d", k) and callable(v))
    s = Session(os.path.join(OUT, f"{stem}.cast"))
    s.first_paint = None
    end = time.monotonic() + 3
    while time.monotonic() < end:
        if s.frame().text.strip():
            s.first_paint = time.monotonic() - s.t0
            break
        time.sleep(0.002)
    s.wait_stable()
    frame, results = s.frame(), []
    for name, fn in tests:
        tag = stem + name
        title = (fn.__doc__ or name).strip()
        c = C(s, frame)
        t_from = time.monotonic() - s.t0
        err = ""
        try:
            fn(c)
        except Fail as e:
            err = str(e)
        except Exception as e:  # bug in test/framework; keep going
            err = f"{type(e).__name__}: {e}"
            c.log.append(f"✗ {err}")
        s.wait_stable(timeout=1.0)
        frame = s.frame()
        t_to = time.monotonic() - s.t0
        for k, fr in (("first", c.first), ("last", frame)):
            with open(os.path.join(OUT, f"{tag}.{k}.json"), "w") as f:
                json.dump(fr.to_json(), f, ensure_ascii=False)
        results.append({"id": tag, "name": title, "ok": not err, "error": err,
                        "log": c.log, "first": f"{tag}.first.json",
                        "last": f"{tag}.last.json", "cast": f"{tag}.cast",
                        "t": [round(t_from, 3), round(t_to, 3)], "_first": c.first})
        print(f"{'PASS' if not err else 'FAIL'} {tag} {title}" + (f"  -- {err}" if err else ""))
    s.close()
    for r in results:
        _segment_cast(os.path.join(OUT, r["cast"]), r["name"], r.pop("_first"),
                      s.events, *r["t"])
    return results


def main(paths):
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    sys.modules.setdefault("tui", sys.modules[__name__])  # test files: from tui import *
    paths = paths or sorted(glob.glob(os.path.join(here, "[0-9]*.py")))
    os.makedirs(OUT, exist_ok=True)
    for n in os.listdir(OUT):
        os.remove(os.path.join(OUT, n))
    results = [r for p in paths for r in run_file(p)]
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump({"tests": results}, f, ensure_ascii=False, indent=1)
    passed = sum(r["ok"] for r in results)
    print(f"{passed}/{len(results)} passed; output in {os.path.relpath(OUT)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
