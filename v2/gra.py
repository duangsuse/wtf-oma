#!/usr/bin/env python3
"""图形协议画矩形 + 补间动画, 独立进程。菜单(menu.js)只管声明"现在应有哪些矩形", 这里负责补间与终端图像。

两种用法, 矩形语法相同:  [key=][from->]x,y,w,h[#rrggbb][@z]    单位=字符格, 可小数; key 缺省取序号
  命令行(放完动画即退出):  gra.py DUR=180 EASE="linear(0, 0.25 25% 75%, 1)" "0,0,10,3->5,0,10,3#1f8c1f" ...
  stdin 流(进程不丢, stdin 非 tty):  每行 "首词 参数", 首词查 CMD 字典; 本进程回写的行同样按首词分派(menu.js 里的 FROM_PY)
    JS -> PY   probe          探测终端图形能力(要查询的转义序列经 out 交给对方写, 应答由对方转交 reply)
               reply <原始应答>
               draw <矩形...>  当前应显示的全部矩形; 新 key 创建, 变了就补间, 消失的 key 删除; 空 = 全清
               snap <矩形...>  同 draw 但不补间(拖拽中)
               ease <linear(...)>
               dur <毫秒>      补间时长(不回应)
    PY -> JS   out <转义序列>   要写到终端的字节(对方统一输出, 保证与文字帧不交错)
               mode shm|direct|none
               state <key...>  正在补间(未到位)的 key; 每次 draw/snap 后一定回一行, 之后集合变化时再发
               ease <N>        新曲线的控制点数, 0 = 解析失败(曲线不变)
    EOF = 清掉所有图像并退出

矩形语法里 "from->" 表示补间: 有 from 的新 key 从 from 出发; 已存在的 key 一律从当前显示位置出发(中途改目标不跳变); 空 from("->x,y,w,h")
= 新 key 直接到位。没有 "->" = 不补间(静态底色块, 只在 layered 终端才需要)。

终端分两类(首次 probe 探测):
  shm     kitty / Ghostty / Warp / WezTerm: t=s 共享内存, 像素级精确; z=-1 的图像盖在字符背景色之上、文字之下
  direct  Konsole 等只支持直传(t=d): zlib 压缩(o=z) + base64 分块; 它们把负 z 图像都画在字符背景色之下(menu.js 据此 layered)
  都不行 / 非 tty / 无像素尺寸 一律 none。环境变量 OMA_GRA=0 强制关闭。像素格尺寸取自 /dev/tty 的 TIOCGWINSZ(Node 没有 ioctl)。
direct 的图放置后不能缩放, 矩形变化时取"上一帧位置 ∪ 新位置"所覆盖整格的最小外接矩形只重传这一块; shm 只在尺寸/颜色变化时重传。"""
import base64, os, re, select, struct, sys, time, zlib

DUR = 0.18                  # 补间时长(秒)
_LAYER, _BASE = -100000, 7000   # layered 终端的叠放起点 / 图像 id 起点
STREAM = not sys.stdin.isatty()

# ---------- 曲线: CSS linear() -> ease(t) ----------
def parse_linear(src):
    """CSS linear(...) -> [[x, y]] 控制点(x 已补全且单调不减); 解析不了返回 None"""
    s = src.strip()
    if not (s.lower().startswith("linear(") and s.endswith(")")): return None
    pts = []                                                     # [x|None, y]
    try:
        for stop in s[7:-1].split(","):
            y, *xs = stop.split()
            y = float(y)
            if xs:
                for x in xs: pts.append([float(x.rstrip("%")) / 100, y])    # 1~2 个百分比
            else: pts.append([None, y])                          # 位置留空, 稍后补全
    except ValueError: return None
    if len(pts) < 2: return None
    if pts[0][0] is None: pts[0][0] = 0
    if pts[-1][0] is None: pts[-1][0] = 1
    hi = float("-inf")                                           # 输入位置必须单调不减
    for p in pts:
        if p[0] is not None: p[0] = hi = max(hi, p[0])
    i = 0                                                        # 缺省位置在相邻已知点间等分
    while i < len(pts):
        if pts[i][0] is None:
            j = i
            while pts[j][0] is None: j += 1
            x0, x1 = pts[i - 1][0], pts[j][0]
            for n in range(i, j): pts[n][0] = x0 + (x1 - x0) * (n - i + 1) / (j - i + 1)
            i = j
        i += 1
    return pts

