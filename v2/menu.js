#!/usr/bin/env node
// Omarchy 风格 Go… 菜单 (menu.py 的 JS 版)。同一份代码跑 Node(CLI) 与浏览器(xterm.js)。
//
// 用法: node menu.js [Learn/Arch] [pop=stack|replace]     arg1=启动时展开并选中的路径; pop 也可用环境变量
// 键鼠与 menu.py 相同: 输入即搜索 ↑↓ →/Enter ←/Esc/Bs Del Alt-Bs/Ctrl-W 滚轮 拖拽; Ctrl-C 退出; Ctrl-V 粘贴 linear(...) 换动画曲线
//
// 数据流: 终端字节 --TextDecoder--> tokens() --> Session.feed 派发到 Menu.event --> layout() 得到 Box 列表(唯一的视图)
//         --> 同一份 Box 列表: route() 命中测试 / paint() 文字帧 / rects() 交给 gra.py 补间成图像遮罩
// 图形: 补间和终端图像全在 gra.py 子进程里(Node 没有 TIOCGWINSZ 取像素格)。两边只靠 stdio 行协议同步, 首词查字典(见 FROM_PY 与 gra.py CMD)。
//       没有 gra.py(浏览器 / 无 python3 / 终端无协议)时退回字符背景色。

/** 可调参数(尺寸单位 = 字符格; index.html 的 lil-gui 面板直接绑这个对象; 命令行/URL 参数 cfg.<键>=值) */
export const CFG = {
  itemH: 3, dragDelay: 100,                       // 菜单项高度(只管菜单; 对话框按钮用 btnH) / 按下后停留多久才算拖拽(ms)
  menuMinW: 32, dialogMinW: 20,                   // 窗口最小宽度
  btnH: 1, itemMinW: 8, gap: 1, fadeX: 2,         // 对话框按钮: 高度(行, 必须是奇数: 文字落在正中那行) / 最小宽度 / 间距(横向纵向都有效) / 底色两端渐隐列数(opts.fadeX 缺省值)
  dur: 180,                                       // gra.py 补间时长(ms)
  kbdRows: 5, kbdBottom: 3,                       // inlineKbd: 最多显示几行(窄高度) / 窗口底边离屏底几行(留给输入框)
  pop: "replace",                                 // 子菜单: replace 原地替换 | stack 叠放
  rempos: "",                                     // 窗口第一次出现(同 id 没被拖拽过)放哪个屏角: rt rd lt ld; 空 = 各窗口自己的默认位置。"<id>_rt|rd" = id 为 <id> 的窗口放右上, 其余放右下
};
let ONPATH = null, STATUS = "", LAST = null, SEQ = 0, SESSION = null;
const REMEMBER = new Map();                       // 窗口 id -> [屏角, dx, dy]: 上次拖拽后窗口相对该屏角的偏移; 同 id 的新窗口放回这里
const uid = () => ++SEQ;
const DEFAULT_TREE = ["Go", ["\uf00a  Apps"], ["\uf19d  Learn"], ["\uf135  Trigger"], ["Style"], ["Setup"], ["About"], ["System"]];

// ---------- 终端 I/O: 核心只经由 io 接触终端 ----------
export const io = { size: () => [80, 24], out: () => {} };
export const ENTER = "\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1003h\x1b[?1006h\x1b[?2004h";
export const LEAVE = "\x1b[0m\x1b[?2004l\x1b[?1006l\x1b[?1003l\x1b[?1000l\x1b[?25h\x1b[?1049l";

function parse(a) {
  if (!(Array.isArray(a) && a.length && typeof a[0] === "string")) throw new Error("bad node: " + JSON.stringify(a).slice(0, 40));
  const i = a[0].indexOf("  "), [icon, name] = i < 0 ? ["", a[0]] : [a[0].slice(0, i), a[0].slice(i + 2)];
  return { icon, name: name.trim(), kids: a.slice(1).map(parse) };
}

/** get() 返回(或 resolve 出) tree.json 文本; 任何失败回滚内置菜单。-> [sexp, 失败说明|null] */
export async function loadTree(get) {
  try { const raw = JSON.parse(await get()); parse(raw); return [raw, null]; }
  catch (e) { return [DEFAULT_TREE, "tree.json 加载失败, 使用内置菜单: " + e.message]; }
}

const THEME = {
  bg: [2, 11, 20], border: [26, 77, 26], text: [207, 232, 245], dim: [106, 138, 160], selBg: [8, 32, 22], selFg: [31, 140, 31],
  btnBg: [12, 28, 42], snackBg: [31, 140, 31], snackFg: [2, 11, 20],
  fadeBg: null,                                   // 按钮底色两端渐隐到的颜色; null = 跟随窗口底色 bg
  glyph: { check: ["\u{F0131}", "\u{F0132}"], radio: ["\u{F043D}", "\u{F043E}"] },   // [关, 开]: Nerd Font md-checkbox-* / md-radiobox-*
};
const rgb = v => {
  const m = Array.isArray(v) ? v : /^#?([0-9a-f]{6})$/i.exec(String(v))?.[1].match(/../g).map(h => parseInt(h, 16));
  if (!(m?.length === 3 && m.every(n => Number.isInteger(n) && n >= 0 && n <= 255))) throw new Error("bad color: " + v);
  return m;
};
/** 颜色可调: { bg, border, text, dim, selBg, selFg, btnBg, snackBg, snackFg, fadeBg: '#rrggbb' | [r,g,b](fadeBg 可为 null = 跟随 bg), glyph: { check: [关,开], radio: [关,开] } } */
export function setTheme(o = {}) {
  for (const [k, v] of Object.entries(o)) {
    if (k === "glyph") Object.assign(THEME.glyph, v);
    else if (k in THEME) THEME[k] = k === "fadeBg" && v == null ? null : rgb(v);
    else throw new Error("unknown theme key: " + k);
  }
}
/** 当前主题的颜色键 -> '#rrggbb'(调参面板用); glyph 直接返回对象 */
export const themeHex = () => Object.fromEntries(Object.entries(THEME).filter(([k]) => k !== "glyph").map(([k, v]) => [k, "#" + hex(v ?? THEME.bg)]));
export const themeGlyph = () => THEME.glyph;

const box = (x, y, w, h, o = {}) => ({ x, y, w, h, id: null, ip: null, bg: null, fg: null, text: "", border: null, win: null, anim: false, lit: null, fade: 0, ...o });
// id 非 null 才参与路由; ip: 项的下标路径; bg 非 null 则不透明; win: layout 时填入所属窗口;
// anim: 有图形协议时该 Box 的 bg 画成补间遮罩(每窗口至多一个); lit: 同窗口遮罩到位后文字才换成这个颜色
// fade: bg 的左右两端共 fade 列向 THEME.fadeBg 渐隐(字符背景色路径; 补间遮罩是硬边矩形)

// ---------- 文字宽度: JS 字符串是 UTF-16, Nerd Font 图标在补充平面, 一律按 code point 处理 ----------
const WIDE = [[0x1100, 0x115F], [0x2E80, 0xA4CF], [0xAC00, 0xD7A3], [0xF900, 0xFAFF], [0xFE30, 0xFE6F], [0xFF00, 0xFF60],
              [0xFFE0, 0xFFE6], [0x1F300, 0x1F64F], [0x1F7E0, 0x1F7EB], [0x1F900, 0x1F9FF], [0x20000, 0x3FFFD]];   // 东亚宽 + emoji
