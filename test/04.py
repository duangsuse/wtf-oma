"""pi.omarchy.menu([], pi.if404(k => .., { 路径: () => .. })) (v2/demo.js omarchy) + 颜色可调 (color.selFg=#e03030)。"""
from tui import *

CMD = f"{DEMO} omarchy color.selFg=#e03030"


def _00(c):
    """会话自带的树: 选中项 Apps 的文字是调过的强调色(红), 其余项不是"""
    c - [grep, "Apps", only_fg, "red", grep, "Learn", only_fg, "red", chr_count, 0]


def _01(c):
    """L Enter 进 Learn, 输入 Arch(先命中 Omarchy)再 ↓ Enter: 叶子 -> 菜单关闭, 路径表里有 'Learn/Arch', resolve 'Learn/Arch'; 下一个菜单打开"""
    c - ["L", ENTER, grep, "Arch", "Arch", grep, "Omarchy", DOWN, ENTER, grep, r"result: Learn/Arch table", grep, "Learn"]


def _02(c):
    """Learn/Bash 没登记: if404 的 fallback 被调用"""
    c - ["L", ENTER, "Bash", ENTER, grep, r"result: Learn/Bash fallback"]


def _03(c):
    """自己的树 ['Root', ['MyPath', ['Arch'], ['Other']]]: 路径 'MyPath/Arch' 命中表里的项"""
    c - [grep, "MyPath", gone, r"┃.*Learn", ENTER, grep, "Other", ENTER, grep, r"result: MyPath/Arch mine"]


def _04(c):
    """Esc 退到底: 菜单消失, resolve null(没有 handler 被调)"""
    c - [grep, "Learn", ESC, grep, r"result: null +$", gone, r"┃.*Learn"]