def eval_linear(pts):
    def ease(t):
        if t <= pts[0][0]: return pts[0][1]
        if t >= pts[-1][0]: return pts[-1][1]
        i = 1
        while pts[i][0] < t: i += 1
        a, b = pts[i - 1], pts[i]
        if b[0] == a[0]: return a[1]
        return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0])
    return ease

EASE = lambda t: t * t * (3 - 2 * t)                             # 默认 ease-in-out

# ---------- 输出 ----------
def send(s):
    if STREAM: sys.stdout.write(s + "\n"); sys.stdout.flush()
def out(s):
    if STREAM: send("out " + s)
    else: sys.stdout.write(s); sys.stdout.flush()

# ---------- 终端探测 ----------
mode = None                 # None 未探测 | "shm" | "direct" | False
_tty = _probe_file = None
_n = _seq = 0

def setmode(m):
    global mode
    mode = m
    send("mode " + (m or "none"))

def cell():
    """(格宽px, 格高px); 取不到像素尺寸返回 None"""
    global _tty
    try:
        if _tty is None: _tty = os.open("/dev/tty", os.O_RDONLY)
        import fcntl, termios
        r, c, xp, yp = struct.unpack("HHHH", fcntl.ioctl(_tty, termios.TIOCGWINSZ, b"\0" * 8))
    except OSError: return None
    return (xp // c, yp // r) if c and r and xp and yp else None

def _shm(raw):
    """raw 写进 /dev/shm, 返回 (base64(带 '/' 的名字), 文件路径); 终端读完会删掉它"""
    global _n
    _n += 1
    name = "oma-%d-%d" % (os.getpid(), _n)
    path = "/dev/shm/" + name
    with open(path, "wb") as f: f.write(raw)
    return base64.b64encode(("/" + name).encode()).decode(), path

def probe(_):
    global _probe_file
    if os.environ.get("OMA_GRA") == "0" or not cell(): return setmode(False)
    q = "\x1b_Gi=32,s=1,v=1,a=q,t=d,f=32;%s\x1b\\" % base64.b64encode(b"\0\0\0\xff").decode()
    if os.path.isdir("/dev/shm"):
        b64, _probe_file = _shm(b"\0\0\0\xff")
        q = "\x1b_Gi=31,s=1,v=1,a=q,t=s,f=32;%s\x1b\\" % b64 + q
    out(q + "\x1b[c")                                            # 两个图形查询 + DA1, 终端按序应答, 图形应答先于 DA1

def reply(s):
    global _probe_file
    if _probe_file:
        try: os.unlink(_probe_file)
        except OSError: pass
        _probe_file = None
    setmode("shm" if "_Gi=31;OK" in s else "direct" if "_Gi=32;OK" in s else False)

def tty_reply():
    """命令行用法: 自己从 tty 读应答直到 DA1"""
    import termios, tty
    old = termios.tcgetattr(0); tty.setcbreak(0)
    buf, end = "", time.time() + 0.3
    try:
        while time.time() < end and not re.search(r"\x1b\[\?[\d;]*c", buf):
            if select.select([0], [], [], max(0, end - time.time()))[0]: buf += os.read(0, 256).decode("latin-1")
    finally: termios.tcsetattr(0, termios.TCSADRAIN, old)
    return buf

# ---------- 补间 ----------
tw = {}                     # key -> [起点, 终点, 起始时刻], 矩形 = (x, y, w, h, r, g, b)
moving = set()              # 上一次补间计算时还没到位的 key
last = {}                   # 上一次 draw 的矩形, 动画期间 tick 用它推进

def _cur(a, now):
    e = EASE(min(1.0, (now - a[2]) / DUR))
    return tuple(p + (q - p) * e for p, q in zip(a[0], a[1]))

def tween(rects, snap):
    global moving
    now, res, moving = time.time(), {}, set()
    for k in [k for k in tw if k not in rects]: del tw[k]
    for k, (frm, to, rgb, z, ani) in rects.items():
        to, a = to + rgb, tw.get(k)
        if not ani or snap: a = tw[k] = [to, to, now]
        elif a is None: a = tw[k] = [frm + rgb if frm else to, to, now]
        elif a[1] != to: a[:] = [_cur(a, now), to, now]          # 从当前显示位置重新出发
        if a[0] == a[1] or now - a[2] >= DUR: res[k] = to
        else: res[k] = _cur(a, now); moving.add(k)
    return res

# ---------- 图像 ----------
live = {}                   # key -> [image id, 当前显示的像素矩形, 放置签名]

def _cells(r, cw, ch):
    """像素矩形 (x, y, w, h) 覆盖的整格范围 (c0, r0, c1, r1), 右下不含"""
    return r[0] // cw, r[1] // ch, -(-(r[0] + r[2]) // cw), -(-(r[1] + r[3]) // ch)

def _rgba(bb, box, rgb):
    """外接矩形 bb(像素, 整格对齐) 大小的 RGBA 图: box 内填 rgb, 其余全透明"""
    x, y = box[0] - bb[0], box[1] - bb[1]
    row = bytes(4 * x) + (bytes(rgb) + b"\xff") * box[2] + bytes(4 * (bb[2] - x - box[2]))
    return bytes(4 * bb[2] * y) + row * box[3] + bytes(4 * bb[2] * (bb[3] - y - box[3]))

def _transmit(raw, w, h, iid, shm):
    """传图: shm 写共享内存; direct 用 zlib 压缩(o=z)后 base64 分块直传(纯色块压缩比极高)"""
    head = "a=t,f=32,s=%d,v=%d,i=%d" % (w, h, iid)
    if shm:
        b64, _ = _shm(raw)
        return "\x1b_G%s,t=s,q=2;%s\x1b\\" % (head, b64)
    data = base64.b64encode(zlib.compress(raw, 1)).decode()
    parts = [data[i:i + 4096] for i in range(0, len(data), 4096)] or [""]
    return "".join("\x1b_G%sm=%d,q=2;%s\x1b\\" % (head + ",t=d,o=z," if n == 0 else "", n < len(parts) - 1, p) for n, p in enumerate(parts))

def _place(iid, px, py, z, cw, ch, span=None):
    """把图像 iid 放到像素 (px, py): 光标移到所在格, X/Y 给格内像素偏移; span=(列数, 行数) 则让终端按整格缩放"""
    return "\x1b[%d;%dH\x1b_Ga=p,i=%d,p=1,X=%d,Y=%d,z=%d,C=1%s,q=2\x1b\\" % (
        py // ch + 1, px // cw + 1, iid, px % cw, py % ch, z, ",c=%d,r=%d" % span if span else "")

def render(rects, snap):
    global _seq
    px = cell()
    if not (mode and px): return
    cw, ch = px
    buf = ["\x1b_Ga=d,d=I,i=%d,q=2\x1b\\" % live.pop(k)[0] for k in [k for k in live if k not in rects]]
    for k, (x, y, w, h, *c) in tween(rects, snap).items():
        box = (round(x * cw), round(y * ch), max(1, round(w * cw)), max(1, round(h * ch)))
        rgb = tuple(max(0, min(255, int(v))) for v in c)
        z = _LAYER + rects[k][3] if mode == "direct" else -1
        cur = live.get(k)                                        # [image id, 图像/像素矩形签名, 放置/(rgb, z)签名]
        if cur is None:
            _seq += 1; cur = live[k] = [_BASE + _seq, None, None]
        if mode == "shm":                                        # 图像 = 矩形本身; 只在尺寸/颜色变了才重传, 位置变了只改放置
            img, at = (box[2], box[3], rgb), (box[0], box[1], z)
            redraw = cur[1] != img
            if redraw:
                buf.append(_transmit((bytes(rgb) + b"\xff") * (box[2] * box[3]), box[2], box[3], cur[0], True))
                cur[1] = img
            if redraw or cur[2] != at:
                cur[2] = at
                buf.append(_place(cur[0], box[0], box[1], z, cw, ch))
        elif (cur[1], cur[2]) != (box, (rgb, z)):                # direct: 取新旧位置所覆盖整格的最小外接矩形, 只重画这一块
            c0, r0, c1, r1 = new = _cells(box, cw, ch)
            if cur[1]:
                old = _cells(cur[1], cw, ch)
                c0, r0, c1, r1 = min(old[0], new[0]), min(old[1], new[1]), max(old[2], new[2]), max(old[3], new[3])
            bb = (c0 * cw, r0 * ch, (c1 - c0) * cw, (r1 - r0) * ch)   # 整格对齐, 终端按 c/r 缩放时每帧图高恒为整数行
            buf.append(_transmit(_rgba(bb, box, rgb), bb[2], bb[3], cur[0], False))
            buf.append(_place(cur[0], bb[0], bb[1], z, cw, ch, (c1 - c0, r1 - r0)))
            cur[1], cur[2] = box, (rgb, z)
    if buf: out("\x1b7" + "".join(buf) + "\x1b8")

# ---------- 命令 ----------
SPEC = re.compile(r"(?:(\w+)=)?(?:([-\d.,]*)->)?([-\d.,]+)(?:#([0-9a-fA-F]{6}))?(?:@(-?\d+))?$")

def spec(i, s):
    """'[key=][from->]x,y,w,h[#rrggbb][@z]' -> (key, (from|None, to, rgb, z, 是否补间))"""
    m = SPEC.match(s)
    if not m: raise ValueError("bad rect: " + s)
    k, f, t, c, z = m.groups()
    nums = lambda g: tuple(float(v) for v in g.split(","))
    c = c or "ffffff"
    return k or str(i), (nums(f) if f else None, nums(t), tuple(int(c[j:j + 2], 16) for j in (0, 2, 4)), int(z or 0), f is not None)

def draw(rest, snap=False):
    global last
    last = dict(spec(i, s) for i, s in enumerate(rest.split()))
    render(last, snap)
    send("state " + " ".join(sorted(moving)))

def snap(rest): draw(rest, True)

def ease(rest):
    global EASE
    pts = parse_linear(rest)
    if pts: EASE = eval_linear(pts)
    send("ease %d" % len(pts or ()))

def dur(rest):
    global DUR
    DUR = float(rest) / 1000

CMD = {f.__name__: f for f in (probe, reply, draw, snap, ease, dur)}

def tick():
    before = set(moving)
    render(last, False)
    if moving != before: send("state " + " ".join(sorted(moving)))

def main():
    global DUR
    specs = []
    for a in sys.argv[1:]:
        k, _, v = a.partition("=")
        if k == "DUR": DUR = float(v) / 1000
        elif k == "EASE": ease(v)
        else: specs.append(a)
    if not STREAM:
        probe("")
        if mode is None: reply(tty_reply())
        if not mode: sys.exit("gra: 终端没有图形协议")
        draw(" ".join(specs))
        while moving: time.sleep(1 / 60); tick()
        return
    buf = b""
    while True:
        if not select.select([0], [], [], 1 / 60 if moving else None)[0]: tick(); continue
        d = os.read(0, 65536)
        if not d: break
        *lines, buf = (buf + d).split(b"\n")
        for l in lines:
            w, _, rest = l.decode(errors="replace").partition(" ")
            try: CMD[w](rest)
            except Exception as e: print("gra:", w, repr(e), file=sys.stderr)
    draw("")

if __name__ == "__main__":
    main()