const wide = c => { const o = c.codePointAt(0); return o >= 0x1100 && WIDE.some(([a, b]) => a <= o && o <= b); };
const cw = t => [...t].reduce((n, c) => n + (wide(c) ? 2 : 1), 0);
const dropLast = q => [...q].slice(0, -1).join("");
const dropWord = q => { const a = [...q.replace(/ +$/, "")]; while (a.length && !" /".includes(a.at(-1))) a.pop(); return a.join(""); };
const printable = k => [...k].length === 1 && k >= " " && k !== "\x7f";

// ---------- 菜单树 ----------
const same = (a, b) => a.join() === b.join();
const has = (idx, ip) => idx.some(p => same(p, ip));
const at = (node, ip) => ip.reduce((n, i) => n.kids[i], node);
const names = (node, ip) => ip.map((_, n) => at(node, ip.slice(0, n + 1)).name);     // 沿路径各级的名字
const trail = (node, ip) => names(node, ip).slice(0, -1);                            // 不含自身的祖先名

/** 深搜 node 之下名字含 q 的项(浅层优先); q 为空或以 './' 开头则只看当前层。返回下标路径数组 */
function matches(node, q) {
  q = q.toLowerCase();
  const local = !q || q.startsWith("./"), out = [];
  if (q.startsWith("./")) q = q.slice(2);
  const walk = (n, ip) => n.kids.forEach((k, i) => {
    if (k.name.toLowerCase().includes(q)) out.push([...ip, i]);
    if (!local) walk(k, [...ip, i]);
  });
  walk(node, []);
  return out.sort((a, b) => a.length - b.length);
}
const maxVis = () => Math.max(3, Math.floor((io.size()[1] - 7) / CFG.itemH));
const height = n => 5 + Math.max(Math.min(n, maxVis()), 1) * CFG.itemH;
const rowY = pos => 4 + pos * CFG.itemH;                                             // 第 pos 个可见项在窗口内的 y
const itemLabel = k => (k.icon ? k.icon + "  " : "") + k.name;
const menuW = node => Math.max(CFG.menuMinW, Math.max(0, ...node.kids.map(k => cw(itemLabel(k)))) + 9);

/** 'Learn/Arch' -> [kid 下标...]; 名字自带 '/' 时回溯匹配, 忽略大小写; 失败 null */
function resolve(node, s) {
  if (!s) return [];
  const l = s.toLowerCase();
  for (const [i, k] of node.kids.entries()) {
    const n = k.name.toLowerCase();
    if (l === n) return [i];
    if (l.startsWith(n + "/")) { const r = resolve(k, s.slice(n.length + 1)); if (r) return [i, ...r]; }
  }
  return null;
}

// ---------- 菜单窗口 ----------
const cornerAt = c => { const [cols, rows] = io.size(); return [c[0] === "r" ? cols : 0, c[1] === "d" ? rows : 0]; };   // 屏角的坐标

/** CFG.rempos = "[<id>_]<屏角>|..." 里第一个适用于窗口 id 的屏角, 没有返回 null。
 *  <id> 是窗口 id(菜单 = 打开它的那一项的名字, 根菜单 = 树名, 对话框 = 标题), 不写 = 所有窗口 */
function spot(id) {
  for (const e of CFG.rempos.split("|")) {
    const m = /^(?:(.+)_)?(lt|ld|rt|rd)$/.exec(e.trim());
    if (m && (m[1] === undefined || m[1] === id)) return m[2];
  }
  return null;
}

const EDIT = { esc: () => "", bs: dropLast, altbs: dropWord };   // 搜索串为空时, 编辑键变成"返回"

/** 窗口基类: 几何 x y w h; view() -> [Box] 局部坐标, event() 处理输入 */
class Win {
  move(x, y) {                                     // 放到 (x, y), 夹在终端范围内
    const [cols, rows] = io.size();
    this.x = Math.max(0, Math.min(x, cols - this.w)); this.y = Math.max(0, Math.min(y, rows - this.h));
  }
  /** 第一次摆放: 同 id 拖拽过 -> 放回那里; 否则 rempos 给了屏角 -> 放屏角; 都没有 -> xy(窗口自己的默认位置)。explicit 只用 xy */
  place(xy, explicit = false) {
    const mem = explicit ? null : REMEMBER.get(this.id), c = explicit ? null : spot(this.id);
    if (mem) { const [ax, ay] = cornerAt(mem[0]); this.move(ax + mem[1], ay + mem[2]); }
    else if (c) { const [ax, ay] = cornerAt(c); this.move(ax - (c[0] === "r" ? this.w : 0), ay - (c[1] === "d" ? this.h : 0)); }
    else this.move(...xy);
  }
  remember() {                                     // 记住本窗口相对屏角的偏移(屏角 = rempos 给的, 没有取左上)
    const c = spot(this.id) ?? "lt", [ax, ay] = cornerAt(c);
    REMEMBER.set(this.id, [c, this.x - ax, this.y - ay]);
  }
}
const DEFAULT_CB = { onpath: s => ONPATH(s) };      // 菜单回调: onpath(每次打开一项) onleaf(叶子; 有则选中即关闭整串窗口) onend(整串窗口都没了)

/** 一个菜单窗口: 几何 + 状态; view() -> [Box] 局部坐标, event() 返回 undefined | 'close' | ['open', 项路径] */
class Menu extends Win {
  /** xy=默认位置; id=窗口 id(缺省取树名), 见 Win.place; altX: 右侧放不下时翻到其左边 */
  constructor(node, path, depth, chain, xy, { id, altX, explicit = false, parent, cb } = {}) {
    super();
    const [cols] = io.size();
    Object.assign(this, { id: id ?? node.name, node, path, depth, chain, parent, cb: cb ?? parent?.cb ?? DEFAULT_CB, sel: [0], q: "", top: 0, name: "m" + uid() });
    this.w = menuW(node);
    this.h = height(node.kids.length);
    this.place(altX != null && xy[0] + this.w > cols ? [altX - this.w, xy[1]] : xy, explicit);
  }

  hits() { return matches(this.node, this.q); }

