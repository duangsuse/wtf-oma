#!/usr/bin/env python3
"""Omarchy 风格 Go… 菜单。纯标准库。tree.json 加载失败则回滚内置菜单。

用法: menu.py [Learn/Arch] [pop=stack|replace]     arg1=启动时展开并选中的路径
  pop=stack 级联弹出 | pop=replace(默认) 原位替换; 命令行参数或环境变量 pop 均可
  拖拽: 按住窗口顶部标题区域, 或按住任意项并移动(按住 >=0.1s 才判定为拖拽, 否则松开时算点击); 点击窗口外空白 = onblur(默认在点击处开新菜单)
  搜索: 输入即在当前菜单下深搜(结果旁淡色显示所在路径); 以 './' 开头则只搜当前层
  键: 输入即搜索 ↑↓选择 →/Enter进入 ←/Esc/Bs返回(先清空搜索, 空则返回) Del/Esc清空搜索 Alt-Bs/Ctrl-W删一个词 滚轮; Ctrl-C 退出
  动画: 终端支持 kitty 图形协议时(共享内存 shm: kitty/Ghostty/Warp/WezTerm; 直传 zlib 压缩: Konsole 等), 选中高亮是 z<0 的遮罩矩形,
       切换选中项时按曲线补间(默认 ease-in-out), 补间到位后文字才变高亮色; shm 只改放置, direct 每帧只重传新旧位置的最小外接矩形; 否则退回字符背景色
       Ctrl-V 粘贴 CSS linear(...) 即换曲线(如 linear(0, 0.25 25% 75%, 1)); 解析失败在屏底提示; 其他粘贴内容当作搜索输入

接口: start(sexp, onpath=show_cmd, rempos='label_rt|rd', onblur=None, args=(), root=True, quit=Ctrl-C) -> Session   事件驱动, 可嵌进任何主循环
  Session.feed(text) / render()   输入字节流 / 重绘; gra.animating() 为真时宿主应 ~60fps 调 render
  Session.open_root(x, y) / open_path('Learn/Arch')   脚本化开窗口; Menu.move(x, y) + Menu.remember() 记住位置
  prompt(sexp, ...)    start() 的 CLI 主循环(termios raw + 阻塞读); 退出键 quit 可为 None(完全由宿主决定退出)
  onpath(s)            打开路径(如 'Learn/Arch')时调用; 默认在屏幕底部显示重开该路径的 python 命令
  rempos               锚点列表, 按 | 取第一个可用的; 角 = l/r + t/d。
                       label_<角>: 打开它的那一项标签的角, 子窗口默认就放在该角; <角>(如 rd): 终端的角
                       拖拽后记忆窗口相对锚点的偏移(全局 REMEMBER), 下次优先于默认位置
  onblur(x, y, open)   点击所有窗口之外时调用; open(x, y) 在该处开新根菜单。默认 open(x, y)

浏览器: 核心只经 size()/out() 触碰终端, 输入是 feed(text) 喂入的原始终端字节流(见 index.html, MicroPython+xterm.js)。

结构:  Menu.view() -> [Box]      局部坐标的声明式视图; Menu.event(kind, arg) 处理按键/点击/悬停
       layout(wins)  -> [Box]   按 z 序(列表末尾=最上层/焦点)转绝对坐标
       route(boxes,x,y) -> Box  命中测试,取最上层带 id 的 Box
       paint(boxes)             同一份 Box 列表绘制
       Session                  窗口栈 + 拖拽/按下状态, feed() 把输入记号翻译成窗口事件
"""
import json, os, sys, time
import gra

ITEM_H = 3
DRAG_DELAY = 0.1      # 按住项后至少这么久再移动才算拖拽(秒)
POP, REMPOS, ONPATH = "replace", "label_rt|rd", None
REMEMBER = {}          # 锚点名 -> (dx, dy): 上次拖拽后窗口相对该锚点的偏移
STATUS = ""            # 屏幕底部一行
_seq = 0
def uid():
    global _seq
    _seq += 1
    return _seq
