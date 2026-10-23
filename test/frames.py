"""Frame (de)serialisation and ANSI rendering; stdlib only (shared by runner/viewer)."""
import json

NAMES = {"black": 0, "red": 1, "green": 2, "brown": 3, "yellow": 3, "blue": 4,
         "magenta": 5, "cyan": 6, "white": 7}


def _color(c, base):
    """SGR params for a pyte colour; base 30 = fg, 40 = bg."""
    if c == "default":
        return str(base + 9)
    if c in NAMES:
        return str(base + NAMES[c])
    if c.startswith("bright") and c[6:] in NAMES:
        return str(base + 60 + NAMES[c[6:]])
    try:
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
        return f"{base + 8};2;{r};{g};{b}"
    except ValueError:
        return str(base + 9)


MARK_BG = {"red": "48;2;160;0;0", "green": "48;2;0;130;0"}


def sgr(cell, mark=None):
    _, fg, bg, bold, rev = cell[:5]
    p = ["0", _color(fg, 30), _color(bg, 40)]
    if bold:
        p.append("1")
    if mark:  # background only; reverse would swap it away
        p.append(MARK_BG[mark])
    elif rev:
        p.append("7")
    return "\x1b[" + ";".join(p) + "m"


def render(cells, top=1, left=1, marks=None):
    """ANSI string drawing `cells` with its top-left at (top, left), 1-based.
    `marks`: {(x, y): "red" | "green"} background overrides (diff view)."""
    marks = marks or {}
    out = []
    for y, row in enumerate(cells):
        out.append(f"\x1b[{top + y};{left}H")
        prev = None
        for x, cell in enumerate(row):
            s = sgr(cell, marks.get((x, y)))
            if s != prev:
                out.append(s)
                prev = s
            out.append(cell[0])  # "" = continuation of a wide char
    out.append("\x1b[0m")
    return "".join(out)


def diff(a, b):
    return {(x, y) for y in range(len(a)) for x in range(len(a[y]))
            if a[y][x] != b[y][x]}


def load(path):
    with open(path) as f:
        return json.load(f)