  view() {
    const W = (this.w = menuW(this.node)), q = this.q, idx = this.hits(), vis = maxVis(), n = idx.findIndex(p => same(p, this.sel));
    if (n >= 0) this.top = Math.min(Math.max(this.top, n - vis + 1), n);
    this.top = Math.max(0, Math.min(this.top, idx.length - vis));
    this.h = height(idx.length);
    const bs = [box(0, 0, W, this.h, { id: "win", bg: THEME.bg, border: THEME.border }),
                box(1, 1, W - 2, 3, { id: "title" }),
                box(3, 2, W - 6, 1, { text: q ? q + "▏" : this.node.name + "…", fg: q ? THEME.text : THEME.dim })];
    if (this.top > 0) bs.push(box(W - 6, 2, 1, 1, { text: "▲", fg: THEME.dim }));
    if (this.top + vis < idx.length) bs.push(box(W - 4, 2, 1, 1, { text: "▼", fg: THEME.dim }));
    if (!idx.length) bs.push(box(3, 5, W - 6, 1, { text: "No matches", fg: THEME.dim }));
    idx.slice(this.top, this.top + vis).forEach((ip, pos) => {
      const k = at(this.node, ip), y = rowY(pos), ty = y + (CFG.itemH >> 1), on = same(ip, this.sel), label = itemLabel(k);
      bs.push(box(1, y, W - 2, CFG.itemH, { id: "item:" + ip.join("."), ip, bg: on ? THEME.selBg : THEME.bg, anim: on }));
      bs.push(box(3, ty, W - 8, 1, { text: label, fg: THEME.text, lit: hl(on) }));   // 选中行文字: 遮罩到位后才点亮(focusHL = '' 且有 gra.py 时不点亮)
      if (ip.length > 1) {                                       // 深搜结果: 名字后淡色显示所在路径
        const tx = 3 + cw(label) + 2;
        bs.push(box(tx, ty, W - 6 - tx, 1, { text: "‹ " + trail(this.node, ip).join("/"), fg: THEME.dim }));
      }
      if (k.kids.length) bs.push(box(W - 5, ty, 1, 1, { text: "›", fg: THEME.dim, lit: hl(on) }));
    });
    return bs;
  }

  event(kind, arg) {                               // arg: 按键名 | 命中的 Box
    if (kind === "key") return this.key(arg);
    if (arg.ip) { this.sel = arg.ip; if (kind === "click") return ["open", arg.ip]; }   // hover / click
  }

  key(k) {
    let idx = this.hits();
    if (k === "up" || k === "down") {
      if (idx.length) {
        const n = Math.max(0, idx.findIndex(p => same(p, this.sel)));
        this.sel = idx[(n + (k === "down" ? 1 : -1) + idx.length) % idx.length];
      }
    } else if (k === "right" || k === "enter") { if (has(idx, this.sel)) return ["open", this.sel]; }
    else if (k === "left") return "close";
    else if (k === "del") this.q = "";
    else if (Object.hasOwn(EDIT, k)) { if (!this.q) return "close"; this.q = EDIT[k](this.q); }
    else if (printable(k)) this.q += k;
    idx = this.hits();
    if (idx.length && !has(idx, this.sel)) this.sel = idx[0];
  }
}

// ---------- 对话框窗口: 只认线上协议的 KV 表(title / body / footer 是文字, 其余键是按钮), 状态在宿主(pi.js)里 ----------
const TEXTK = new Set(["title", "body", "footer"]);
const MARKS = [[/^\[([ xX])\]\s+/, "check", m => m[1] !== " "], [/^\(([ *•xX])\)\s+/, "radio", m => m[1] !== " "],
               [/^[○◯]\s+/, "radio", () => false], [/^[●◉]\s+/, "radio", () => true]];

/** 按钮文字开头的勾选/单选语法 `[ ]` `[x]` `( )` `(*)` `○` `●` -> { kind: 'check'|'radio', on, text }; 没有返回 null */
export function mark(label) {
  for (const [re, kind, on] of MARKS) { const m = re.exec(label); if (m) return { kind, on: on(m), text: label.slice(m[0].length) }; }
  return null;
}

const mix = (to, c, f) => c.map((v, i) => Math.round(to[i] + (v - to[i]) * f));   // f = 1 -> c, f = 0 -> to
const fadeBg = (b, x) => {
  const l = Math.ceil(b.fade / 2), r = b.fade >> 1, i = x - b.x, j = b.x + b.w - 1 - x;
  const f = Math.min(i < l ? (i + 1) / (l + 1) : 1, j < r ? (j + 1) / (r + 1) : 1);
  return f < 1 ? mix(THEME.fadeBg ?? THEME.bg, b.bg, f) : b.bg;
};
/** 选中项文字的强调色(pi.arg.focusHL): '' 且 gra.py 生效(有补间遮罩可看出焦点)时不用, 否则只靠这个颜色 */
const hl = on => on && (!!SESSION?.arg.focusHL || !gfx.on()) ? THEME.selFg : null;

/** wire = { press(id, key|null), active(id, key) } 向宿主回报; arg = pi.arg(focusHL: 'color' 文字用强调色, '' 不用 —— 只在 gra.py 生效时才关, 补间遮罩(动效)一直在); opts = { timeout, or, eachRow, fadeX }
 *  有 timeout = 非模态: 放右上角, 正文末尾附 "(Ns)" 倒计时, 到点按下 or(没有 or 则 key null); 第一次交互(按键/鼠标)就取消自动选择, 倒计时也撤掉 */
class Dialog extends Win {
  constructor(did, kv, opts, n, wire, arg) {
    super();
    Object.assign(this, { did, wire, arg, opts, kv: new Map(Object.entries(kv)), id: kv.title || "dialog", name: "d" + uid(), chain: uid(), depth: 0, x: 0, y: 0, shown: -1,
                          deadline: opts.timeout ? Date.now() + opts.timeout : 0 });
    this.sel = [Math.max(0, this.items().findIndex(([k]) => k === opts.or))];
    this.fit();
    const [cols, rows] = io.size();
    this.place(opts.timeout ? [cols - this.w - 1, 1] : [((cols - this.w) >> 1) + n * 2, ((rows - this.h) >> 1) + n]);   // 堆叠: 每层错开, 露出下面一层的边
  }

  items() { return [...this.kv].filter(([k]) => !TEXTK.has(k)); }
  keyOf(i) { return this.items()[i]?.[0] ?? null; }
  cancelAuto() { this.deadline = 0; }

  patch(kv) {
    for (const [k, v] of Object.entries(kv)) v === null ? this.kv.delete(k) : this.kv.set(k, v);
    this.sel = [Math.min(this.sel[0], Math.max(0, this.items().length - 1))];
    this.fit();
  }

  fit() { const g = this.geom(); this.w = g.W; this.h = g.H; this.move(this.x, this.y); }

  /** 布局: 各段(标题/正文/按钮/文字)之间空一行; 按钮按 eachRow 分行, 列宽取各行同列最大值(列对齐) */
  geom() {
    const [cols] = io.size(), get = k => this.kv.get(k) || "", per = this.opts.eachRow;
    const title = get("title"), footer = get("footer"), body = get("body") ? get("body").split("\n") : [];
    if (this.deadline) {
      this.shown = Math.max(0, Math.ceil((this.deadline - Date.now()) / 1000));
      const tag = `(${this.shown}s)`;
      if (body.length) body[body.length - 1] += " " + tag; else body.push(tag);
    }
    const cells = this.items().map(([key, label], i) => { const mk = mark(label); return { i, key, label, mk, lw: mk ? 2 + cw(mk.text) : cw(label) }; });
    const sizes = per === "vertical" ? [1] : Array.isArray(per) && per.length ? per : [Math.max(1, cells.length)];
    const grid = [], colW = [];
    for (let i = 0, r = 0; i < cells.length; r++) { const n = Math.max(1, sizes[Math.min(r, sizes.length - 1)]); grid.push(cells.slice(i, i + n)); i += n; }
    const btnH = CFG.btnH | 1, vert = per === "vertical";                                 // btnH 必须是奇数, 偶数向上取奇
    grid.forEach(row => row.forEach((c, j) => { colW[j] = Math.max(colW[j] ?? 0, c.lw + 2); }));   // 左右至少各留 1 列
    colW.forEach((w, j) => { colW[j] = Math.max(CFG.itemMinW, w); });                      // 再撑到最小宽度
    const rowW = Math.max(0, ...grid.map(row => row.reduce((s, _, j) => s + colW[j] + CFG.gap, -CFG.gap)));
    const W = Math.min(Math.max(CFG.dialogMinW, cw(title), cw(footer), rowW, ...body.map(cw)) + 6, cols), L = {};
    let y = 2;
    if (title) { L.title = y; y += 2; }
    if (body.length) { L.body = y; y += body.length + 1; }
    if (grid.length) { L.btn = y; y += grid.length * btnH + (grid.length - 1) * CFG.gap + 1; }
    if (footer) { L.footer = y; y += 2; }
    return { W, H: y + 1, title, body, footer, grid, colW, L, btnH, vert };
  }