DEFAULT_TREE = ["Go", ["\uf00a  Apps"], ["\uf19d  Learn"], ["\uf135  Trigger"], ["Style"],
                ["Setup"], ["About"], ["System"]]
try: TREE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tree.json")
except Exception: TREE_PATH = "tree.json"           # MicroPython 没有 abspath/__file__

# ---------- 终端 I/O: 核心只经由这三个钩子接触终端, 浏览器侧直接替换它们 ----------
def size():
    c, r = os.get_terminal_size(); return c, r
def out(s):
    sys.stdout.write(s); sys.stdout.flush()
ENTER = "\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1003h\x1b[?1006h\x1b[?2004h"
LEAVE = "\x1b[0m\x1b[?2004l\x1b[?1006l\x1b[?1003l\x1b[?1000l\x1b[?25h\x1b[?1049l"

def parse(a):
    """["icon  Name", [child], ...] -> {icon, name, kids}"""
    if not (isinstance(a, list) and a and isinstance(a[0], str)):
        raise ValueError("bad node: " + repr(a)[:40])
    icon, sep, name = a[0].partition("  ")
    if not sep: icon, name = "", a[0]
    return {"icon": icon, "name": name.strip(), "kids": [parse(k) for k in a[1:]]}

def load_tree(path=TREE_PATH, text=None):
    """text 给定则解析它(浏览器: fetch 来的), 否则读 path。返回 (sexp, 失败说明或 None)"""
    try:
        if text is None:
            with open(path) as f: text = f.read()
        raw = json.loads(text)
        parse(raw); return raw, None
    except Exception as e:
        return DEFAULT_TREE, "tree.json 加载失败, 使用内置菜单: %s: %s" % (type(e).__name__, e)

BG, BORDER = (2, 11, 20), (26, 77, 26)
TEXT, DIM = (207, 232, 245), (106, 138, 160)
SEL_BG, SEL_FG = (8, 32, 22), (31, 140, 31)
CORNER = {(1, 1): "┏", (1, 0): "┓", (0, 1): "┗", (0, 0): "┛"}   # (top?, left?)

class Box:
    def __init__(self, x, y, w, h, id=None, bg=None, fg=None, text="", border=None, win=None, anim=None, lit=None):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.id = id               # 非 None 才参与路由
        self.bg, self.fg = bg, fg  # bg 非 None 则不透明填充
        self.text, self.border, self.win = text, border, win   # win: layout 时填入所属窗口
        self.anim = anim           # 缓动曲线 f(t)->进度 或 None。曲线非 None: 有图形协议时该 Box 的 bg 改画成 z<0 的遮罩, 跨帧位置/尺寸/颜色按该曲线补间; 每窗口至多一个
        self.lit = lit             # 颜色 或 None: 同窗口的动画遮罩补间到位后, 文字才换成这个颜色(无遮罩时立即)
    def moved(self, dx, dy, win):
        return Box(self.x + dx, self.y + dy, self.w, self.h, self.id, self.bg, self.fg, self.text, self.border, win, self.anim, self.lit)

# ---------- 菜单窗口 ----------
WIDE = ((0x1100, 0x115F), (0x2E80, 0xA4CF), (0xAC00, 0xD7A3), (0xF900, 0xFAFF), (0xFE30, 0xFE6F), (0xFF00, 0xFF60),
        (0xFFE0, 0xFFE6), (0x1F300, 0x1F64F), (0x1F7E0, 0x1F7EB), (0x1F900, 0x1F9FF), (0x20000, 0x3FFFD))   # 东亚宽 + emoji
def wide(c):
    o = ord(c); return o >= 0x1100 and any(a <= o <= b for a, b in WIDE)
def cw(t): return sum(2 if wide(c) else 1 for c in t)
def at(node, ip):
    for i in ip: node = node["kids"][i]
    return node

def names(node, ip): return [at(node, ip[:n])["name"] for n in range(1, len(ip) + 1)]   # 沿路径各级的名字
def trail(node, ip): return names(node, ip)[:-1]                                         # 不含自身的祖先名

