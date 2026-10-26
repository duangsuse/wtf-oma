"""CDP tests: run the %%js cells of v2/demo.ipynb against `node v2/demo.js repl` in a pty, and compare each
value (repr) with the cell's metadata `oma.want`. The cells' outputs are left alone: they are whatever was run in Jupyter.

    uvx --with pyte python test/nb.py [--update] [cell-id ...]      (test/nb.sh does the same)

A cell's metadata `oma.keys` is what gets typed while it runs: 'right' 'left' 'up' 'down' 'enter' 'esc' 'tab',
'type:<text>', 'click:X,Y' (left click at 0-based cell X,Y), or a number = seconds to wait. `oma.check: false` = only require no exception (timing-dependent values).
Cells without `oma` metadata are not run. --update writes the values into `oma.want` (the expectations).
The %%js client is the notebook's own magic cell (one CDP connection kept open). Port: NB_PORT (default 9231).
"""
import json, os, pty, select, struct, fcntl, termios, sys, threading, time

import pyte

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NB = os.path.join(ROOT, "v2", "demo.ipynb")
PORT, COLS, ROWS = int(os.environ.get("NB_PORT", 9231)), 100, 34
KEYS = {"right": "\x1b[C", "left": "\x1b[D", "down": "\x1b[B", "up": "\x1b[A", "enter": "\r", "esc": "\x1b", "tab": "\t"}
GREEN, RED, RST = "\x1b[32m", "\x1b[31m", "\x1b[0m"


def src(c):
    return "".join(c["source"])


def client(nb):
    """cdp_eval from the notebook's magic cell (IPython missing -> it skips registering the magic)"""
    ns = {}
    exec(next(src(c) for c in nb["cells"] if "def cdp_eval" in src(c)), ns)
    return ns["cdp_eval"]


class Term:
    def __init__(self):
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(ROOT)
            os.environ["OMA_GRA"] = "0"
            os.execvp("node", ["node", "v2/demo.js", "repl", f"port={PORT}"])
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))

    def pump(self, t):
        end = time.time() + t
        while time.time() < end:
            if select.select([self.fd], [], [], 0.05)[0]:
                try:
                    self.stream.feed(os.read(self.fd, 65536))
                except OSError:
                    return

    def type(self, k):
        if isinstance(k, (int, float)):
            return self.pump(k)
        if k.startswith("click:"):
            x, y = (int(v) + 1 for v in k[6:].split(","))
            k = f"type:\x1b[<0;{x};{y}M\x1b[<0;{x};{y}m"
        os.write(self.fd, (k[5:] if k.startswith("type:") else KEYS[k]).encode())
        self.pump(0.35)

    def text(self):
        return "\n".join(l.rstrip() for l in self.screen.display if l.strip())

    def close(self):
        os.kill(self.pid, 9)


def main(args):
    update = "--update" in args
    only = [a for a in args if not a.startswith("--")]
    nb = json.load(open(NB))
    cdp_eval, term, n, fails = client(nb), Term(), 0, 0
    term.pump(1.5)
    try:
        for c in nb["cells"]:
            meta = c["metadata"].get("oma")
            if c["cell_type"] != "code" or meta is None or (only and c["id"] not in only):
                continue
            code = src(c).split("\n", 1)[1]
            res = {}

            def run():
                try:
                    res["v"] = cdp_eval(code, PORT, 30)
                except Exception as e:
                    res["e"] = str(e)
            th = threading.Thread(target=run)
            th.start()
            term.pump(0.6)
            for k in meta.get("keys", []):
                term.type(k)
            th.join(30)
            got = repr(res["v"]) if "v" in res else None
            want = meta.get("want")
            ok = "e" not in res and th.is_alive() is False and (not meta.get("check", True) or update or got == want)
            n += 1
            fails += not ok
            title = code.strip().split("\n")[0][:60]
            print(f"{GREEN + 'PASS' if ok else RED + 'FAIL'}{RST} {c['id']} {title}")
            if not ok:
                print(f"     want {want}\n     got  {got}" + (f"\n     error {res['e']}" if "e" in res else "")
                      + ("\n     (still waiting for input)" if th.is_alive() else ""))
                print("\n".join("     | " + l for l in term.text().split("\n")))
                if th.is_alive():
                    term.type("esc")
                    th.join(5)
            if update and "v" in res and meta.get("check", True):
                meta["want"] = got
    finally:
        term.close()
    if update:
        json.dump(nb, open(NB, "w"), ensure_ascii=False, indent=1)
        print("oma.want written to", os.path.relpath(NB))
    print(f"{n - fails}/{n} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
