"""命令行参数 cfg.<键>=值 改尺寸 (v2/demo.js dialogs cfg.itemMinW=10 cfg.dialogMinW=40 cfg.btnH=3 cfg.itemH=5)。"""
from tui import *

CMD = f"{DEMO} dialogs cfg.itemMinW=10 cfg.dialogMinW=40 cfg.btnH=3 cfg.itemH=5"


def _00(c):
    """按钮最小宽度 10(文字居中): OK 与下一个按钮的图标之间隔 3 + 1 + 3 = 7 列; 最小宽度 40: 窗口宽 40 + 6"""
    c - [grep, "OK {7}" + CHK_OFF, grep, "┏━+┓", chr_count, 46]


def button_rows(c):
    """cfg.btnH=3: OK 按钮的底色占 3 行(文字在中间行), 上下再外一行不是 —— 对话框按钮高度只看 btnH, 不看 cfg.itemH=5(那是菜单项的)"""
    x, y = c.frame.find("OK")
    bg = lambda dy: c.frame.cells[y + dy][x][2]
    c.check(bg(-1) == bg(0) == bg(1) and bg(-2) != bg(0) and bg(2) != bg(0), f"OK 的底色正好 3 行 ({[bg(d) for d in range(-2, 3)]})")


def _01(c):
    """按钮高度 btnH 独立于菜单项高度 itemH"""
    c - [button_rows]