def matches(node, q):
    """深搜 node 之下名字含 q 的项(浅层优先); q 为空或以 './' 开头则只看当前层。返回下标路径元组列表"""
    q = q.lower(); local = not q or q.startswith("./")
    if q.startswith("./"): q = q[2:]
    out = []
    def walk(n, ip):
        for i, k in enumerate(n["kids"]):
            if q in k["name"].lower(): out.append(ip + (i,))
            if not local: walk(k, ip + (i,))
    walk(node, ())
    return sorted(out, key=len)
def max_vis(): return max(3, (size()[1] - 7) // ITEM_H)
def height(n): return 5 + max(min(n, max_vis()), 1) * ITEM_H
def row_y(pos): return 4 + pos * ITEM_H                       # 第 pos 个可见项在窗口内的 y
def item_label(k): return (k["icon"] + "  " if k["icon"] else "") + k["name"]

def resolve(node, s):
    """'Learn/Arch' -> [kid 下标...]; 名字自带 '/' 时回溯匹配, 忽略大小写; 失败返回 None"""
    if not s: return []
    for i, k in enumerate(node["kids"]):
        n = k["name"].lower()
        if s.lower() == n: return [i]
        if s.lower().startswith(n + "/") and (r := resolve(k, s[len(n) + 1:])) is not None: return [i] + r
    return None

CORNERS = ("lt", "ld", "rt", "rd")

def corner(c, x, y, w, h): return x + (w if c[0] == "r" else 0), y + (h if c[1] == "d" else 0)

def anchor(opener):
    """opener=(x,y,w,h) 打开本窗口的那一项标签的矩形(无则 None)"""
    cols, rows = size()
    for a in REMPOS.split("|"):
        if a.startswith("label_") and opener and a[6:] in CORNERS: return a, corner(a[6:], *opener)
        if a in CORNERS: return a, corner(a, 0, 0, cols, rows)
    return None, (0, 0)

class Menu:
    """一个菜单窗口: 几何 + 状态; view() -> [Box] 局部坐标, event() 返回 None | 'close' | ('open', 项路径)"""
    def __init__(self, node, path, depth, chain, xy, opener=None, alt_x=None, explicit=False, parent=None):
        """xy=默认位置; 有记忆偏移则用 锚点+偏移 (explicit=True 时忽略记忆); alt_x: 右侧放不下时翻到其左边"""
        cols, rows = size()
        a, (ax, ay) = anchor(opener)
        remembered = a in REMEMBER
        if remembered and not explicit: xy = ax + REMEMBER[a][0], ay + REMEMBER[a][1]
        elif a and a.startswith("label_"): xy = ax, ay
        self.node, self.path, self.depth, self.chain, self.parent = node, path, depth, chain, parent
        self.anchor = (a, ax, ay)
        self.sel, self.q, self.top = (0,), "", 0         # 选中项路径 / 搜索串 / 首个可见项的序号
        self.name = "m%d" % uid()
        self.w = max(32, max([cw(item_label(k)) for k in node["kids"]] + [0]) + 9)
        self.h = height(len(node["kids"]))
        x = alt_x - self.w if alt_x is not None and xy[0] + self.w > cols and not remembered else xy[0]
        self.x, self.y = 0, 0
        self.move(x, xy[1])

    def move(self, x, y):
        """放到 (x, y), 夹在终端范围内"""
        cols, rows = size()
        self.x, self.y = max(0, min(x, cols - self.w)), max(0, min(y, rows - self.h))

    def remember(self):
        """记住本窗口相对锚点的偏移(全局 REMEMBER), 之后同锚点的新窗口默认放在这里"""
        a, ax, ay = self.anchor
        if a == "rd": ax, ay = size()
        if a: REMEMBER[a] = (self.x - ax, self.y - ay)

    def hits(self): return matches(self.node, self.q)

    def view(self):
        W, q, idx, vis = self.w, self.q, self.hits(), max_vis()
        if self.sel in idx:
            n = idx.index(self.sel); self.top = min(max(self.top, n - vis + 1), n)
        self.top = max(0, min(self.top, len(idx) - vis))
        self.h = height(len(idx))
        bs = [Box(0, 0, W, self.h, id=("win",), bg=BG, border=BORDER),
              Box(1, 1, W - 2, 3, id=("title",)),
              Box(3, 2, W - 6, 1, text=q + "▏" if q else self.node["name"] + "…", fg=TEXT if q else DIM)]
        if self.top > 0: bs.append(Box(W - 6, 2, 1, 1, text="▲", fg=DIM))
        if self.top + vis < len(idx): bs.append(Box(W - 4, 2, 1, 1, text="▼", fg=DIM))
        if not idx: bs.append(Box(3, 5, W - 6, 1, text="No matches", fg=DIM))
        for pos, ip in enumerate(idx[self.top:self.top + vis]):
            k, y, on = at(self.node, ip), row_y(pos), ip == self.sel
            label = item_label(k)
            bs.append(Box(1, y, W - 2, ITEM_H, id=("item", ip), bg=SEL_BG if on else BG, anim=gra.EASE if on else None))
            bs.append(Box(3, y + 1, W - 8, 1, text=label, fg=TEXT, lit=SEL_FG if on else None))   # 选中行文字: 遮罩到位后才点亮
            if len(ip) > 1:                                      # 深搜结果: 名字后淡色显示所在路径
                tx = 3 + cw(label) + 2
                bs.append(Box(tx, y + 1, W - 6 - tx, 1, text="‹ " + "/".join(trail(self.node, ip)), fg=DIM))
            if k["kids"]: bs.append(Box(W - 5, y + 1, 1, 1, text="›", fg=DIM, lit=SEL_FG if on else None))
        return bs

    def event(self, kind, arg):
        if kind == "key": return self.key(arg)
        if arg[0] == "item":                                     # hover / click
            self.sel = arg[1]
            if kind == "click": return ("open", arg[1])

    def key(self, k):
        idx = self.hits()
        if k in ("up", "down"):
            if idx:
                n = idx.index(self.sel) if self.sel in idx else 0
                self.sel = idx[(n + (1 if k == "down" else -1)) % len(idx)]
        elif k in ("right", "enter"):
            if self.sel in idx: return ("open", self.sel)
        elif k == "left": return "close"
        elif k == "del": self.q = ""
        elif k in EDIT:                                          # 搜索串为空时, 编辑键变成"返回"
            if not self.q: return "close"
            self.q = EDIT[k](self.q)
        elif printable(k): self.q += k
        idx = self.hits()
        if idx and self.sel not in idx: self.sel = idx[0]

def drop_word(q):
    q = q.rstrip(" ")
    while q and q[-1] not in " /": q = q[:-1]
    return q
EDIT = {"esc": lambda q: "", "bs": lambda q: q[:-1], "altbs": drop_word}

def printable(k): return len(k) == 1 and k >= " " and k != "\x7f"

def drop_deeper(wins, w):
    wins[:] = [x for x in wins if x.chain != w.chain or x.depth <= w.depth]

def close_menu(wins, w):
    """replace 模式下回到父窗口(放在当前位置), 否则关掉自己及更深的窗口。返回 True 表示已无窗口"""
    if w.depth and POP == "replace" and w.parent:
        w.parent.move(w.x, w.y)
        wins[wins.index(w)] = w.parent
    else:
        wins[:] = [x for x in wins if x.chain != w.chain or x.depth < w.depth]
        return not wins

def open_item(wins, w, ip):
    kid, path = at(w.node, ip), w.path + names(w.node, ip)
    try: ONPATH("/".join(path))
    except Exception: pass
    drop_deeper(wins, w)
    if not kid["kids"]: return
    y = w.y + row_y(w.hits().index(ip) - w.top)
    c = Menu(kid, path, w.depth + 1, w.chain, (w.x + w.w, y), (w.x, y, w.w, ITEM_H), alt_x=w.x, parent=w)
    if POP == "replace":
        c.move(w.x, w.y)
        wins[wins.index(w)] = c
    else: wins.append(c)

def act(wins, w, r):
    """处理 Menu.event 的结果。返回 True 表示已无窗口"""
    if r == "close": return close_menu(wins, w)
    if r: open_item(wins, w, r[1])

def quote(s): return s if s and all(c.isalnum() or c in "-_./" for c in s) else "'" + s.replace("'", "'\\''") + "'"

def show_cmd(s):
    """默认 onpath: 底部显示重开该路径的命令"""
    global STATUS
    STATUS = " ".join(["python3", getattr(sys, "argv", ["menu.py"])[0].split("/")[-1]] + (["pop=stack"] if POP == "stack" else []) + [quote(s)])

# ---------- 布局 / 路由 / 绘制 ----------
def layout(wins):
    out = []
    for w in wins:
        out += [b.moved(w.x, w.y, w.name) for b in w.view()]
    return out

def route(boxes, x, y):
    return next((b for b in reversed(boxes)
                 if b.id is not None and b.x <= x < b.x + b.w and b.y <= y < b.y + b.h), None)

def sgr(fg, bg):
    s = "\x1b[0m"
    if fg: s += "\x1b[38;2;%d;%d;%dm" % fg
    if bg: s += "\x1b[48;2;%d;%d;%dm" % bg
    return s

def covered(boxes, i):
    """boxes[i] 是否被更上层窗口的不透明 Box 压住(遮罩只能盖在字符背景之上, 压住就不能用遮罩, 退回字符背景)"""
    b = boxes[i]
    return any(c.win != b.win and c.bg and c.x < b.x + b.w and b.x < c.x + c.w and c.y < b.y + b.h and b.y < c.y + c.h
               for c in boxes[i + 1:])

_last = None            # 上一帧, 相同则不重复写出
def paint(boxes, snap=False):
    global _last
    cols, rows = size()
    keys, rects = {}, {}                                         # 交给图形协议的 Box: 动画 Box(遮罩) + 静态底色(仅 layered 终端会画)
    for i, b in enumerate(boxes):
        if b.bg and not (b.anim is not None and covered(boxes, i)):
            keys[i] = k = b.win if b.anim is not None else ("bg", i)   # 动画 Box 每窗口至多一个, 以窗口名为键
            rects[k] = (b.x, b.y, b.w, b.h, b.bg, i, b.anim)
    drawn, lay = gra.draw(rects, out, snap), gra.layered()       # 未被画的(无协议/非 layered 的底色)走字符背景色
    imaged = {i for i, k in keys.items() if k in drawn}
    g = [[[" ", None, None] for _ in range(cols)] for _ in range(rows)]
    def cell(x, y): return g[y][x] if 0 <= x < cols and 0 <= y < rows else None
    for i, b in enumerate(boxes):
        for y in range(b.y, b.y + b.h):
            for x in range(b.x, b.x + b.w):
                c = cell(x, y)
                if not c: continue
                if b.bg: c[0], c[2] = ((" ", None) if lay else (c[0], c[2])) if i in imaged else (" ", b.bg)
                if b.border:
                    top, bot = y == b.y, y == b.y + b.h - 1
                    left, right = x == b.x, x == b.x + b.w - 1
                    if (top or bot) and (left or right): c[0] = CORNER[(top, left)]
                    elif top or bot: c[0] = "━"
                    elif left or right: c[0] = "┃"
                    else: continue
                    c[1] = b.border
        col, fg = 0, b.fg
        if b.lit and (b.win not in drawn or gra.settled(b.win)): fg = b.lit   # 遮罩补间到位后才点亮文字
        for ch in b.text:
            wd = 2 if wide(ch) else 1
            if col + wd > b.w: break
            c = cell(b.x + col, b.y)
            if c: c[0], c[1] = ch, fg
            if wd == 2 and (c2 := cell(b.x + col + 1, b.y)): c2[0], c2[1] = "", fg   # 宽字符占的第二格
            col += wd
    buf = []
    for y, row in enumerate(g):
        buf.append("\x1b[%d;1H" % (y + 1)); cur = None
        for ch, fg, bg in row:
            if (fg, bg) != cur: buf.append(sgr(fg, bg)); cur = (fg, bg)
            buf.append(ch)
    frame = "".join(buf) + "\x1b[0m"
    if frame != _last: _last = frame; out(frame)

# ---------- 输入: 喂入终端原始字节流(tty 或 xterm.js 的 onData 完全同形), 切成按键/鼠标记号 ----------
KEYS = {"\x7f": "bs", "\x08": "bs", "\x17": "altbs", "\r": "enter", "\n": "enter"}
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}

