// pi 插件 API 的宿主侧(规格见 cld-pi/goal-v1.ts): pi.dialog / pi.onEmit / pi.omarchy.menu / pi.if404 / pi.notify。
// 纯 JS、无 I/O: 通过 Session(menu.js) 的线上协议驱动渲染, 浏览器和 Node 通用。
//
//   host -> 渲染   sess.dialogOpen(id, kv, opts) / dialogPatch(id, kv) / dialogClose(id)     kv 的值 null = 撤下该键
//   渲染 -> host   sess.wire.press(id, key|null)  Enter / 点击 / 到点自动按下; Esc 为 null
//                  sess.wire.active(id, key)      焦点移到某个按钮(规格只有 press; 这是为 `update` 重绘加的)
//
// 用法:
//   const sess = start(tree, { persist: true, root: false }), pi = createPi(sess)
//   const [c, c1] = pi.onEmit({ title: 'T', body: '', footer: '', web: 0 })
//   const r = await pi.dialog({ init: c }, { OK() {}, web: up => (up && c1.web(c.web ^ 1), c.web ? '[x] web' : '[ ] web') })
//
// 按钮标签的渲染语法(都只是画法, 宿主侧没有别的 API; 识别在 menu.js mark()):
//   '[x] a' '( ) a' '(*) a' '○ a' '● a'   开头: 勾选 / 单选图标         'a [x]' 'a [ ]'  结尾: 开关(滑块, gra.py 补间)
//   'a ▼'                                 下拉框; 用 dialog 的 drop: { key: items } 声明时 ' ▼' 自动追加, 按下即弹出列表
//   '[...]'                               spacer: 不可见、不可聚焦, 平分该行剩余宽度(该行撑满对话框)
//   eachRow 里的负数 -n                   n 个按钮的分段组: 撑满对话框、平分宽度、无间隔; '●' 的那段是选中段(图标不画); 键盘移到哪段就按下哪段
// 点在所有窗口之外 = Esc: dialog / 下拉列表 resolve null(非模态 toast 除外), omarchy.menu resolve null
//   const path = await pi.omarchy.menu([], pi.if404(k => console.log('no handler', k), { 'Learn/Arch': () => {} }))

let LOG = (...a) => console.error(...a);
const timers = new WeakMap();
const RADIO = /^(\(([ *•xX])\)|[○◯●◉])\s/;            // 单选语法: oldnew 模式下 State 变化时这些按钮也重新渲染(兄弟按钮要跟着换点)
const SPACER = "[...]", DROP = /\s+[▼▾]$/;                     // State -> Set<取消函数>

/** 状态: 返回 [c, c1]。c.x 读, c1.x(v) / c1({ x, y }) 写; 写入合并到当前 microtask 末尾, 之后 c.onUpd(kv) 收到值有变化的键(字符串, null = 撤下) */
export function onEmit(initial = {}) {
  const c = { ...initial }, dirty = new Map();    // dirty: 键 -> 本事务开始时的值
  let queued = false;
  const flush = () => {
    queued = false;
    const kv = {};
    for (const [k, before] of dirty) if (!Object.is(before, c[k])) kv[k] = c[k] == null ? null : String(c[k]);
    dirty.clear();
    if (Object.keys(kv).length) c.onUpd?.(kv);
  };
  const set = (k, v) => {
    if (!dirty.has(k)) dirty.set(k, c[k]);
    c[k] = v;
    if (!queued) { queued = true; queueMicrotask(flush); }
  };
  const c1 = new Proxy(patch => { for (const k of Object.keys(patch)) set(k, patch[k]); }, {
    get: (_, k) => typeof k === "string" && k !== "then" ? v => set(k, v) : undefined,
  });
  Object.defineProperty(c, "onUpd", { value: undefined, writable: true });
  Object.defineProperty(c, "setTimeout", {
    value(ms, fn) {                               // ms > 0 一次, ms < 0 每 |ms| 毫秒; 回调里写 State 同样走 microtask 事务
      const all = timers.get(c) ?? timers.set(c, new Set()).get(c);
      const run = async () => { try { await fn(); } catch (e) { LOG("timer threw", e); } };
      const id = ms < 0 ? setInterval(run, -ms) : setTimeout(() => { all.delete(cancel); run(); }, ms);
      const cancel = () => { clearTimeout(id); clearInterval(id); all.delete(cancel); };
      all.add(cancel);
      return cancel;
    },
  });
  return [c, c1];
}