  view() {
    const { W, H, title, body, footer, grid, colW, L, btnH, vert } = this.geom(), fade = this.opts.fadeX ?? CFG.fadeX;
    this.w = W; this.h = H;
    const bs = [box(0, 0, W, H, { id: "win", bg: THEME.bg, border: THEME.border }), box(1, 1, W - 2, title ? 3 : 1, { id: "title" })];
    if (title) bs.push(box(3, L.title, W - 6, 1, { text: title, fg: THEME.selFg }));
    body.forEach((t, i) => bs.push(box(3, L.body + i, W - 6, 1, { text: t, fg: THEME.text })));
    grid.forEach((row, r) => {
      let x = 3;
      row.forEach((c, j) => {
        const on = c.i === this.sel[0], y = L.btn + r * (btnH + CFG.gap), ty = y + (btnH >> 1);
        const ox = vert ? 1 : (colW[j] - c.lw) >> 1;              // 竖排列表左对齐(图标同列), 横排按钮居中
        const lit = hl(on);
        bs.push(box(x, y, colW[j], btnH, { id: "btn:" + c.i, ip: [c.i], bg: on ? THEME.selBg : THEME.btnBg, anim: on, fade }));
        if (c.mk) {                                              // 勾选/单选: Omarchy 图标 + 文字; 开 = 强调色, 关 = 暗色
          bs.push(box(x + ox, ty, 1, 1, { text: THEME.glyph[c.mk.kind][+c.mk.on], fg: c.mk.on ? THEME.selFg : THEME.dim, lit }));
          bs.push(box(x + ox + 2, ty, colW[j] - ox - 3, 1, { text: c.mk.text, fg: THEME.text, lit }));
        } else bs.push(box(x + ox, ty, colW[j] - ox - 1, 1, { text: c.label, fg: THEME.text, lit }));
        x += colW[j] + CFG.gap;
      });
    });
    if (footer) bs.push(box(3, L.footer, W - 6, 1, { text: footer, fg: THEME.dim }));
    return bs;
  }

  go(i) {
    if (i === this.sel[0]) return;
    this.sel = [i];
    this.wire.active(this.did, this.keyOf(i));
  }

  event(kind, arg) {                               // 结果一律经 wire 回报宿主; 关窗由宿主发 close
    this.cancelAuto();
    if (kind === "key") return this.key(arg);
    if (!arg.ip) return;
    this.go(arg.ip[0]);
    if (kind === "click") this.wire.press(this.did, this.keyOf(arg.ip[0]));
  }

  key(k) {
    const n = this.items().length;
    if (k === "esc") return this.wire.press(this.did, null);
    if (!n) return;
    let i = this.sel[0];
    if (k === "enter") return this.wire.press(this.did, this.keyOf(i));
    if (k === "right" || k === "\t") i = (i + 1) % n;
    else if (k === "left" || k === "btab") i = (i + n - 1) % n;
    else if (k === "up" || k === "down") {                       // 换行保持列; 该行没有这一列则取行尾
      const { grid } = this.geom(), r = grid.findIndex(row => row.some(c => c.i === i)), c = grid[r].findIndex(c => c.i === i);
      const row = grid[(r + (k === "down" ? 1 : grid.length - 1)) % grid.length];
      i = row[Math.min(c, row.length - 1)].i;
    } else return;
    this.go(i);
  }

  /** 返回 true = 需要重绘(倒计时数字变了, 或到点按下了) */
  tick(now) {
    if (!this.deadline) return false;
    if (now >= this.deadline) {
      this.deadline = 0;
      this.wire.press(this.did, this.opts.or ?? null);
      return true;
    }
    return Math.max(0, Math.ceil((this.deadline - now) / 1000)) !== this.shown;
  }
}

/** inlineKbd: 输入框上方的窄下拉(fzf 式 Tab 补齐)。打字过滤(子序列匹配), ↑ ↓ Tab Shift-Tab 选择, Enter 确认, Esc 取消; 最多 CFG.kbdRows 行, 超出滚动。
 *  结果经 wire.press(did, 选中项 | null) 回报, 关窗由宿主发 close(同对话框) */
class Kbd extends Win {
  constructor(did, items, wire) {
    super();
    Object.assign(this, { did, wire, id: "kbd", items, q: "", top: 0, sel: [0], name: "k" + uid(), chain: uid(), depth: 0, x: 0, y: 0, w: 0, h: 0 });
    this.view();
  }

  hits() {                                         // 匹配的项下标: 前缀匹配排前面, 其余保持原序
    const q = this.q.toLowerCase(), sub = s => { let i = 0; for (const c of s.toLowerCase()) if (c === q[i]) i++; return i === q.length; };
    return this.items.flatMap((s, i) => sub(s) ? [i] : []).sort((a, b) => !this.items[a].toLowerCase().startsWith(q) - !this.items[b].toLowerCase().startsWith(q));
  }

  view() {
    const [cols, rows] = io.size(), idx = this.hits(), vis = Math.max(1, Math.min(CFG.kbdRows, idx.length)), n = idx.indexOf(this.sel[0]);
    if (n >= 0) this.top = Math.min(Math.max(this.top, n - vis + 1), n);
    this.top = Math.max(0, Math.min(this.top, idx.length - vis));
    const W = this.w = Math.min(cols, Math.max(16, ...this.items.map(cw)) + 6), H = this.h = vis + 3;
    this.move(1, rows - CFG.kbdBottom - H);
    const bs = [box(0, 0, W, H, { id: "win", bg: THEME.bg, border: THEME.border }),
                box(2, H - 2, W - 4, 1, { text: "> " + this.q + "▏", fg: this.q ? THEME.text : THEME.dim }),
                box(W - 8, H - 2, 6, 1, { text: `${idx.length}/${this.items.length}`.padStart(6), fg: THEME.dim })];
    if (!idx.length) bs.push(box(2, 1, W - 4, 1, { text: "No matches", fg: THEME.dim }));
    idx.slice(this.top, this.top + vis).forEach((i, pos) => {
      const on = i === this.sel[0];
      bs.push(box(1, 1 + pos, W - 2, 1, { id: "item:" + i, ip: [i], bg: on ? THEME.selBg : THEME.bg, anim: on }));
      bs.push(box(2, 1 + pos, W - 4, 1, { text: this.items[i], fg: THEME.text, lit: hl(on) }));
    });
    return bs;
  }