def tail(s):
    """s 尾部若停在未写完的转义序列中, 返回该序列起点, 否则 len(s)(CLI 据此等一小会儿再喂入)"""
    p = s.rfind("\x1b[200~")
    if p > s.rfind("\x1b[201~"): return p                        # 粘贴未结束
    i = s.rfind("\x1b")
    if i < 0: return len(s)
    t = s[i + 1:]
    if not t: return i                                           # 孤立 ESC: 可能是 Esc, 也可能是序列前半
    if t[0] == "O": return i if len(t) < 2 else len(s)
    if t[0] in "]P_^X": return len(s) if t[0] == "]" and "\x07" in t else i   # 字符串序列: 终止符 ESC\ 本身就是最后一个 ESC
    if t[0] != "[": return len(s)
    for c in t[1:]:
        if not " " <= c <= "?": return len(s)                    # 终止字节(完整)或非法字节(序列已断开)
    return i

def tokens(s):
    """str -> 'up'/'enter'/'del'/'a'... 或 ('mouse', b, x, y, 'M'|'m') (SGR 鼠标 ESC[<b;x;yM, 坐标已转 0 起)
    或 ('paste', text) (括号粘贴 ESC[200~ ... ESC[201~)
    转义序列按 ECMA-48 整条吞掉: 不认识的(Home/F 键/焦点/终端应答/Alt+字符)直接忽略, 绝不当作 Esc 或文字泄漏;
    Alt-Bs -> 'altbs'; Delete(ESC[3~) -> 'del'; 只有孤立的 ESC 才是 'esc'; 格式错乱的序列在非法字节处截断, 后面的 Ctrl-C 照常生效"""
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c != "\x1b":
            yield KEYS.get(c, c); i += 1; continue
        if i + 1 >= n: yield "esc"; return
        k = s[i + 1]
        if k in "[O":
            j = i + 2
            while j < n and "0" <= s[j] <= "?": j += 1           # 参数字节
            while j < n and " " <= s[j] <= "/": j += 1           # 中间字节
            if j >= n: return                                    # 不完整: 丢弃
            f = s[j]
            if not "@" <= f <= "~": i = j; continue              # 非法终止字节: 从它重新解析
            body = s[i + 2:j]
            if k == "[" and body.startswith("<") and f in "Mm":
                p = body[1:].split(";")
                if len(p) == 3 and all(x.isdigit() for x in p):
                    yield ("mouse", int(p[0]), int(p[1]) - 1, int(p[2]) - 1, f)
            elif k == "[" and f == "~" and body == "200":
                e = s.find("\x1b[201~", j + 1)
                if e < 0: return                                 # 粘贴未结束: 丢弃
                yield ("paste", s[j + 1:e]); i = e + 6; continue
            elif k == "[" and f == "~" and body == "3": yield "del"
            elif f in ARROWS and all(x in "0123456789;" for x in body): yield ARROWS[f]
            i = j + 1
        elif k in "]P_^X":                                       # OSC/DCS/APC/PM/SOS: 吞到 ST(ESC\, OSC 也可 BEL)
            e1, e2 = s.find("\x1b\\", i + 2), (s.find("\x07", i + 2) if k == "]" else -1)
            if e1 < 0 and e2 < 0: return
            i = e2 + 1 if e2 >= 0 and (e1 < 0 or e2 < e1) else e1 + 2
        elif k in "\x7f\x08": yield "altbs"; i += 2
        elif k == "\x1b": yield "esc"; i += 1                    # ESC ESC: 先出一个 Esc, 后一个继续解析
        else: i += 2                                             # Alt+字符: 忽略