const stopTimers = c => { for (const cancel of [...(timers.get(c) ?? [])]) cancel(); };

/** 路径表: table[k] 没有时返回 (...a) => fallback(k, ...a), 所以 handler[path]?.() 总能调到 */
export const if404 = (fallback, table = {}) => new Proxy(table, {
  get: (t, k) => Object.hasOwn(t, k) ? t[k] : typeof k === "string" && k !== "then" ? (...a) => fallback(k, ...a) : undefined,
});

const color = bg => bg === "none" ? null : typeof bg === "number" ? [bg >> 16 & 255, bg >> 8 & 255, bg & 255]    // 数字按 0xRRGGBB
  : typeof bg === "string" ? bg.replace("#", "").match(/../g).map(h => parseInt(h, 16)) : undefined;

export function createPi(sess, { log } = {}) {
  if (log) LOG = log;
  const dialogs = new Map();                      // id -> { press(key), active(key) }
  let seq = 0;
  sess.wire.press = (id, key) => dialogs.get(id)?.press(key);
  sess.wire.active = (id, key) => dialogs.get(id)?.active(key);

  /** d.init 是 onEmit 的 c(dialog 只监听它的变化, 写入在宿主手里), 或不会变的 { title, body, footer }。resolve 为按下的按钮键名; Esc 为 null。
   *  返回的 Promise 同时是句柄: ret(value) 在任何地方关闭并 resolve 为 value; drop(key, items) 在按钮 key 正下方弹出下拉列表
   *  update: 'oldnew'(默认) 焦点移动和 State 变化都只重新渲染上一个焦点、当前焦点(及单选语法的按钮); 'full' 全部重新渲染
   *  drop: { key: items | () => items }: 这些按钮是下拉框, 标签自动追加 ' ▼'; 按下时在它下面弹出列表(焦点移过去),
   *        选中后调用按钮 bs[key](选中项)(渲染时仍是 bs[key](false)), Esc / 点别处什么都不做 */
  function dialog(d = {}, bs = {}) {
    const c = d.init && "onUpd" in d.init ? d.init : onEmit(d.init ?? {})[0], id = ++seq, keys = Object.keys(bs), labels = {}, sent = {};
    let closed = false, busy = false, last = null, cur = null, resolve;
    const promise = new Promise(r => { resolve = r; });
    const text = k => c[k] == null ? "" : String(c[k]);
    const now = () => ({ title: text("title"), body: text("body"), footer: text("footer"), ...labels });
    const drops = d.drop ?? {};
    const label = (k, r) => {                                           // null / undefined / void -> 键名; 下拉框追加 ' ▼'
      const t = typeof r === "string" ? r : k;
      return Object.hasOwn(drops, k) ? t.replace(DROP, "") + " ▼" : t;
    };

    const sync = () => {                          // 只发和上次不同的键
      if (closed) return;
      const cur = now(), kv = {};
      for (const k in cur) if (sent[k] !== cur[k]) kv[k] = cur[k];
      Object.assign(sent, kv);
      if (Object.keys(kv).length) sess.dialogPatch(id, kv);
    };
    const render = ks => {                        // up = false: 渲染(open / 焦点移动 / State 变化)
      for (const k of ks) {
        let r;
        try { r = bs[k](false); } catch (e) { LOG("dialog button threw", e); }
        if (r?.then) {                                                  // 文字稍后到: 先用键名(没有 label 键按钮就不存在), resolve 后再 patch
          labels[k] ??= k;
          r.then(v => { if (!closed) { labels[k] = label(k, v); sync(); } }, e => LOG("dialog button threw", e));
        } else labels[k] = label(k, r);
      }
    };
    const close = v => {
      if (closed) return;
      closed = true;
      dialogs.delete(id);
      if (c.onUpd === upd) { c.onUpd = undefined; stopTimers(c); }      // 单槽: 只有仍绑着自己才清(替换时新 dialog 已接手)
      sess.dialogClose(id);
      resolve(v);
    };
    const dirty = () => d.update === "full" ? keys
      : keys.filter(k => k === last || k === cur || RADIO.test(labels[k] ?? ""));
    const upd = () => { render(dirty()); sync(); };                     // State 变化: 重算(部分)按钮再 diff

    dialogs.set(id, {
      active(key) {                               // update: 'full' 刷新全部按钮, 默认 'oldnew' 只刷新上一个和新的
        last = cur; cur = key;
        render(d.update === "full" ? keys : [...new Set([last, cur])].filter(k => k != null && k in bs)); sync();
      },
      async press(key) {
        if (closed) return;
        if (key == null) return close(null);
        if (busy || !(key in bs)) return;                                // Promise 等待期间不响应第二次按下
        let r;
        busy = true;
        try {
          if (Object.hasOwn(drops, key)) {                              // 下拉框: 先选, 再把选中项交给按钮
            const items = typeof drops[key] === "function" ? drops[key]() : drops[key];
            const v = await inlineKbd(await items, { below: [id, key] });
            if (v == null || closed) return;
            r = bs[key](v);
          } else r = bs[key](true);
          if (r?.then) r = await r;
        } catch (e) { LOG("dialog button threw", e); return; }
        finally { busy = false; }
        if (closed) return;
        if (typeof r === "string") { labels[key] = label(key, r); queueMicrotask(sync); } else close(key);   // 排在本事务 flush 之后: 同一事务只发一条 patch
      },
    });
    render(keys);
    cur = d.or ?? keys.find(k => labels[k] !== SPACER) ?? null;          // 渲染侧的初始焦点同样跳过 spacer
    Object.assign(sent, now());
    c.onUpd = upd;
    sess.dialogOpen(id, { ...sent }, { timeout: d.timeout, or: d.or, eachRow: d.eachRow, fadeX: d.fadeX });
    return Object.assign(promise, { ret: v => close(v ?? null), drop: (key, items) => inlineKbd(items, { below: [id, key] }) });
  }

  /** 输入框上方的窄下拉(fzf 式 Tab 补齐, 行数见 CFG.kbdRows): 打字过滤, ↑/↓/Tab 选择, Enter 确认; resolve 为选中项, Esc 为 null。
   *  '~' 开头的项禁用(暗色、跳过、不可选; resolve 不含 '~')。opts.below = [对话框 id, 按钮键]: 贴在该按钮正下方、同宽, 搜索行在顶上(下拉框) */
  function inlineKbd(items, opts = {}) {
    const id = ++seq;
    return new Promise(resolve => {
      dialogs.set(id, { active() {}, press(key) { dialogs.delete(id); sess.dialogClose(id); resolve(key); } });
      sess.kbdOpen(id, [...items], opts);
    });
  }

  /** 菜单: tree 是 tree.json 同形的 s-expr(["Go", ["  Apps"], ...]), [] = 会话自带的树。选中叶子 -> 关闭菜单, 调 handler 后 resolve 路径('Learn/Arch');
   *  Esc 退到底 resolve null。handler 是函数 path => ... 或路径表 { 'Learn/Arch': () => ... }(配 pi.if404 处理没登记的路径) */
  const menu = (tree, handler) => new Promise((resolve, reject) => {
    let picked = false;
    sess.menuOpen(tree, {
      onleaf: path => {
        picked = true;
        (async () => (typeof handler === "function" ? handler(path) : handler?.[path]?.()))().then(() => resolve(path), reject);
      },
      onend: () => { if (!picked) resolve(null); },
    });
  });

  /** 只管角标: 'snack' 右上 / 'snackRD' 右下, '' 撤下; style.bg: 0xRRGGBB | '#rrggbb' | 'none'。桌面通知(notify-send)是宿主 OS 的事, 不在这里 */
  const notify = (msg, where, style = {}) => {
    if (where === "snack" || where === "snackRD") sess.snack(where === "snack" ? "rt" : "rd", msg, color(style.bg));
  };

  /** pi.arg.focusHL = 'color' | '': 全局开关, '' 不画按钮焦点高亮(改了立即重绘) */
  const arg = new Proxy(sess.arg, { set: (t, k, v) => (t[k] = v, sess.render(), true) });

  return { dialog, inlineKbd, onEmit, if404, omarchy: { menu }, notify, arg };
}
