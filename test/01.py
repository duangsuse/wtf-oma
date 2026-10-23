"""OMA_GRA=0 python3 menu.py, 80x24. 同一进程按 _00.._06 顺序执行，每条从上一条结束的画面开始。
"、" = 等到下一次画面变化后稳定；变化前进程退出或 2s 内无变化即失败。"""
from tui import *


def _00(c):
    """0.1s 内出首帧"""
    c - [opened, 0.1]


def _01(c):
    """↑、▼ 的字形或位置变化；↓、整屏(字+颜色)回到初始"""
    c - [UP, changed, "▼", DOWN, back]


def _02(c):
    """L、含 "Learn"；退格、整屏(字+颜色, 含选中项)回到初始"""
    c - ["L", grep, "Learn", BS, UP, back]


def _03(c):
    """L、回车、进入 Learn 子菜单，含 "Arch\""""
    c - ["L", ENTER, grep, "Arch"]


def _04(c):
    """ESC、退回根菜单且不退出，含 "Learn"；粘贴 "faq"、DEL、查询清空(显示 "Go…")，含 "Apps\""""
    c - [ESC, grep, "Learn", paste("faq"), DEL, grep, "Go…", grep, "Apps"]


def _05(c):
    """按住 "Go" 右拖 1 格松开、"Go" 右移 1 格；↓、"Go" 仍在新位置，非 ASCII 绿色字符数不变"""
    c - [drag, "Go", 1, 0, moved, "Go", 1, 0, DOWN, moved, "Go", 1, 0,
         grep, r"[^\w]", only_fg, "green", chr_count, "x1"]


def _06(c):
    """点 ▼ 右边第 7 格、出现同样的第二个窗口，非 ASCII 绿色字符数翻倍；退格、整屏回到初始"""
    c - [click, "▼", 7, 0, grep, r"[━]", only_fg, "green", chr_count, "x2",
         BS, back]
