"""pi.arg.focusHL (v2/demo.js focus): HL 按钮切换 'color' <-> ''; '' 只在 gra.py 生效时才关掉按钮焦点高亮。
黑盒测试强制 OMA_GRA=0 ((等探测结果)正文显示 gra.py: none), 所以这里验证"没有 gra.py 时 focusHL='' 不生效": 否则焦点就看不出来了。
gra 生效(shm)时的关闭分支靠一次性冒烟(没有终端能回答 gra 的图形探测, 黑盒里造不出来)。"""
from tui import *

CMD = f"{DEMO} focus"


def _00(c):
    """(等探测结果)正文显示 gra.py: none 和 focusHL=color; 选中的 Yes 有焦点底色和强调色文字"""
    c - [wait, 0.6, grep, r"gra\.py: none +focusHL=color", bg_same, "Yes", "No", False, grep, "Yes", only_fg, "green", chr_count, 3]


def _01(c):
    """→ → Enter 按 HL: focusHL 变成 ''(正文和 [ ] 都变), 但没有 gra.py, 选中的 HL 按钮仍然有焦点底色"""
    c - [RIGHT, RIGHT, ENTER, grep, r"focusHL=''", grep, CHK_OFF + " HL", bg_same, "Yes", CHK_OFF, False]


def _02(c):
    """再按一次 HL: 变回 color"""
    c - [ENTER, grep, r"focusHL=color", grep, CHK_ON + " HL"]


def _03(c):
    """→ Enter 按 Done: resolve 'Done'"""
    c - [RIGHT, ENTER, grep, "result: Done"]
