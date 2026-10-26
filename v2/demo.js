#!/usr/bin/env node
// pi.dialog / pi.omarchy.menu 的可运行示例, 也是 test/02..10.py 黑盒测试的被测程序:
//   node v2/demo.js                 无参: 打开 inspect(屏底滚动显示宿主 <-> 渲染的线上消息) + 场景菜单(Esc 退出)
//   node v2/demo.js <场景> [color.selFg=#rrggbb cfg.itemMinW=10 inspect=1 ...]
//   node v2/demo.js repl [port=9229] [color.preset=pink]   只开 inspector 并把 pi / sess 挂到 globalThis: v2/demo.ipynb 的 %%js 单元经 CDP 在这里执行
// 场景分两组: SCENARIOS 显示在用法和场景菜单里; HIDDEN 不显示, 只能按名字运行(专测边角 API 语义)。
// 每个场景按顺序执行若干步, 每步的结果写在屏底 "$ result: ..."; Ctrl-C 退出。
// 本模块也是"程序模块": default export boot(...) -> Session, 浏览器 index.html?OMA_CMD=demo.js 同样可用。
import { CFG, FRAMES, PRESETS, cli, gfx, setTheme, start } from "./menu.js";
import { createPi } from "./pi.js";

const sleep = ms => new Promise(r => setTimeout(r, ms));

export const SCENARIOS = {
  /** goal-v1.ts 的示例: 勾选 / 单选 + State + 定时器 / 网格 / 堆叠与替换 / ret / 角标 */
  async dialogs(pi, report) {
    let web = false;                                             // 1. 勾选: 按钮自己渲染 '[x] web'
    report(await pi.dialog({ init: { title: 'T', body: '...', footer: '' } },
                           { OK() {}, web: up => (up && (web = !web), web ? '[x] web' : '[ ] web') }));

    const [c, c1] = pi.onEmit({ title: 'Ctrl+P', body: '', footer: '', cost: 0, sel: 'A', web: 0 });   // 2. 单选 + 派生文字写在每个写入处
    const body = () => c1.body(`selected ${c.sel} · $${c.cost.toFixed(2)}`);
    const radio = name => up => (up && (c1.sel(name), body()), c.sel === name ? `● ${name}` : `○ ${name}`);
    const dlg = pi.dialog({ init: c }, {
      A: radio('A'),
      B: radio('B'),
      web: up => (up && (c1.web(c.web ^ 1), c1.footer(c.web ? '关掉 WebUI' : '打开 WebUI')), c.web ? '[x] web' : '[ ] web'),
      Done: () => {},
    });
    body();
    c.setTimeout(-1000, () => (c1.cost(c.cost + 0.12), body()));
    c.setTimeout(10_000, () => dlg.ret(null));
    report(await dlg);

    report(await pi.dialog({ init: { title: 'Ctrl+P' }, eachRow: [2, 2] },   // 3. 网格: 两行各两个, ↑/↓ 保持列
                           { model() {}, effort() {}, plan() {}, web() {} }));

    let third;                                                   // 4. 堆叠: 按钮返回文字 = 不关; 替换: 返回 undefined 的同时开新的。副作用只在 up(按下) 时做: 渲染也会调用按钮
    const second = () => pi.dialog({ init: { title: 'second', body: 'stacked' } }, { Back() {} });
    report(await pi.dialog({ init: { title: 'first', body: 'S1' } }, {
      Push: up => up ? (second(), 'Push') : undefined,
      Replace: up => { if (up) third = pi.dialog({ init: { title: 'third', body: 'replaced S1' } }, { Fin() {} }); },
    }));
    report(await third);

    pi.notify('● 2.1s · 3m $0.12', 'snack');                     // 5. ret 从外部关闭 + 右上角角标
    const [c2, c3] = pi.onEmit({ title: 'ret', body: 'closes itself' });
    const d5 = pi.dialog({ init: c2 }, { Stay() {} });
    c2.setTimeout(1500, () => d5.ret('late'));
    report(await d5);
  },

  /** 非模态: 右上角, 到点按下 or(没有则 null); 第一次交互就取消自动选择 */
  async timeout(pi, report) {
    const ask = (title, or) => pi.dialog({ init: { title, body: 'Delete everything?' }, timeout: 2000, or }, { Yes() {}, No() {} });
    report(await ask('with or', 'No'));                          // 没人动: 按 or
    report(await ask('no or'));                                  // 没 or 且没动过: null
    report(await ask('touched'));                                // 测试里按一下 → 自动选择被取消, 之后只能手动按
  },

  /** pi.arg.focusHL: HL 按钮在 'color' ⇄ '' 之间切换; 正文实时显示 gra.py 的模式 —— '' 只在 gra.py 生效(shm / direct)时才真的关掉高亮, 否则焦点会看不出来 */
  async focus(pi, report) {
    const [c, c1] = pi.onEmit({ title: 'focusHL', body: '', footer: 'HL 只在 gra.py 生效时才能关; ← → 移动焦点, 看补间' });
    const info = () => c1.body(`gra.py: ${gfx.mode ?? 'probing…'}   focusHL=${pi.arg.focusHL || "''"}`);
    info();
    c.setTimeout(-300, info);                                    // gra.py 的探测结果是异步到的
    report(await pi.dialog({ init: c }, {
      Yes() {}, No() {},
      HL: up => (up && (pi.arg.focusHL = pi.arg.focusHL ? '' : 'color', info()), pi.arg.focusHL ? '[x] HL' : '[ ] HL'),
      Done() {},
    }));
  },

  /** pi.omarchy.menu([], pi.if404(k => ..., { 路径: () => ... })) */
  async omarchy(pi, report) {
    const how = [], h = pi.if404(() => how.push('fallback'), { 'Learn/Arch': () => how.push('table'), 'MyPath/Arch': () => how.push('mine') });
    const show = async p => report(`${await p} ${how.splice(0)}`);
    await show(pi.omarchy.menu([], h));                          // 会话自带的树, 选 Learn/Arch -> 表里有
    await show(pi.omarchy.menu([], h));                          // 选 Learn/Bash -> 没登记, 走 fallback
    await show(pi.omarchy.menu(['Root', ['MyPath', ['Arch'], ['Other']]], h));   // 自己的树
    await show(pi.omarchy.menu([], h));                          // Esc 到底 -> null
  },

  /** pi.inlineKbd(items): 输入框上方的窄下拉; Tab/↑/↓ 选, 打字过滤, Enter 给选中项, Esc 给 null */
  async kbd(pi, report) {
    const items = ['/model', '/memory', '/mcp', '/help', '/clear', '/compact', '/config', '/cost'];
    report(await pi.inlineKbd(items));
    report(await pi.inlineKbd(items));
  },
};