  event(kind, arg) {
    if (kind === "key") return this.key(arg);
    if (!arg.ip) return;
    this.sel = arg.ip;
    if (kind === "click") this.wire.press(this.did, this.items[arg.ip[0]]);
  }

  key(k) {
    let idx = this.hits();
    if (k === "esc") return this.wire.press(this.did, null);
    if (k === "enter") { if (idx.includes(this.sel[0])) this.wire.press(this.did, this.items[this.sel[0]]); return; }
    if (k === "up" || k === "btab" || k === "down" || k === "\t") {
      if (idx.length) this.sel = [idx[(Math.max(0, idx.indexOf(this.sel[0])) + (k === "up" || k === "btab" ? idx.length - 1 : 1)) % idx.length]];
      return;
    }
    if (k === "del") this.q = "";
    else if (k === "bs") this.q = dropLast(this.q);
    else if (k === "altbs") this.q = dropWord(this.q);
    else if (printable(k)) this.q += k;
    else return;
    idx = this.hits();
    if (!idx.includes(this.sel[0])) this.sel = [idx[0] ?? -1];
    this.top = 0;
  }
}

const keep = (a, f) => a.splice(0, a.length, ...a.filter(f));
const dropDeeper = (wins, w) => keep(wins, x => x.chain !== w.chain || x.depth <= w.depth);

/** replace 模式下回到父窗口(放在当前位置), 否则关掉自己及更深的窗口。返回 true 表示已无窗口 */
function closeMenu(wins, w) {
  if (w.depth && CFG.pop === "replace" && w.parent) { w.parent.move(w.x, w.y); wins[wins.indexOf(w)] = w.parent; }
  else { keep(wins, x => x.chain !== w.chain || x.depth < w.depth); return !wins.length; }
}

function openItem(wins, w, ip) {
  const kid = at(w.node, ip), path = [...w.path, ...names(w.node, ip)], full = path.join("/");
  try { w.cb.onpath?.(full); } catch {}
  dropDeeper(wins, w);
  if (!kid.kids.length) {
    if (w.cb.onleaf) { keep(wins, x => x.chain !== w.chain); try { w.cb.onleaf(full); } catch {} }   // 叶子: 先关整串窗口再通知
    return;
  }
  const y = w.y + rowY(w.hits().findIndex(p => same(p, ip)) - w.top);
  const c = new Menu(kid, path, w.depth + 1, w.chain, [w.x + w.w, y], { id: kid.name, altX: w.x, parent: w });
  if (CFG.pop === "replace") { c.move(w.x, w.y); wins[wins.indexOf(w)] = c; }
  else wins.push(c);
}

/** 处理 Menu.event 的结果(对话框的结果经 wire 回报, event 返回值一律忽略)。返回 true 表示已无窗口 */
function act(wins, w, r) {
  if (r === "close") return closeMenu(wins, w);
  if (Array.isArray(r)) openItem(wins, w, r[1]);
}

const quote = s => s && /^[\p{L}\p{N}\-_./]+$/u.test(s) ? s : "'" + s.replaceAll("'", "'\\''") + "'";
const SELF = globalThis.process?.argv?.[1]?.split("/").pop() ?? "menu.js";
const showCmd = s => { STATUS = ["node", SELF, ...(CFG.pop === "stack" ? ["pop=stack"] : []), quote(s)].join(" "); };   // 默认 onpath: 屏底显示重开该路径的命令

// ---------- 布局 / 路由 ----------
const layout = wins => wins.flatMap(w => w.view().map(b => ({ ...b, x: b.x + w.x, y: b.y + w.y, win: w.name })));
const route = (boxes, x, y) => boxes.findLast(b => b.id && b.x <= x && x < b.x + b.w && b.y <= y && y < b.y + b.h);

/** boxes[i] 是否被更上层窗口的不透明 Box 压住(遮罩只能盖在字符背景之上, 压住就退回字符背景) */
const covered = (boxes, i) => {
  const b = boxes[i];
  return boxes.slice(i + 1).some(c => c.win !== b.win && c.bg && c.x < b.x + b.w && b.x < c.x + c.w && c.y < b.y + b.h && b.y < c.y + c.h);
};

// ---------- 图形进程 gra.py: 状态靠 stdio 行协议同步, 首词查字典 ----------
export const gfx = {
  mode: null,                 // null 未知 | "none" | "shm" | "direct"
  moving: new Set(),          // gra.py 报告的"补间未到位"的 key
  proc: null, probe: null,    // probe: 探测期间攒下的终端应答(字符串), 否则 null
  on() { return this.mode === "shm" || this.mode === "direct"; },
  send(line) { this.proc?.stdin.write(line + "\n"); },
};
let curve = "";               // 最近一次粘贴的曲线文本, 用于解析失败的提示

/** py -> js, 首词 -> 处理函数(参数 = 该行首词之后的原文) */
const FROM_PY = {
  out: s => io.out(s),
  mode: m => { gfx.mode = m; gfx.probe = null; if (gfx.on()) gfx.send("dur " + CFG.dur); SESSION?.render(); },
  state: s => { gfx.moving = new Set(s.split(" ").filter(Boolean)); if (CUR) paint(); },
  ease: n => { STATUS = +n ? `曲线已更新: ${n} 个控制点` : "曲线解析失败(需要 CSS linear(...)): " + curve.slice(0, 60); SESSION?.render(); },
};
/** 补间时长(ms): 改 CFG.dur 并(gra.py 在跑时)立即生效; 调参面板用 */
export const setDur = ms => { CFG.dur = ms; if (gfx.on()) gfx.send("dur " + ms); };

/** 把按行到达的文本按首词分派给 dict */
const lines = dict => {
  let buf = "";
  return chunk => {
    const ls = (buf + chunk).split("\n"); buf = ls.pop();
    for (const l of ls) { const i = l.indexOf(" "); dict[i < 0 ? l : l.slice(0, i)]?.(i < 0 ? "" : l.slice(i + 1)); }
  };
};

const hex = c => c.map(v => v.toString(16).padStart(2, "0")).join("");

/** 要交给 gra.py 的矩形: 动画 Box(遮罩, 补间) + 静态底色(仅 layered 终端需要)。keys: Box 下标 -> gra key */
function rects(boxes) {
  const lay = gfx.mode === "direct", keys = new Map(), specs = [];
  boxes.forEach((b, i) => {
    if (!b.bg || !(b.anim || lay) || (b.anim && covered(boxes, i))) return;
    const k = b.anim ? b.win : "bg" + i;                         // 动画 Box 每窗口至多一个, 以窗口名为键
    keys.set(i, k);
    specs.push(`${k}=${b.anim ? "->" : ""}${b.x},${b.y},${b.w},${b.h}#${hex(b.bg)}@${i}`);
  });
  return { keys, specs };
}

// ---------- 绘制: 有图形进程时先发矩形, 等它回 state(补间状态)再画文字帧 ----------
let CUR = null;               // 最近一次 show 的 { boxes, keys }

function show(boxes, snap) {
  CUR = { boxes, keys: new Map() };
  if (!gfx.on()) return paint();
  const r = rects(boxes);
  CUR.keys = r.keys;
  gfx.send((snap ? "snap " : "draw ") + r.specs.join(" "));
}

