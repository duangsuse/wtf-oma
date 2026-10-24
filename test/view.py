"""Viewer for test/out (stdlib only; needs a terminal >= 80x27).

    python3 test/view.py          (or: sh test/view.sh)

  ←      pull out the test menu (↑↓/digits select with live preview; →/Enter/←/Esc close)
  →      play this test point's cast at 0.3x, return automatically
  ↑/↓    switch view: first frame / last frame / diff
         (diff: green bg = changed/new cell of last frame, red bg = cell blanked)
  0-9    jump to test _0N
  Enter  re-run the test suite
  Q      quit
"""
import os, shutil, subprocess, sys, termios, tty

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from frames import diff, load, render  # noqa: E402

OUT = os.path.join(HERE, "out")
RUN = ["uvx", "--with", "pyte", "python", os.path.join(HERE, "tui.py")]
MODES = ["首帧", "尾帧", "diff"]
KEYS = {"\x1b[A": "up", "\x1bOA": "up", "\x1b[B": "down", "\x1bOB": "down",
        "\x1b[C": "right", "\x1bOC": "right", "\x1b[D": "left", "\x1bOD": "left",
        "\r": "enter", "\n": "enter", "\x1b": "esc", "q": "quit", "Q": "quit",
        "\x03": "quit"}
MENU_W = 46
MENU_TOP, MENU_ROWS = 14, 10      # 菜单画在下半屏(第 14 行起: 标题 + 10 个可见项 + 错误行), 上半屏的预览不被盖住

GREEN, RED, DIM, REV, RST = "\x1b[32m", "\x1b[31m", "\x1b[2m", "\x1b[7m", "\x1b[0m"


def w(s):
    sys.stdout.write(s)


def cut(s, n):
    """Truncate to n terminal columns (CJK = 2)."""
    out, used = "", 0
    for ch in s:
        cw = 2 if ord(ch) >= 0x1100 and not 0x2500 <= ord(ch) <= 0x25ff else 1
        if used + cw > n:
            break
        out, used = out + ch, used + cw
    return out + " " * (n - used)


class Viewer:
    def __init__(self):
        self.i, self.mode, self.menu = 0, 2, False
        self.load()

    def load(self):
        path = os.path.join(OUT, "results.json")
        self.tests = load(path)["tests"] if os.path.exists(path) else []
        self.i = min(self.i, max(len(self.tests) - 1, 0))

    # ------------------------------------------------------------ drawing
    def draw(self):
        w("\x1b[0m\x1b[2J\x1b[H")
        if not self.tests:
            w("没有结果: 按 Enter 运行测试, Q 退出")
        else:
            self.draw_frame()
            if self.menu:
                self.draw_menu()
        sys.stdout.flush()

    def draw_frame(self):
        t = self.tests[self.i]
        first = load(os.path.join(OUT, t["first"]))["cells"]
        last = load(os.path.join(OUT, t["last"]))["cells"]
        marks, view = None, MODES[self.mode]
        if self.mode == 0:
            cells = first
        elif self.mode == 1:
            cells = last
        else:
            cells, marks = [row[:] for row in last], {}
            for x, y in diff(first, last):
                if not last[y][x][0].strip() and first[y][x][0].strip():
                    cells[y][x], marks[x, y] = first[y][x], "red"
                else:
                    marks[x, y] = "green"
            view += f" ({len(marks)} 格不同)"
        mark = f"{GREEN}PASS{RST}" if t["ok"] else f"{RED}FAIL{RST}"
        w(f"\x1b[1;1H[{self.i + 1}/{len(self.tests)}] {t['id']} {mark} {t['name']}"
          f"  {REV}{view}{RST}")
        w(render(cells, top=2, marks=marks))
        log = [(GREEN if l.startswith("✓") else RED if l.startswith("✗") else DIM) + l + RST
               for l in t["log"]]
        cols = shutil.get_terminal_size().columns
        w(f"\x1b[26;1H\x1b[2K{'  '.join(log)}")
        w(f"\x1b[27;1H\x1b[2K{DIM}{cut('←菜单  →0.3x播放  ↑↓首/尾/diff  数字跳转  Enter重跑  Q退出', cols - 1)}{RST}")

    def draw_menu(self):
        n = len(self.tests)
        top = min(max(getattr(self, "top", 0), self.i - MENU_ROWS + 1), self.i)     # 当前项保持在可见窗口内
        self.top = max(0, min(top, n - MENU_ROWS))
        head = f" 测试点 {self.i + 1}/{n}  ↑↓/数字选择  →/Enter/←收起"
        w(f"\x1b[{MENU_TOP};1H{REV}{cut(head, MENU_W)}{RST}")
        for r in range(MENU_ROWS):
            k, row = self.top + r, MENU_TOP + 1 + r
            if k >= n:
                w(f"\x1b[{row};1H{' ' * MENU_W}")
                continue
            t = self.tests[k]
            mark = f"{GREEN}✓{RST}" if t["ok"] else f"{RED}✗{RST}"
            cur = REV if k == self.i else ""
            w(f"\x1b[{row};1H {mark} {cur}{cut(t['id'] + ' ' + t['name'], MENU_W - 3)}{RST}")
        err = self.tests[self.i]["error"]
        row = MENU_TOP + 1 + MENU_ROWS
        w(f"\x1b[{row};1H{RED}{cut(err, MENU_W)}{RST}" if err else f"\x1b[{row};1H{' ' * MENU_W}")

    # ------------------------------------------------------------ actions
    def rerun(self):
        self.restore()
        w("\x1b[2J\x1b[H运行测试...\n")
        sys.stdout.flush()
        subprocess.run(RUN)
        input("\n按 Enter 返回")
        self.load()
        self.raw()

    def play(self):
        # stay on the alt screen; only hand the tty back in cooked mode
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved)
        w("\x1b[0m\x1b[2J\x1b[H")
        sys.stdout.flush()
        subprocess.run(["uvx", "asciinema", "play", "-s", "0.3",
                        os.path.join(OUT, self.tests[self.i]["cast"])])
        self.raw()

    def jump(self, digit):
        want = self.tests[self.i]["id"][:-3] + "_0" + digit
        self.i = next((k for k, t in enumerate(self.tests) if t["id"] == want), self.i)

    def key(self, k):
        n = len(self.tests)
        if k == "quit":
            return False
        if k == "enter" and not self.menu:
            self.rerun()
        elif not n:
            pass
        elif len(k) == 1 and k.isdigit():
            self.jump(k)
        elif self.menu:
            if k == "up":
                self.i = (self.i - 1) % n
            elif k == "down":
                self.i = (self.i + 1) % n
            elif k in ("right", "enter", "left", "esc"):
                self.menu = False
        elif k == "left":
            self.menu = True
        elif k == "right":
            self.play()
        elif k == "up":
            self.mode = (self.mode - 1) % len(MODES)
        elif k == "down":
            self.i = (self.i + 1) % n
        return True

    # ------------------------------------------------------------ terminal
    def raw(self):
        tty.setraw(sys.stdin.fileno())
        w("\x1b[?1049h\x1b[?25l")

    def restore(self):
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved)
        w("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()

    def run(self):
        self.saved = termios.tcgetattr(sys.stdin.fileno())
        self.raw()
        try:
            while True:
                self.draw()
                data = os.read(sys.stdin.fileno(), 64).decode(errors="replace")
                if not self.key(KEYS.get(data, data)):
                    break
        finally:
            self.restore()


if __name__ == "__main__":
    Viewer().run()
