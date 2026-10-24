"""pi.dialog (v2/demo.js dialogs): 同一进程依次走 5 个对话框, 每条从上一条结束的画面开始。
勾选/单选语法 [x] ○ ● 渲染成 Omarchy 图标; 状态 = pi.onEmit, 按钮 = (up) => 文字。"""
import re
from tui import *

CMD = f"{DEMO} dialogs"


def cost_grows(c):
    cost = lambda: float(re.search(r"\$(\d+\.\d\d)", c.frame.text).group(1))
    a = cost()
    wait(c, 1.3)
    c.check(cost() > a, f"定时器写 State, 费用自己涨 ({a} → {cost()})")


def _00(c):
    """首个对话框: 标题 T / 正文 ...; '[ ] web' 渲染成关闭的勾选图标, 按钮最小宽度 8、文字居中、底色两端渐隐; 选中的 OK 文字是强调色"""
    c - [grep, r"┃  T +┃", grep, r"\.\.\.", grep, CHK_OFF + " web", gone, r"\[ \]",
         grep, "OK", only_fg, "green", darker, "OK", -3, grep, "OK {5}" + CHK_OFF]


def _01(c):
    """→、Enter 点 web: 变成打开的勾选图标(强调色), 对话框不关; ←、焦点回到 OK 后图标仍是强调色"""
    c - [RIGHT, ENTER, grep, CHK_ON + " web", gone, CHK_OFF,
         LEFT, grep, CHK_ON, only_fg, "green", chr_count, 1]


def _02(c):
    """Enter 按下 OK: 关闭并 resolve 'OK'; 下一个对话框是单选 A/B, 正文含 State 派生的文字"""
    c - [ENTER, grep, "result: OK", grep, r"selected A · \$\d\.\d\d",
         grep, RAD_ON + " A", only_fg, "green", grep, RAD_OFF + " B"]


def _03(c):
    """→ Enter 选 B: 单选互斥(● 移到 B), 正文随 sel 变成 'selected B'"""
    c - [RIGHT, ENTER, grep, r"selected B · \$\d\.\d\d", grep, RAD_ON + " B",
         gone, RAD_ON + " A", grep, RAD_OFF + " A"]


def _04(c):
    """→ Enter 点 web: 按钮写 footer(关掉 WebUI), 再按一次变回(打开 WebUI)"""
    c - [RIGHT, ENTER, grep, "关掉 WebUI", grep, CHK_ON + " web",
         ENTER, grep, "打开 WebUI", gone, "关掉 WebUI", grep, CHK_OFF + " web"]


def _05(c):
    """c.setTimeout(-1000) 每秒写 cost 和 body: 不按键费用也在涨"""
    c - [cost_grows]


def _06(c):
    """→ Enter 按 Done: resolve 'Done'; 下一个是 eachRow [2, 2] 的网格, 两行按钮按列居中对齐"""
    c - [RIGHT, ENTER, grep, "result: Done", grep, r"model +effort", grep, r"plan +web",
         centered, "effort", "web", centered, "model", "plan"]


def _07(c):
    """→ ↓ 换行保持列(effort 的正下方是 web), Enter 得到 'web'"""
    c - [RIGHT, DOWN, ENTER, grep, "result: web"]


def _08(c):
    """堆叠: Enter 按 Push(按钮返回文字 = 不关)出现 second; Esc 只关最上层, first 还在"""
    c - [grep, "first", ENTER, grep, "second", grep, "stacked", ESC,
         gone, "second", grep, "first"]


def _09(c):
    """替换: → Enter 按 Replace(返回 undefined = 关自己, 同时开了 third): first 没了, third 在, resolve 'Replace'"""
    c - [RIGHT, ENTER, grep, "third", grep, "replaced S1", gone, "first", grep, "result: Replace"]


def _10(c):
    """Enter 按 Fin 得 'Fin'; 下一个对话框正文可见, pi.notify(.., 'snack') 的角标在右上角"""
    c - [ENTER, grep, "result: Fin", grep, "closes itself", corner, "3m $0.12", "top"]


def _11(c):
    """ret('late') 在没人按键时从外部关闭, resolve 'late'; 角标仍在"""
    c - [wait, 1.8, grep, "result: late", gone, "closes itself", grep, "3m"]