export const HIDDEN = {
  /** 空场景: inspector + globalThis.pi, 给 v2/demo.ipynb 用 */
  repl: async (pi, report, sess) => report(`pi ready · ${(await devtools(sess).catch(() => null)) ?? "inspector 没开成(9229 被占?)"}`),

  /** Button 返回 Promise: 等待期间保持原样且不响应第二次按下; 渲染时返回 Promise = 文字稍后到; 按钮抛错只记日志、对话框不关 */
  async: async (pi, report) => {
    const [c, c1] = pi.onEmit({ title: 'async', body: 'calls: 0', n: 0 });
    report(await pi.dialog({ init: c }, {
      Slow: up => up ? (c1({ n: c.n + 1, body: `calls: ${c.n + 1}` }), sleep(800).then(() => 'Slow ✓')) : undefined,
      Label: up => up ? undefined : sleep(300).then(() => 'late label'),
      Boom: up => { if (up) throw new Error('boom'); },
      Done: () => Promise.resolve(),
    }));
  },

  /** update: 'oldnew'(默认)只重新渲染上一个和新的焦点按钮, 'full' 重新渲染全部; 标签 = 键名 + 渲染次数 */
  update: async (pi, report) => {
    for (const update of ['oldnew', 'full']) {
      const n = { A: 0, B: 0, C: 0 }, btn = k => up => up ? undefined : `${k}${++n[k]}`;
      report(await pi.dialog({ init: { title: `update=${update}` }, update, or: 'A' }, { A: btn('A'), B: btn('B'), C: btn('C') }));
    }
  },

  /** 布局: 无标题 + 'vertical' + 勾选/单选语法变体 + CJK 宽度 + fadeX 0 + 点击; 再来 eachRow [1, 2](最后一个数字重复)的 ↑/↓ 保持列 */
  layout: async (pi, report) => {
    let strict = true;
    const keep = s => () => s;                                   // 返回文字 = 不关
    report(await pi.dialog({ init: { body: 'line one\n第二行', footer: 'footer' }, eachRow: 'vertical', fadeX: 0 }, {
      cn: keep('( ) 中文按钮'),
      go: keep('(*) Go'),
      strict: up => (up && (strict = !strict), strict ? '[x] strict' : '[ ] strict'),
      plain: keep('plain text'),
      Quit() {},
    }));
    report(await pi.dialog({ init: { title: 'rows [1, 2]' }, eachRow: [1, 2] }, { b1() {}, b2() {}, b3() {}, b4() {}, b5() {} }));
  },

  /** State 事务: 写同值 / 写了又写回 都不发 patch; 批量写合成一条; c.setTimeout 一次 / 取消 / 重复, 关闭后定时器全清。
   *  每条 patch 的键写在屏底 "patches=N keys=..." */
  state: async (pi, report, sess) => {
    const [c, c1] = pi.onEmit({ title: 'state', body: 'b0', footer: '', n: 0 });
    let patches = 0, fired = 0, stop;
    const patch = sess.dialogPatch.bind(sess);
    sess.dialogPatch = (id, kv) => { patch(id, kv); sess.status(`patches=${++patches} keys=${Object.keys(kv)}`); };
    const lab = name => `${name} n=${c.n}`;
    report(await pi.dialog({ init: c, eachRow: [4, 3] }, {
      Same: up => (up && c1.n(c.n), lab('Same')),
      Bounce: up => (up && (c1.n(c.n + 1), c1.n(c.n - 1)), lab('Bounce')),
      Batch: up => (up && c1({ n: c.n + 1, body: 'batched' }), lab('Batch')),
      Once: up => (up && c.setTimeout(300, () => c1.footer('timer fired')), 'Once'),
      Cancel: up => (up && c.setTimeout(300, () => c1.footer('SHOULD NOT'))(), 'Cancel'),
      Tick: up => (up && !stop && (stop = c.setTimeout(-100, () => { fired++; })), 'Tick'),
      Done() {},
    }));
    const t0 = fired;
    await sleep(700);
    report(fired === t0 ? `timers stopped after ${t0 > 0 ? 'some' : 'zero'} ticks` : 'timers leaked');
  },

  /** pi.notify 的角标变体(默认底色 / 'none' / '#rrggbb' / 0xRRGGBB / '' 撤下 / 没有 where 不画); dialog.ret() 无参得 null; pi.if404 直接用 */
  notify: async (pi, report, sess) => {
    pi.notify('top-right default', 'snack');
    pi.notify('bottom-right plain', 'snackRD', { bg: 'none' });
    pi.notify('desktop only');
    report(await pi.dialog({ init: { title: 'snacks' } }, {
      Theme: up => up ? (setTheme({ snackBg: '#3050e0' }), sess.render(), 'Theme') : undefined,      // 改 snackBg: 已经在屏上的默认底色角标跟着变
      Red: up => up ? (pi.notify('red snack', 'snack', { bg: '#e03030' }), 'Red') : undefined,
      Num: up => up ? (pi.notify('num snack', 'snackRD', { bg: 0x2030e0 }), 'Num') : undefined,
      Clear: up => up ? (pi.notify('', 'snack'), pi.notify('', 'snackRD'), 'Clear') : undefined,
      Done() {},
    }));
    const [c, c1] = pi.onEmit({ title: 'ret()' }), d = pi.dialog({ init: c }, { Stay() {} });
    c.setTimeout(600, () => d.ret());
    const r = await d, t = pi.if404(k => 'nf:' + k, { a: () => 'A' });
    report(`${r} ${t.a()} ${t.zzz()} ${typeof t.then}`);
  },
};

