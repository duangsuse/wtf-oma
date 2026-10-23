"""图形协议画矩形 + 补间动画。

唯一的绘制入口 draw(rects, out, snap=False):
  rects  {key: (x, y, w, h, (r, g, b), z, ease)}  单位=字符格, 可为小数(亚格定位); key 任意可哈希, 跨帧同 key 视为同一个矩形
         z     叠放次序(越大越上, 仅 layered 终端用)
         ease  缓动曲线 f(t: 0..1) -> 进度, 如 gra.EASE; None = 静态底色块: 不补间, 且只在 layered 终端上才画
  out    写终端的函数(与调用方的输出钩子一致)
  snap   True = 不补间, 直接到位(如窗口拖拽中)
  返回   终端已绘制的 key 集合(空 = 无协议, 调用方应改用字符背景色自己画这些矩形); layered() 为 True 时, 被画的矩形
         所在格子必须取消字符背景色(否则盖住图像)
每次调用传入"当前应显示的全部矩形": 新 key 创建, 位置/尺寸/颜色变了就按曲线补间到新值, 消失的 key 删除(传 {} 全部清掉)。
animating() 为 True 时调用方应以 ~60fps 再调 draw(同样的 rects) 推进动画。
set_curve(text) 换默认缓动曲线 EASE(CSS linear(...)); 解析失败返回 None。调用方每帧把要用的曲线放进 rects(通常就是 gra.EASE)。

direct 的图放置后不能缩放, 矩形变化时取"上一帧显示位置 ∪ 新位置"所覆盖整格的最小外接矩形, 只重传这一块(整格对齐 + c/r 按格放置): RGBA 图, 矩形内填色, 其余透明。
shm 只在尺寸/颜色变化时重传整块矩形, 位置变化只改放置。
settled(key) 该 key 的补间是否已到位, 调用方可据此在动画结束后再切换文字高亮。默认曲线 ease-in-out(平滑 S 形)。

首次 draw 时同步探测一次(一次往返), 终端分两类:
  shm     kitty / Ghostty / Warp / WezTerm: t=s 共享内存(Linux /dev/shm, 名字须带前导 '/'), 像素级精确。z=-1 的图像盖在字符背景色之上、
          文字之下, 所以只画"遮罩"(ease 非 None 的矩形), 底色仍由字符背景色负责
  direct  Konsole 等只支持直传(t=d)的终端: 同样的 RGBA 图, zlib 压缩(o=z)后 base64 分块直传(纯色块压缩比极高)。
          它们把一切负 z 图像都画在字符背景色之下, 所以 layered(): 所有矩形(含 ease=None 的底色)都画成图像, 且格子不能带背景色
  都不行 / 非 tty / 无像素尺寸 / MicroPython(浏览器) 一律无协议。环境变量 OMA_GRA=0 强制关闭。"""
import os, sys, time

Z = -1
_LAYER = -100000  # layered 终端的叠放起点: 最终 z = _LAYER + 调用方给的 z
_BASE = 7000      # 图像 id 起点, 避开调用方可能用的小 id
_mode = None      # None 未探测 | "shm" | "direct" | False
_live = {}        # key -> [image id, 当前显示的像素矩形, (rgb, z)]
_seq = _n = 0

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

def ease_in_out(t): return t * t * (3 - 2 * t)
EASE = ease_in_out
DUR = 0.18        # 补间时长(秒)

def set_curve(text):
    """换曲线; 成功返回控制点数, 解析失败返回 None(曲线不变)"""
    global EASE
    pts = parse_linear(text)
    if pts is None: return None
    EASE = eval_linear(pts)
    return len(pts)

# ---------- 补间 ----------
_tw = {}          # key -> [起点, 终点, 起始时刻], 矩形 = (x, y, w, h, r, g, b)
_active = False
_done = set()     # 上一次 draw 时已到位(不在动)的 key
def animating(): return _active
def settled(key): return key in _done

def _cur(a, now):
    e = a[3](min(1.0, (now - a[2]) / DUR))
    return tuple(p + (q - p) * e for p, q in zip(a[0], a[1]))

def _tween(rects, snap):
    global _active, _done
    now, res, _active, _done = time.time(), {}, False, set()
    for k in [k for k in _tw if k not in rects]: del _tw[k]
    for k, (x, y, w, h, c, _, ease) in rects.items():
        to, a = (x, y, w, h) + tuple(c), _tw.get(k)
        if a is None or snap or ease is None: a = _tw[k] = [to, to, now, ease]   # ease=None: 静态, 不补间
        else:
            a[3] = ease                                          # 曲线随调用方每帧给出(可中途更换)
            if a[1] != to: a[:] = [_cur(a, now), to, now, ease]  # 从当前显示位置重新出发
        if a[0] == a[1] or now - a[2] >= DUR: cur = to; _done.add(k)
        else: cur, _active = _cur(a, now), True
        res[k] = cur
    return res

# ---------- 终端 ----------
def _shm(raw):
    """raw 写进 /dev/shm, 返回 (base64(带 '/' 的名字), 文件路径); 终端读完会删掉它"""
    import base64
    global _n
    _n += 1
    name = "oma-%d-%d" % (os.getpid(), _n)
    path = "/dev/shm/" + name
    with open(path, "wb") as f: f.write(raw)
    return base64.b64encode(("/" + name).encode()).decode(), path

