"""窗口初始屏角 cfg.rempos=T_rd 与按窗口 id 记忆拖拽位置 (v2/demo.js dialogs): id = 对话框标题。"""
from tui import *

CMD = f"{DEMO} dialogs cfg.rempos=T_rd"


def _00(c):
    """rempos 'T_rd': 标题为 T 的对话框第一次出现在右下角(不是居中)"""
    c - [lower_right, "T"]


def _01(c):
    """OK -> 下一个标题 Ctrl+P 的 id 不是 T, 不受 rempos 影响: 居中, 不在右下象限"""
    c - [ENTER, grep, "Ctrl\\+P", left_of, "Ctrl+P", 40]


def _02(c):
    """把 Ctrl+P 拖到左边, Esc 关掉; 同标题 Ctrl+P 的下一个对话框(网格)放回拖过的位置而不是居中"""
    c - [drag, "Ctrl+P", -15, 0, ESC, left_of, "Ctrl+P", 20]