let PORT = 9229;                                                 // 参数 port=NNNN 可改
/** 无参启动: Node DevTools(inspector, 默认 9229, 被占就不开; 浏览器里直接按 F12) + 场景菜单(只列 SCENARIOS), 选一个跑完回到菜单, Esc 退出 */
async function devtools(sess) {
  if (!globalThis.process?.versions?.node) return "浏览器里按 F12";
  const inspector = await import("node:inspector");
  if (!inspector.url()) {
    const write = process.stderr.write;                          // 端口被占时 node 会往 stderr 打一行, 会弄花界面
    process.stderr.write = () => true;
    try { inspector.open(PORT, "127.0.0.1", false); } catch {} finally { process.stderr.write = write; }
  }
  if (!inspector.url()) return null;                             // 没开成: 不显示
  const u = new URL(inspector.url());
  sess.note("·", `devtools://devtools/bundled/js_app.html?ws=${u.host}${u.pathname}`);
  return `${u.host}  (chrome://inspect → Configure…)`;
}

async function hub(pi, report, sess, quit) {
  const buttons = Object.fromEntries(Object.keys(SCENARIOS).map(k => [k, () => {}])), dt = await devtools(sess).catch(() => null);
  for (;;) {
    const r = await pi.dialog({ init: { title: 'oma demo', body: "pick a scenario (inspect is on)" + (dt ? `\nDevTools: ${dt}` : ""), footer: 'Esc quits' }, eachRow: 'vertical' }, buttons);
    if (r === null) return quit();
    await SCENARIOS[r](pi, report, sess);
  }
}

export default function boot({ tree, args, quit }) {
  const name = args.find(a => !a.includes("=")), rest = args.filter(a => a.includes("="));
  PORT = +(rest.find(a => a.startsWith("port="))?.slice(5) ?? PORT);
  const run = name && { ...SCENARIOS, ...HIDDEN }[name];
  const sess = start(tree, { args: name || rest.includes("inspect=0") ? rest : [...rest, "inspect=1"], root: false, persist: true, onblur: () => {} });
  const pi = createPi(sess, { log: (...a) => sess.status("log: " + a.map(String).join(" ")) }), report = v => sess.status("result: " + v);
  Object.assign(globalThis, { pi, sess, oma: { setTheme, CFG, FRAMES, PRESETS, gfx } });   // CDP / DevTools 控制台里直接用
  if (name && !run) { sess.status(`usage: demo.js [${Object.keys(SCENARIOS).join("|")}]`); return sess; }
  (run ? run(pi, report, sess) : hub(pi, report, sess, quit)).catch(e => sess.status("scenario threw: " + e.stack));
  return sess;
}

if (globalThis.process?.versions?.node && decodeURIComponent(new URL(import.meta.url).pathname) === process.argv[1]) cli(boot);