def _cell():
    """(格宽px, 格高px); 取不到像素尺寸返回 None"""
    import fcntl, termios, struct
    r, c, xp, yp = struct.unpack("HHHH", fcntl.ioctl(1, termios.TIOCGWINSZ, b"\0" * 8))
    return (xp // c, yp // r) if c and r and xp and yp else None

def _probe():
    """-> "shm" | "direct" | False; shm 与 direct 两个查询 + DA1 一次发出, 终端按序应答"""
    try:
        if os.environ.get("OMA_GRA") == "0" or not (os.isatty(0) and os.isatty(1)) or not _cell(): return False
        import select, base64
        path = None
        q = "\x1b_Gi=32,s=1,v=1,a=q,t=d,f=32;%s\x1b\\" % base64.b64encode(b"\0\0\0\xff").decode()
        if os.path.isdir("/dev/shm"):
            b64, path = _shm(b"\0\0\0\xff")
            q = "\x1b_Gi=31,s=1,v=1,a=q,t=s,f=32;%s\x1b\\" % b64 + q
        try:
            sys.stdout.write(q + "\x1b[c"); sys.stdout.flush()
            buf, end = b"", time.time() + 0.3
            while time.time() < end:                             # 图形应答先于 DA1
                if not select.select([0], [], [], max(0, end - time.time()))[0]: break
                buf += os.read(0, 256)
                i = buf.find(b"\x1b[?")
                if i >= 0 and b"c" in buf[i:]: break
            return "shm" if b"_Gi=31;OK" in buf else "direct" if b"_Gi=32;OK" in buf else False
        finally:
            if path:
                try: os.unlink(path)
                except OSError: pass
    except Exception:
        return False

def layered():
    """True = 终端把所有图像画在字符背景色之下(direct): 调用方要让被画矩形的格子不带背景色, 并把底色也交给 draw"""
    global _mode
    if _mode is None: _mode = _probe()
    return _mode == "direct"

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
    if shm: return "\x1b_G%s,t=s,q=2;%s\x1b\\" % (head, _shm(raw)[0])
    import zlib, base64
    data = base64.b64encode(zlib.compress(raw, 1)).decode()
    parts = [data[i:i + 4096] for i in range(0, len(data), 4096)] or [""]
    return "".join("\x1b_G%sm=%d,q=2;%s\x1b\\" % (head + ",t=d,o=z," if n == 0 else "", n < len(parts) - 1, p) for n, p in enumerate(parts))

def _place(iid, px, py, z, cw, ch, span=None):
    """把图像 iid 放到像素 (px, py): 光标移到所在格, X/Y 给格内像素偏移; span=(列数, 行数) 则让终端按整格缩放"""
    return "\x1b[%d;%dH\x1b_Ga=p,i=%d,p=1,X=%d,Y=%d,z=%d,C=1%s,q=2\x1b\\" % (
        py // ch + 1, px // cw + 1, iid, px % cw, py % ch, z, ",c=%d,r=%d" % span if span else "")

def draw(rects, out, snap=False):
    global _seq
    lay = layered()
    cell = _cell() if _mode else None
    if not cell: return set()
    cw, ch = cell
    use = {k: v for k, v in rects.items() if lay or v[6] is not None}
    buf = []
    for k in [k for k in _live if k not in use]:
        buf.append("\x1b_Ga=d,d=I,i=%d,q=2\x1b\\" % _live.pop(k)[0])
    for k, (x, y, w, h, *c) in _tween(use, snap).items():
        box = (round(x * cw), round(y * ch), max(1, round(w * cw)), max(1, round(h * ch)))
        rgb = tuple(max(0, min(255, int(v))) for v in c)
        z = _LAYER + use[k][5] if lay else Z
        live = _live.get(k)                                      # [image id, 图像/像素矩形签名, 放置/(rgb, z)签名]
        if live is None:
            _seq += 1; live = _live[k] = [_BASE + _seq, None, None]
        if _mode == "shm":                                       # 图像 = 矩形本身; 只在尺寸/颜色变了才重传, 位置变了只改放置
            img, at = (box[2], box[3], rgb), (box[0], box[1], z)
            redraw = live[1] != img
            if redraw:
                buf.append(_transmit((bytes(rgb) + b"\xff") * (box[2] * box[3]), box[2], box[3], live[0], True))
                live[1] = img
            if redraw or live[2] != at:
                live[2] = at
                buf.append(_place(live[0], box[0], box[1], z, cw, ch))
        elif (live[1], live[2]) != (box, (rgb, z)):              # direct: 放置不能缩放, 取新旧位置所覆盖整格的最小外接矩形, 只重画这一块
            c0, r0, c1, r1 = new = _cells(box, cw, ch)
            if live[1]:
                old = _cells(live[1], cw, ch)
                c0, r0, c1, r1 = min(old[0], new[0]), min(old[1], new[1]), max(old[2], new[2]), max(old[3], new[3])
            bb = (c0 * cw, r0 * ch, (c1 - c0) * cw, (r1 - r0) * ch)   # 整格对齐, 终端按 c/r 缩放时每帧图高恒为整数行, 不随亚格位置跳变
            buf.append(_transmit(_rgba(bb, box, rgb), bb[2], bb[3], live[0], False))
            buf.append(_place(live[0], bb[0], bb[1], z, cw, ch, (c1 - c0, r1 - r0)))
            live[1], live[2] = box, (rgb, z)
    if buf: out("\x1b7" + "".join(buf) + "\x1b8")
    return set(use)