def set_curve(text):
    """粘贴的 linear(...) 换缓动曲线, 结果写到屏底"""
    global STATUS
    n = gra.set_curve(text)
    STATUS = "曲线解析失败(需要 CSS linear(...)): " + text.strip()[:60] if n is None else "曲线已更新: %d 个控制点" % n

def focus(wins, name):
    wins.sort(key=lambda w: w.name == name)      # 稳定排序: 目标窗口移到末尾

def pop_mode(args=()):
    for a in list(args) + ["pop=" + getattr(os, "environ", {}).get("pop", "")]:
        k, _, v = a.lstrip("$").partition("=")
        if k == "pop" and v in ("stack", "replace"): return v
    return "replace"

class Session:
    """窗口栈(末尾=最上层/焦点) + 拖拽/按下状态; feed() 把输入记号翻译成窗口事件。窗口全部由 open_root/open_path 创建"""
    def __init__(self, tree, onblur, quit="\x03"):
        self.tree, self.onblur, self.quit = tree, onblur, quit
        self.wins = []
        self.drag = None         # (win, 抓取点相对窗口的 dx, dy): 拖拽中, 不做路由
        self.press = None        # (win, id, x, y, 时刻): 项上按下后尚未判定是点击还是拖拽
        self.dirty = False       # 本次 feed 是否需要重绘

    def open_root(self, x, y, explicit=True):
        """在 (x, y) 开一个根菜单窗口并置顶, 返回它; explicit=False 时若其锚点已有记忆位置(REMEMBER)则用记忆位置"""
        w = Menu(self.tree, [], 0, uid(), (x, y), explicit=explicit)
        self.wins.append(w)
        return w

    def open_path(self, s):
        """按路径逐级展开并选中(无窗口时先开一个根); 找不到则在屏底提示"""
        global STATUS
        idxs = resolve(self.tree, s)
        if idxs is None: STATUS = "路径未找到: " + s
        if not self.wins: self.open_root(4, 2, explicit=False)
        for i in idxs or []:
            layout(self.wins)                                    # 先跑一遍 view, 让窗口尺寸/滚动就位
            w = self.wins[-1]; w.sel = (i,)
            act(self.wins, w, ("open", (i,)))

    def render(self):
        cols, rows = size()
        boxes = layout(self.wins)
        if STATUS: boxes.append(Box(1, rows - 1, cols - 2, 1, text="$ " + STATUS, fg=DIM))
        paint(boxes, self.drag is not None)

    def dispatch(self, w, kind, arg):
        return act(self.wins, w, w.event(kind, arg))

    def paste(self, text):
        """linear(...) 换动画曲线, 其余当作输入"""
        if text.lstrip().lower().startswith("linear("): set_curve(text)
        else:
            for ch in text:
                if printable(ch): self.dispatch(self.wins[-1], "key", ch)
        self.dirty = True

    def start_drag(self, x, y):
        """按住项后移动: 停留 >=DRAG_DELAY 才算拖拽, 之前是抖动。返回是否已进入拖拽"""
        w, _, px, py, t = self.press
        if (x, y) == (px, py) or time.time() - t < DRAG_DELAY: return False
        self.drag, self.press = (w, px - w.x, py - w.y), None
        return True

    def drag_to(self, b, x, y):
        w, dx, dy = self.drag
        self.dirty = True
        if b == 32: w.move(x - dx, y - dy)
        else:                                                    # 松开(或松开事件丢失后的无键移动)
            w.remember()
            self.drag = None

    def press_down(self, w, hit, x, y):
        drop_deeper(self.wins, w); focus(self.wins, w.name)      # 关闭更深的窗口, 取得焦点
        if hit.id == ("title",): self.drag = (w, x - w.x, y - w.y)
        if hit.id[0] != "item": return w, "click", hit.id
        self.press = (w, hit.id, x, y, time.time())
        return w, "hover", hit.id

    def release(self, x, y):
        """项上的按下: 原地松开才是点击"""
        w, pid = self.press[:2]; self.press = None
        hit = route(layout(self.wins), x, y)
        if w in self.wins and hit and hit.id == pid and hit.win == w.name: return w, "click", pid

    def mouse(self, b, x, y, kind):
        """b=按钮码, kind='M' 按下/移动 | 'm' 松开。返回要派发的 (窗口, 事件, 参数) 或 None"""
        if self.press and b == 32 and not self.start_drag(x, y): return
        if self.drag: return self.drag_to(b, x, y)
        if self.press and kind == "m" and b == 0: return self.release(x, y)
        self.press = None
        hit = route(layout(self.wins), x, y)
        if not hit:
            if b == 0 and kind == "M": self.onblur(x, y, self.open_root); self.dirty = True
            return
        w = next(w for w in self.wins if w.name == hit.win)
        if b & 64: return w, "key", "up" if b == 64 else "down"
        if b == 0 and kind == "M": return self.press_down(w, hit, x, y)
        if b == 35 and hit.id[0] == "item" and w.sel != hit.id[1]: return w, "hover", hit.id

    def feed(self, data):
        """True 表示该退出了(按下 quit 键或已无窗口)"""
        self.dirty = False
        for t in tokens(data):
            if not self.wins or t == self.quit: return True
            if not isinstance(t, tuple): ev = (self.wins[-1], "key", t)
            elif t[0] == "paste": self.paste(t[1]); continue
            else: ev = self.mouse(*t[1:])
            if ev:
                self.dirty = True
                if self.dispatch(*ev): return True
        if self.dirty: self.render()

