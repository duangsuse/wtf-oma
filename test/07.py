"""HIDDEN update (v2/demo.js update): update 默认 oldnew 只刷新上一个/新的焦点按钮, full 刷新全部; Tab / Shift-Tab 切换。标签 = 键名 + 渲染次数。"""
from tui import *

CMD = f"{DEMO} update"


def _00(c):
    """首帧: update=oldnew, 每个按钮渲染 1 次"""
    c - [grep, "update=oldnew", grep, r"A1 +B1 +C1"]


def _01(c):
    """→: 焦点 A→B, 只重新渲染 A(上一个, 初始 = or)和 B"""
    c - [RIGHT, grep, r"A2 +B2 +C1"]


def _02(c):
    """Tab 同 →: B→C, 只刷新 B 和 C(A 不再变)"""
    c - [TAB, grep, r"A2 +B3 +C2"]


def _03(c):
    """Shift-Tab 同 ←: C→B, 只刷新 C 和 B"""
    c - [BTAB, grep, r"A2 +B4 +C3"]


def _04(c):
    """Enter 按 B 得 'B'; 下一个对话框是 update=full, 首帧各渲染 1 次"""
    c - [ENTER, grep, "result: B", grep, "update=full", grep, r"A1 +B1 +C1"]


def _05(c):
    """full: Tab 一次, 三个按钮全部重新渲染"""
    c - [TAB, grep, r"A2 +B2 +C2"]