const sgr = (fg, bg) => "\x1b[0m" + (fg ? `\x1b[38;2;${fg.join(";")}m` : "") + (bg ? `\x1b[48;2;${bg.join(";")}m` : "");

function paint() {
  const { boxes, keys } = CUR, [cols, rows] = io.size(), lay = gfx.mode === "direct", imaged = new Set(keys.keys());
  const g = Array.from({ length: rows }, () => Array.from({ length: cols }, () => [" ", null, null]));   // [字, fg, bg]
  const cell = (x, y) => g[y]?.[x];
  boxes.forEach((b, i) => {
    for (let y = b.y; y < b.y + b.h; y++) for (let x = b.x; x < b.x + b.w; x++) {
      const c = cell(x, y);
      if (!c) continue;
      if (b.bg) { if (!imaged.has(i)) { c[0] = " "; c[2] = b.fade ? fadeBg(b, x) : b.bg; } else if (lay) { c[0] = " "; c[2] = null; } }
      if (b.border) {
        const top = y === b.y, bot = y === b.y + b.h - 1, left = x === b.x, right = x === b.x + b.w - 1;
        if ((top || bot) && (left || right)) c[0] = "┏┓┗┛"[(top ? 0 : 2) + (left ? 0 : 1)];
        else if (top || bot) c[0] = "━";
        else if (left || right) c[0] = "┃";
        else continue;
        c[1] = b.border;
      }
    }
    let col = 0;
    const fg = b.lit && !gfx.moving.has(b.win) ? b.lit : b.fg;   // 遮罩补间到位后才点亮文字
    for (const ch of b.text) {
      const wd = wide(ch) ? 2 : 1;
      if (col + wd > b.w) break;
      const c = cell(b.x + col, b.y), c2 = wd === 2 && cell(b.x + col + 1, b.y);
      if (c) { c[0] = ch; c[1] = fg; }
      if (c2) { c2[0] = ""; c2[1] = fg; }                        // 宽字符占的第二格
      col += wd;
    }
  });
  const frame = g.map((row, y) => {
    let s = `\x1b[${y + 1};1H`, cur = null;
    for (const [ch, fg, bg] of row) {
      if (!cur || fg !== cur[0] || bg !== cur[1]) { s += sgr(fg, bg); cur = [fg, bg]; }
      s += ch;
    }
    return s;
  }).join("") + "\x1b[0m";
  if (frame !== LAST) { LAST = frame; io.out(frame); }           // 相同则不重复写出
}

// ---------- 输入: 终端原始字节流(tty 或 xterm.js 的 onData 同形), 切成按键/鼠标记号 ----------
const KEYS = { "\x7f": "bs", "\x08": "bs", "\x17": "altbs", "\r": "enter", "\n": "enter" };
const ARROWS = { A: "up", B: "down", C: "right", D: "left", Z: "btab" };

/** s 尾部若停在未写完的转义序列中, 返回该序列起点, 否则 s.length(CLI 据此等一小会儿再喂入) */
export function tail(s) {
  const p = s.lastIndexOf("\x1b[200~");
  if (p > s.lastIndexOf("\x1b[201~")) return p;                  // 粘贴未结束
  const i = s.lastIndexOf("\x1b");
  if (i < 0) return s.length;
  const t = s.slice(i + 1);
  if (!t) return i;                                              // 孤立 ESC: 可能是 Esc, 也可能是序列前半
  if (t[0] === "O") return t.length < 2 ? i : s.length;
  if ("]P_^X".includes(t[0])) return t[0] === "]" && t.includes("\x07") ? s.length : i;   // 字符串序列: 终止符 ESC\ 本身就是最后一个 ESC
  if (t[0] !== "[") return s.length;
  for (const c of t.slice(1)) if (!(" " <= c && c <= "?")) return s.length;   // 终止字节(完整)或非法字节(序列已断开)
  return i;
}

/** str -> 'up'/'enter'/'del'/'a'... | ['mouse', b, x, y, 'M'|'m'] (SGR 鼠标, 坐标 0 起) | ['paste', text]
 *  转义序列按 ECMA-48 整条吞掉: 不认识的(Home/F 键/焦点/终端应答/Alt+字符)忽略, 绝不当作 Esc 或文字泄漏; 只有孤立的 ESC 才是 'esc' */
export function* tokens(s) {
  const n = s.length, cpLen = i => String.fromCodePoint(s.codePointAt(i)).length;
  let i = 0;
  while (i < n) {
    const c = s[i];
    if (c !== "\x1b") { const ch = s.slice(i, i + cpLen(i)); yield KEYS[ch] ?? ch; i += ch.length; continue; }
    if (i + 1 >= n) { yield "esc"; return; }
    const k = s[i + 1];
    if (k === "[" || k === "O") {
      let j = i + 2;
      while (j < n && "0" <= s[j] && s[j] <= "?") j++;          // 参数字节
      while (j < n && " " <= s[j] && s[j] <= "/") j++;          // 中间字节
      if (j >= n) return;                                        // 不完整: 丢弃
      const f = s[j], body = s.slice(i + 2, j);
      if (!("@" <= f && f <= "~")) { i = j; continue; }          // 非法终止字节: 从它重新解析
      if (k === "[" && body.startsWith("<") && "Mm".includes(f)) {
        const p = body.slice(1).split(";");
        if (p.length === 3 && p.every(x => /^\d+$/.test(x))) yield ["mouse", +p[0], +p[1] - 1, +p[2] - 1, f];
      } else if (k === "[" && f === "~" && body === "200") {
        const e = s.indexOf("\x1b[201~", j + 1);
        if (e < 0) return;                                       // 粘贴未结束: 丢弃
        yield ["paste", s.slice(j + 1, e)]; i = e + 6; continue;
      } else if (k === "[" && f === "~" && body === "3") yield "del";
      else if (ARROWS[f] && /^[0-9;]*$/.test(body)) yield ARROWS[f];
      i = j + 1;
    } else if ("]P_^X".includes(k)) {                            // OSC/DCS/APC/PM/SOS: 吞到 ST(ESC\, OSC 也可 BEL)
      const e1 = s.indexOf("\x1b\\", i + 2), e2 = k === "]" ? s.indexOf("\x07", i + 2) : -1;
      if (e1 < 0 && e2 < 0) return;
      i = e2 >= 0 && (e1 < 0 || e2 < e1) ? e2 + 1 : e1 + 2;
    } else if (k === "\x7f" || k === "\x08") { yield "altbs"; i += 2; }
    else if (k === "\x1b") { yield "esc"; i += 1; }              // ESC ESC: 先出一个 Esc, 后一个继续解析
    else i += 1 + cpLen(i + 1);                                  // Alt+字符: 忽略
  }
}

const focus = (wins, name) => wins.sort((a, b) => (a.name === name) - (b.name === name));   // 稳定排序: 目标窗口移到末尾

function popMode(args) {                                         // 没指定返回 null
  for (const a of [...args, "pop=" + (globalThis.process?.env.pop ?? "")]) {
    const [k, v] = a.replace(/^\$+/, "").split("=");
    if (k === "pop" && (v === "stack" || v === "replace")) return v;
  }
  return null;
}