def start(sexp, onpath=show_cmd, rempos="label_rt|rd", onblur=None, args=(), root=True, quit="\x03"):
    """事件驱动核心(无阻塞、无 tty)。写出 ENTER, 开初始窗口并首绘, 返回 Session:
       s.feed(text) -> True 表示该退出了(按下 quit 键, 或已无窗口); s.render() 按当前尺寸重绘; gra.animating() 为真时宿主应 ~60fps 调 render
       s.open_root(x, y) / s.open_path('Learn/Arch') 脚本化开窗口; w.move(x, y) + w.remember() 记住位置
       root=False 不开初始窗口(由脚本自己开); quit=None 不把 Ctrl-C 当退出键(退出完全由宿主决定)"""
    global POP, REMPOS, ONPATH, _last
    POP, REMPOS, ONPATH, _last = pop_mode(args), rempos, onpath, None
    s = Session(parse(sexp), onblur or (lambda x, y, open: open(x, y)), quit)
    out(ENTER)
    if root: s.open_root(4, 2, explicit=False)
    arg1 = next((a for a in args if "=" not in a), "")
    if arg1: s.open_path(arg1)                                   # 按 arg1 展开路径并选中
    s.render()
    return s

def prompt(sexp, onpath=show_cmd, rempos="label_rt|rd", onblur=None):
    """CLI 驱动(只是 start() 的一个主循环): raw 模式下把 stdin 读到的字节喂给 feed; 动画进行中以 ~60fps 调 render()"""
    import termios, tty, select, codecs
    fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
    dec = codecs.getincrementaldecoder("utf8")("ignore")
    def read():
        b = os.read(fd, 4096)
        if not b: raise EOFError
        return dec.decode(b)
    try:
        tty.setraw(fd)
        s = start(sexp, onpath, rempos, onblur, sys.argv[1:])
        while True:
            if not select.select([fd], [], [], 1 / 60 if gra.animating() else None)[0]: s.render(); continue
            data = read()
            while tail(data) < len(data) and select.select([fd], [], [], 0.05)[0]: data += read()   # 序列被拆成多次 read
            if s.feed(data): break
    except EOFError: pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old); gra.draw({}, out); out(LEAVE)

def main():
    tree, note = load_tree()
    try: prompt(tree)
    finally:
        if note: print(note, file=sys.stderr)

if __name__ == "__main__":
    main()