/** 窗口栈(末尾=最上层/焦点) + 拖拽/按下状态; feed() 把输入记号翻译成窗口事件 */
class Session {
  constructor(tree, onblur, quit, persist = false) {
    Object.assign(this, { tree, onblur, quit, persist, wins: [], drag: null, press: null, dirty: false, chains: new Map(), snacks: {},
                          wire: { press() {}, active() {} },   // wire: 渲染 -> 宿主 的回报(press / active), 由宿主(pi.js)接上
                          arg: { focusHL: "color" },           // arg: 即 pi.arg; focusHL = 'color' | '' (按钮文字的强调色; 只在 gra.py 生效时才能关, 动效不受影响)
                          inspect: false, wlog: [] });         // inspect: 屏底滚动显示宿主 <-> 渲染 的线上消息
    this.emit = { press: (id, k) => { this.note("←", `press #${id} ${k}`); this.wire.press(id, k); },     // 渲染 -> 宿主(经 wlog 记录)
                  active: (id, k) => { this.note("←", `active #${id} ${k}`); this.wire.active(id, k); } };
    // drag: [窗口, 抓取点相对窗口的 dx, dy]; press: {w, hit, x, y, t} 项上按下后尚未判定是点击还是拖拽
  }

  note(dir, text) { if (this.inspect) { this.wlog.push(dir + " " + text); if (this.wlog.length > 5) this.wlog.shift(); } }   // 只留最近 5 条, 不压到居中的对话框

  openRoot(x, y, explicit = true) {                              // 在 (x, y) 开一个根菜单窗口并置顶
    const w = new Menu(this.tree, [], 0, uid(), [x, y], { explicit });
    this.wins.push(w);
    return w;
  }

  openPath(s) {                                                  // 按路径逐级展开并选中; 找不到则在屏底提示
    const idxs = resolve(this.tree, s);
    if (!idxs) STATUS = "路径未找到: " + s;
    if (!this.wins.length) this.openRoot(4, 2, false);
    for (const i of idxs ?? []) {
      layout(this.wins);                                         // 先跑一遍 view, 让窗口尺寸/滚动就位
      const w = this.wins.at(-1); w.sel = [i];
      act(this.wins, w, ["open", [i]]);
    }
  }

  render() {
    const [cols, rows] = io.size(), boxes = layout(this.wins);
    if (STATUS) boxes.push(box(1, rows - 1, cols - 2, 1, { text: "$ " + STATUS, fg: THEME.dim }));
    if (this.inspect) this.wlog.slice(-Math.max(0, rows - 3)).forEach((t, i, a) => boxes.push(box(1, rows - 1 - a.length + i, cols - 2, 1, { text: t, fg: THEME.dim })));
    for (const [where, s] of Object.entries(this.snacks)) if (s) {      // 角标: rt 右上, rd 右下
      const w = cw(s.text) + 2;
      const bg = s.bg === undefined ? THEME.snackBg : s.bg;                 // undefined = 跟随主题(改 snackBg 立即生效), null = 无底色
      boxes.push(box(cols - w, where === "rd" ? rows - 1 : 0, w, 1, { text: " " + s.text + " ", bg, fg: bg ? THEME.snackFg : THEME.text }));
    }
    show(boxes, this.drag !== null);
  }

  dispatch(w, kind, arg) { return act(this.wins, w, w.event(kind, arg)); }

  // ---- 宿主 -> 渲染(线上协议): 都会重绘 ----
  dialogOpen(id, kv, opts = {}) {
    this.note("→", `open #${id} ${JSON.stringify(kv)} ${JSON.stringify(opts)}`);
    this.wins.push(new Dialog(id, kv, opts, this.wins.filter(w => w instanceof Dialog).length, this.emit, this.arg));
    this.render();
  }
  kbdOpen(id, items) { this.note("→", `kbd #${id} ${items.length} items`); this.wins.push(new Kbd(id, items, this.emit)); this.render(); }   // 关窗用 dialogClose(id)
  dialogPatch(id, kv) { this.note("→", `patch #${id} ${JSON.stringify(kv)}`); this.wins.find(w => w.did === id)?.patch(kv); this.render(); }
  dialogClose(id) { this.note("→", `close #${id}`); keep(this.wins, w => w.did !== id); this.settle(); this.render(); }

  /** 开一个菜单(sexp 缺省或 [] = 本会话的树); cb = { onpath, onleaf, onend } 见 DEFAULT_CB */
  menuOpen(sexp, cb = {}) {
    const node = sexp?.length ? parse(sexp) : this.tree;
    if (!node) throw new Error("没有可用的菜单树");
    this.note("→", `menu ${node.name}`);
    const inner = cb, wrapped = { ...cb, onleaf: cb.onleaf && (p => { this.note("←", `leaf ${p}`); inner.onleaf(p); }) };
    const w = new Menu(node, [], 0, uid(), [4, 2], { cb: wrapped });
    this.chains.set(w.chain, wrapped); this.wins.push(w);
    this.render();
  }

  settle() {                                                     // 整串菜单窗口都没了 -> onend
    for (const [ch, cb] of [...this.chains]) if (!this.wins.some(w => w.chain === ch)) { this.chains.delete(ch); cb.onend?.(); }
  }

  tick(now = Date.now()) { if ([...this.wins].map(w => w.tick?.(now)).includes(true)) this.render(); }   // 驱动对话框倒计时
  status(text) { STATUS = text; this.render(); }
  /** where: 'rt' | 'rd'; bg: undefined 主题底色 | null 无底色 | [r,g,b]; text 为空撤下 */
  snack(where, text, bg) { this.note("→", `snack ${where} ${text}`); this.snacks[where] = text ? { text, bg } : null; this.render(); }

  paste(text) {                                                  // linear(...) 换动画曲线, 其余当作输入
    if (/^\s*linear\(/i.test(text)) {
      curve = text.trim();
      if (gfx.proc) gfx.send("ease " + curve.replace(/\s+/g, " "));
      else STATUS = "换曲线需要 gra.py 进程";
    } else for (const ch of text) if (printable(ch) && this.wins.length) this.dispatch(this.wins.at(-1), "key", ch);
    this.dirty = true;
  }

  startDrag(x, y) {                                              // 按住项后移动: 停留 >=DRAG_DELAY 才算拖拽, 之前是抖动
    const { w, x: px, y: py, t } = this.press;
    if ((x === px && y === py) || Date.now() - t < CFG.dragDelay) return false;
    this.drag = [w, px - w.x, py - w.y]; this.press = null;
    return true;
  }

  dragTo(b, x, y) {
    const [w, dx, dy] = this.drag;
    this.dirty = true;
    if (b === 32) w.move(x - dx, y - dy);
    else { w.remember(); this.drag = null; }                     // 松开(或松开事件丢失后的无键移动)
  }

  pressDown(w, hit, x, y) {
    dropDeeper(this.wins, w); focus(this.wins, w.name);          // 关闭更深的窗口, 取得焦点
    if (hit.id === "title") this.drag = [w, x - w.x, y - w.y];
    if (!hit.ip) return [w, "click", hit];
    this.press = { w, hit, x, y, t: Date.now() };
    return [w, "hover", hit];
  }

  release(x, y) {                                                // 项上的按下: 原地松开才是点击
    const { w, hit: h0 } = this.press, hit = route(layout(this.wins), x, y);
    this.press = null;
    if (this.wins.includes(w) && hit?.id === h0.id && hit.win === w.name) return [w, "click", h0];
  }

  /** b=按钮码, kind='M' 按下/移动 | 'm' 松开。返回要派发的 [窗口, 事件, 参数] 或 undefined */
  mouse(b, x, y, kind) {
    if (this.press && b === 32 && !this.startDrag(x, y)) return;
    if (this.drag) return this.dragTo(b, x, y);
    if (this.press && kind === "m" && b === 0) return this.release(x, y);
    this.press = null;
    const hit = route(layout(this.wins), x, y);
    if (!hit) {
      if (b === 0 && kind === "M") { this.onblur(x, y, (px, py) => this.openRoot(px, py)); this.dirty = true; }
      return;
    }
    const w = this.wins.find(w => w.name === hit.win);
    if (b & 64) return [w, "key", b === 64 ? "up" : "down"];
    if (b === 0 && kind === "M") return this.pressDown(w, hit, x, y);
    if (b === 35 && hit.ip && !same(w.sel, hit.ip)) return [w, "hover", hit];
  }

  /** true 表示该退出了(按下 quit 键或已无窗口) */
  feed(data) {
    this.dirty = false;
    for (const t of tokens(data)) {
      if (t === this.quit || (!this.persist && !this.wins.length)) return true;
      let ev;
      if (typeof t === "string") ev = this.wins.length ? [this.wins.at(-1), "key", t] : null;
      else if (t[0] === "paste") { this.paste(t[1]); continue; }
      else ev = this.mouse(...t.slice(1));
      if (ev) { this.dirty = true; if (this.dispatch(...ev) && !this.persist) return true; }
    }
    this.settle();
    if (this.dirty) this.render();
  }
}

/** 事件驱动核心(无阻塞、无 tty): 写出 ENTER, 开初始窗口并首绘, 返回 Session。
 *  o: { args, onpath(s), onblur(x, y, open), rempos, root=true, quit="\x03"(null=不把 Ctrl-C 当退出键), status=屏底初始文字,
 *       persist=窗口都关了也不退出(宿主模式; 此时 sexp 可为 null), theme(见 setTheme; args 里的 color.<键>=#rrggbb 同效),
 *       inspect=屏底显示线上消息(args 里 inspect=1 同效); args 里 cfg.<键>=值 改 CFG(如 cfg.itemH=4 cfg.itemMinW=10 cfg.rempos=rt) } */
export function start(sexp, o = {}) {
  const args = o.args ?? [];
  const pairs = re => args.flatMap(a => { const m = re.exec(a); return m ? [[m[1], m[2]]] : []; });
  CFG.pop = popMode(args) ?? CFG.pop; if (o.rempos) CFG.rempos = o.rempos;
  for (const [k, v] of pairs(/^cfg\.(\w+)=(.+)$/)) { if (!(k in CFG)) throw new Error("unknown cfg key: " + k); CFG[k] = typeof CFG[k] === "number" ? Number(v) : v; }
  if (CFG.btnH % 2 === 0) throw new Error("cfg.btnH 必须是奇数: " + CFG.btnH);
  ONPATH = o.onpath ?? showCmd; LAST = null; STATUS = o.status ?? "";
  setTheme({ ...Object.fromEntries(pairs(/^color\.(\w+)=(.+)$/)), ...o.theme });
  const s = SESSION = new Session(sexp ? parse(sexp) : null, o.onblur ?? (sexp ? (x, y, open) => open(x, y) : () => {}),
                                  o.quit === undefined ? "\x03" : o.quit, !!o.persist);
  io.out(ENTER);
  s.inspect = !!o.inspect || args.includes("inspect=1");
  if (o.root !== false && sexp) s.openRoot(4, 2, false);
  const arg1 = args.find(a => !a.includes("="));
  if (arg1 && sexp) s.openPath(arg1);                            // 按 arg1 展开路径并选中
  s.render();
  return s;
}

/** 程序模块约定(cli 与 index.html 的 ?OMA_CMD=xxx.js 共用): default export boot({ tree, note, args, quit, hooks }) -> Session */
export default ({ tree, note, args, hooks = {} }) => start(tree, { args, status: note, ...hooks });

// ---------- CLI: setRawMode + stdin 流 + gra.py 子进程 ----------
/** boot({ tree, note, args, quit }) 返回 Session(缺省 start(tree)); 宿主模式见 demo.js */
export async function cli(boot) {
  const { spawn } = await import("node:child_process"), { readFile } = await import("node:fs/promises");
  const { stdin, stdout } = process, dec = new TextDecoder();
  io.size = () => [stdout.columns, stdout.rows]; io.out = s => stdout.write(s);
  const [tree, note] = await loadTree(() => readFile(new URL("../tree.json", import.meta.url), "utf8"));

  let quitting = false, done = () => {};
  const quit = () => { quitting = true; if (gfx.proc) gfx.proc.stdin.end(); else done(); };   // gra.py 读到 EOF 会清掉图像再退出, 之后 close -> done
  const args = process.argv.slice(2), sess = boot ? boot({ tree, note, args, quit }) : start(tree, { args });
  done = () => { stdin.setRawMode(false); stdout.write(LEAVE, () => { if (note) console.error(note); process.exit(); }); };

  const py = gfx.proc = spawn("python3", [new URL("gra.py", import.meta.url).pathname], { stdio: ["pipe", "pipe", "inherit"] });
  py.stdin.on("error", () => {});
  py.stdout.setEncoding("utf8").on("data", lines(FROM_PY));
  py.on("close", () => {
    gfx.proc = null; gfx.mode = "none"; gfx.moving = new Set(); gfx.probe = null;
    if (quitting) done(); else sess.render();
  });
  gfx.probe = ""; gfx.send("probe");
  setTimeout(() => { if (gfx.probe !== null) { gfx.send("reply " + gfx.probe); gfx.probe = null; } }, 300).unref();   // 终端不答 DA1
  setInterval(() => sess.tick(), 250).unref();                   // 对话框倒计时

  let pend = "", timer;
  const flush = () => { clearTimeout(timer); const s = pend; pend = ""; if (s && sess.feed(s)) quit(); };
  const input = s => {
    if (gfx.probe !== null) {                                    // 探测期间: 应答(到 DA1 为止)转交 gra.py, 余下的才是按键
      gfx.probe += s;
      const m = /\x1b\[\?[\d;]*c/.exec(gfx.probe);
      if (!m) return;
      const end = m.index + m[0].length;
      gfx.send("reply " + gfx.probe.slice(0, end).replace(/[\r\n]/g, ""));
      s = gfx.probe.slice(end); gfx.probe = null;
    }
    clearTimeout(timer); pend += s;
    if (tail(pend) < pend.length) timer = setTimeout(flush, 50); // 序列被拆成多次 read: 等一小会儿
    else flush();
  };
  stdin.setRawMode(true);
  stdin.on("data", c => input(dec.decode(c, { stream: true })));
  stdin.on("end", quit);
  stdout.on("resize", () => sess.render());
  for (const sig of ["SIGTERM", "SIGHUP"]) process.on(sig, quit);
}

if (globalThis.process?.versions?.node && decodeURIComponent(new URL(import.meta.url).pathname) === process.argv[1]) cli();   // 被 import 时不自启
